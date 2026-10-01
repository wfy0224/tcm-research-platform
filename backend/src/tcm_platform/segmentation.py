"""Deterministic structure resolution; outputs drafts, never published Evidence."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from itertools import pairwise
from uuid import UUID

from tcm_platform.parsing import ParsedDocument

RESOLVER_VERSION = "structure-resolver/v2"
NUMBER = r"[一二三四五六七八九十百千零〇两\d]+"
VOLUME = re.compile(rf"^(?:卷{NUMBER}|第{NUMBER}卷)(?:[\s　].*)?$")
CHAPTER = re.compile(rf"^(?:第{NUMBER}[篇章]|.{1,30}篇)(?:[\s　].*)?$")
SECTION = re.compile(rf"^第{NUMBER}节(?:[\s　].*)?$")
CLAUSE = re.compile(rf"^(?:第{NUMBER}条|\d{{1,5}}[.．、]|【[^】]{{1,30}}】)")
SENTENCE = re.compile(r"[^。！？!?]+[。！？!?]*[”’」』）)]*|[。！？!?]+[”’」』）)]*")
PARAGRAPH_TYPES = frozenset({"CLAUSE", "PARAGRAPH", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"})
END_SENTENCE = re.compile(r"[。！？!?．.][\"”’」』）)]*$")


def _new_block(line: str) -> bool:
    return bool(VOLUME.match(line) or CHAPTER.match(line) or SECTION.match(line)
                or CLAUSE.match(line) or line.startswith(("按语：", "按曰：", "案语：", "注：", "注曰：", "医案：", "病案：", "方：", "处方："))
                or (len(line) <= 20 and not re.search(r"[，。；：！？、,.!?;:]", line)))


def _logical_blocks(parsed: ParsedDocument):
    """Join likely typesetting wraps; retain physical page/line provenance.

    Short unpunctuated classical lines and headings remain separate. Long CJK
    lines with unfinished sentences may continue even across OCR blank lines.
    DOCX paragraph boundaries always take precedence over that heuristic.
    """
    lines, positions = [], []
    previous = ""
    for page in parsed.pages:
        for line_no, raw in enumerate(page.text.splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            authoritative_break = (page.paragraph_starts is not None
                                   and line_no in page.paragraph_starts)
            wrapped = (len(previous) >= 30 and re.search(r"[\u3400-\u9fff]", previous)
                       and not END_SENTENCE.search(previous) and not _new_block(line))
            docx_wrap = page.paragraph_starts is not None and not authoritative_break
            if lines and (authoritative_break or not (wrapped or docx_wrap)):
                yield "\n".join(lines), positions
                lines, positions = [], []
            lines.append(line)
            positions.append({"page_no": page.page_no, "line_no": line_no})
            previous = line
    if lines:
        yield "\n".join(lines), positions


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SegmentDraft:
    segment_type: str
    parent_index: int | None
    sequence_no: int
    original_text: str
    normalized_text: str
    context_before: str
    context_after: str
    page_no: int | None
    chapter_no: int | None
    paragraph_no: int | None
    structural_locator: dict
    checksum: str


@dataclass(frozen=True)
class PreviousSegment:
    revision_id: UUID
    segment_id: UUID
    segment_type: str
    original_text: str
    normalized_text: str
    checksum: str
    structural_locator: dict


@dataclass(frozen=True)
class AlignmentDecision:
    old: PreviousSegment | None
    status: str


@dataclass(frozen=True)
class StructuralChange:
    old_revision_id: UUID
    new_index: int
    status: str


def resolve_structure(parsed: ParsedDocument, *, title: str) -> list[SegmentDraft]:
    if not title.strip():
        raise ValueError("source title is required")
    drafts: list[SegmentDraft] = []

    def add(
        kind: str,
        parent: int | None,
        content: str,
        *,
        path: str,
        page: int | None,
        chapter: int | None,
        paragraph: int | None,
    ) -> int:
        index = len(drafts)
        drafts.append(
            SegmentDraft(
                segment_type=kind,
                parent_index=parent,
                sequence_no=index,
                original_text=content,
                normalized_text=normalized(content),
                context_before="",
                context_after="",
                page_no=page,
                chapter_no=chapter,
                paragraph_no=paragraph,
                structural_locator={
                    "path": path,
                    "page_no": page,
                    "chapter_no": chapter,
                    "paragraph_no": paragraph,
                },
                checksum=checksum(content),
            )
        )
        return index

    book = add("BOOK", None, title.strip(), path="book", page=None, chapter=None, paragraph=None)
    volume: int | None = None
    chapter: int | None = None
    section: int | None = None
    chapter_no = 0
    paragraph_no = 0
    volume_no = 0
    section_no = 0

    for line, physical_lines in _logical_blocks(parsed):
        page = physical_lines[0]["page_no"]
        if len(line) <= 100 and VOLUME.match(line):
            volume_no += 1
            volume = add(
                "VOLUME", book, line, path=f"volume:{volume_no}",
                page=page, chapter=None, paragraph=None,
            )
            chapter = None
            section = None
            continue
        if len(line) <= 100 and CHAPTER.match(line):
            chapter_no += 1
            chapter = add(
                "CHAPTER", volume if volume is not None else book, line,
                path=f"chapter:{chapter_no}", page=page,
                chapter=chapter_no, paragraph=None,
            )
            section = None
            continue
        if len(line) <= 100 and SECTION.match(line):
            section_no += 1
            section = add(
                "SECTION", chapter if chapter is not None else (volume or book), line,
                path=f"section:{section_no}", page=page,
                chapter=chapter_no or None, paragraph=None,
            )
            continue

        paragraph_no += 1
        parent = section if section is not None else (
            chapter if chapter is not None else (volume if volume is not None else book)
        )
        if CLAUSE.match(line):
            kind = "CLAUSE"
        elif line.startswith(("按语：", "按曰：", "案语：")):
            kind = "COMMENTARY"
        elif line.startswith(("注：", "注曰：")):
            kind = "NOTE"
        elif line.startswith(("医案：", "病案：")):
            kind = "CASE_NOTE"
        elif line.startswith(("方：", "处方：")):
            kind = "FORMULA_TEXT"
        else:
            kind = "PARAGRAPH"
        line_index = add(
            kind, parent, line, path=f"paragraph:{paragraph_no}",
            page=page, chapter=chapter_no or None, paragraph=paragraph_no,
        )
        drafts[line_index].structural_locator.update({
            "line_start": physical_lines[0]["line_no"],
            "line_end": physical_lines[-1]["line_no"],
            "page_end": physical_lines[-1]["page_no"],
            "physical_lines": physical_lines,
        })
        for sentence_no, sentence in enumerate(SENTENCE.findall(line), 1):
            if not sentence.strip():
                continue
            add(
                "SENTENCE", line_index, sentence,
                path=f"paragraph:{paragraph_no}/sentence:{sentence_no}",
                page=page, chapter=chapter_no or None, paragraph=paragraph_no,
            )

    siblings: dict[tuple[int | None, str], list[int]] = {}
    for index, draft in enumerate(drafts):
        siblings.setdefault((draft.parent_index, "BODY" if draft.segment_type in PARAGRAPH_TYPES else draft.segment_type), []).append(index)
    for indices in siblings.values():
        for position, index in enumerate(indices):
            before = drafts[indices[position - 1]].original_text[-1000:] if position else ""
            after = (
                drafts[indices[position + 1]].original_text[:1000]
                if position + 1 < len(indices) else ""
            )
            drafts[index] = replace(drafts[index], context_before=before, context_after=after)
    return drafts


def align_revisions(
    drafts: list[SegmentDraft], previous: list[PreviousSegment]
) -> tuple[list[AlignmentDecision], list[PreviousSegment]]:
    """Prefer exact content; reuse identity for clear edits only."""
    decisions: list[AlignmentDecision | None] = [None] * len(drafts)
    unmatched = {old.revision_id: old for old in previous}

    def claim(index: int, old: PreviousSegment, status: str) -> None:
        decisions[index] = AlignmentDecision(old, status)
        unmatched.pop(old.revision_id)

    # Same structural location and content is the strongest identity signal.
    by_location = {
        (old.segment_type, old.structural_locator.get("path")): old for old in previous
    }
    for index, draft in enumerate(drafts):
        old = by_location.get((draft.segment_type, draft.structural_locator["path"]))
        if (
            old and old.revision_id in unmatched and old.checksum == draft.checksum
            and old.structural_locator == draft.structural_locator
        ):
            claim(index, old, "UNCHANGED")

    # A unique exact text match at a new location is a move, not a modification.
    for index, draft in enumerate(drafts):
        if decisions[index] is not None:
            continue
        matches = [
            old for old in unmatched.values()
            if old.segment_type == draft.segment_type and old.checksum == draft.checksum
        ]
        if len(matches) == 1:
            claim(index, matches[0], "MOVED")

    # Position alone is insufficient: require strong similarity before reusing identity.
    for index, draft in enumerate(drafts):
        if decisions[index] is not None:
            continue
        old = by_location.get((draft.segment_type, draft.structural_locator["path"]))
        if old and old.revision_id in unmatched:
            similarity = SequenceMatcher(
                None, old.normalized_text, draft.normalized_text, autojunk=False
            ).ratio()
            if similarity >= 0.75:
                claim(index, old, "MODIFIED")

    return [decision or AlignmentDecision(None, "ADDED") for decision in decisions], list(
        unmatched.values()
    )


def detect_split_merge(
    drafts: list[SegmentDraft],
    decisions: list[AlignmentDecision],
    deleted: list[PreviousSegment],
) -> tuple[list[StructuralChange], set[int], set[UUID]]:
    """Recognize exact text reflow across adjacent paragraph-level segments."""
    eligible = {"CLAUSE", "PARAGRAPH", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"}
    additions = [
        index for index, decision in enumerate(decisions)
        if decision.status == "ADDED" and drafts[index].segment_type in eligible
    ]
    removals = [old for old in deleted if old.segment_type in eligible]
    used_new: set[int] = set()
    used_old: set[UUID] = set()
    changes: list[StructuralChange] = []

    # One old line split into two neighboring lines under the same parent.
    for old in removals:
        if old.revision_id in used_old:
            continue
        for left, right in pairwise(additions):
            if left in used_new or right in used_new:
                continue
            a, b = drafts[left], drafts[right]
            if (
                a.paragraph_no is not None
                and b.paragraph_no == a.paragraph_no + 1
                and a.segment_type == b.segment_type == old.segment_type
                and a.parent_index == b.parent_index
                and a.normalized_text + b.normalized_text == old.normalized_text
            ):
                changes.extend([
                    StructuralChange(old.revision_id, left, "SPLIT"),
                    StructuralChange(old.revision_id, right, "SPLIT"),
                ])
                used_new.update((left, right))
                used_old.add(old.revision_id)
                break

    # Two adjacent old lines merged into one new line. Old paths encode the
    # original global paragraph order, so unrelated lines cannot be combined.
    for index in additions:
        if index in used_new:
            continue
        draft = drafts[index]
        for left, right in pairwise(removals):
            if left.revision_id in used_old or right.revision_id in used_old:
                continue
            left_no = left.structural_locator.get("paragraph_no")
            right_no = right.structural_locator.get("paragraph_no")
            if (
                left.segment_type == right.segment_type == draft.segment_type
                and left_no is not None and right_no == left_no + 1
                and left.structural_locator.get("chapter_no")
                == right.structural_locator.get("chapter_no")
                and left.normalized_text + right.normalized_text == draft.normalized_text
            ):
                changes.extend([
                    StructuralChange(left.revision_id, index, "MERGED"),
                    StructuralChange(right.revision_id, index, "MERGED"),
                ])
                used_new.add(index)
                used_old.update((left.revision_id, right.revision_id))
                break
    return changes, used_new, used_old
