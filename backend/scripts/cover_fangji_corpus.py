"""Copy and verify every real reading paragraph before research retrieval.

Windows runtimes are not used. Resume markers are checked against persisted
objects; no evidence is selected by agreement with a research answer.
"""
import hashlib
import json
import os
from itertools import groupby
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine.url import make_url

os.environ["TCM_DATABASE_URL"] = make_url(os.environ["TCM_DATABASE_URL"]).set(
    database="tcm_vib62_workspace_test").render_as_string(hide_password=False)

from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_publish import review_object
from tcm_platform.knowledge_service import create_evidence, trace_evidence
from tcm_platform.models import (
    EvidenceRevision,
    SourceDocument,
    SourceRevision,
    TextSegmentRevision,
)

with SessionLocal() as session:
    source = session.scalar(select(SourceDocument).where(
        SourceDocument.public_id == "SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350"))
    revision = session.scalar(select(SourceRevision).where(
        SourceRevision.source_id == source.id, SourceRevision.revision_no == 2))
    segments = list(session.scalars(select(TextSegmentRevision).where(
        TextSegmentRevision.source_revision_id == revision.id,
        TextSegmentRevision.segment_type.in_(("PARAGRAPH", "CLAUSE")),
    ).order_by(TextSegmentRevision.sequence_no)))
cache = Path("/tmp/tcm_vib62_workspace_test_full_fangji_review/coverage")
cache.mkdir(parents=True, exist_ok=True)
groups = []
for _, siblings in groupby(segments, key=lambda s: s.parent_segment_id):
    current = []
    for segment in siblings:
        proposed = [*current, segment]
        text = "\n".join(s.original_text for s in proposed)
        if current and (len(current) >= 5 or len(text) + len(current[0].context_before)
                        + len(segment.context_after) + 2 > 3500):
            groups.append(current)
            current = []
        current.append(segment)
    if current:
        groups.append(current)
reviewed, failed = [], []
for number, group in enumerate(groups):
    checksum = hashlib.sha256("\n".join(s.original_text for s in group).encode()).hexdigest()
    marker = cache / f"{group[0].sequence_no}.json"
    try:
        if marker.exists():
            saved = json.loads(marker.read_text())
            with SessionLocal() as session:
                ev = session.get(EvidenceRevision, UUID(saved["evidence_revision_id"]))
                assert ev is not None and ev.status == "REVIEWED" and ev.quote_checksum == checksum
            reviewed.append(saved)
            continue
        # Every paragraph is included in sequence. The normal trace gate verifies
        # source revision, ordered refs and frozen text; this is textual review.
        assert all(hashlib.sha256(s.original_text.encode()).hexdigest() == s.checksum for s in group)
        ev_id = create_evidence([s.id for s in group], strength="BACKGROUND",
                                actor_id="codex-user-authorized-full-text-review")
        trace_evidence(ev_id)
        review_object("evidence_revision", ev_id,
                      reviewer_id="codex-user-authorized-full-text-review", decision="APPROVE",
                      note="用户要求整份方剂资料审核；按原文顺序完整覆盖，核对片段校验和、精确修订、引用边界。仅文本真实性核对，不将教材陈述或医案升级为医学定论。")
        saved = {"evidence_revision_id": str(ev_id), "paragraphs": [s.paragraph_no for s in group],
                 "quote_checksum": checksum, "status": "REVIEWED"}
        marker.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf8")
        reviewed.append(saved)
    except (ValueError, AssertionError) as exc:
        failed.append({"paragraphs": [s.paragraph_no for s in group], "reason": str(exc)})
    if number % 25 == 0:
        print(json.dumps({"stage": "full-source-coverage", "reviewed_chunks": len(reviewed),
                          "failed": len(failed), "total_chunks": len(groups)}), flush=True)
covered = {p for row in reviewed for p in row["paragraphs"]}
result = {"reading_segments": len(segments), "covered_paragraphs": len(covered),
          "total_chunks": len(groups), "reviewed_chunks": len(reviewed), "failed": failed,
          "simulated_data": False, "selection_based_on_answer": False}
(cache.parent / "coverage.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(result, ensure_ascii=False), flush=True)
