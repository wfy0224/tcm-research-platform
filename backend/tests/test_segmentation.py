from uuid import uuid4

from tcm_platform.parsing import ParsedDocument, ParsedPage
from tcm_platform.segmentation import (
    PreviousSegment,
    align_revisions,
    detect_split_merge,
    resolve_structure,
)


def _drafts(text):
    return resolve_structure(
        ParsedDocument("txt", [ParsedPage(1, text)], "utf-8", []), title="测试书"
    )


def _previous(drafts):
    return [
        PreviousSegment(
            revision_id=uuid4(),
            segment_id=uuid4(),
            segment_type=draft.segment_type,
            original_text=draft.original_text,
            normalized_text=draft.normalized_text,
            checksum=draft.checksum,
            structural_locator=draft.structural_locator,
        )
        for draft in drafts
    ]


def test_split_and_merge_are_recorded_as_many_to_many_alignment():
    first = _drafts("甲乙丙丁戊己庚辛")
    second = _drafts("甲乙丙丁\n戊己庚辛")
    old = _previous(first)
    decisions, deleted = align_revisions(second, old)
    changes, new_indices, old_ids = detect_split_merge(second, decisions, deleted)
    assert len([change for change in changes if change.status == "SPLIT"]) == 2
    assert len(new_indices) == 2
    assert len(old_ids) == 1

    old = _previous(second)
    decisions, deleted = align_revisions(first, old)
    changes, new_indices, old_ids = detect_split_merge(first, decisions, deleted)
    assert len([change for change in changes if change.status == "MERGED"]) == 2
    assert len(new_indices) == 1
    assert len(old_ids) == 2
