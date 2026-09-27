from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.db import SessionLocal, engine
from tcm_platform.knowledge_publish import (
    activate_knowledge_version,
    compare_knowledge_versions,
    create_index_build,
    create_knowledge_version,
    open_quality_issue,
    resolve_quality_issue,
    review_object,
)
from tcm_platform.knowledge_service import create_concept, create_evidence
from tcm_platform.models import (
    EvidenceRevision,
    HumanReview,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    QualityIssue,
    TextSegmentRevision,
)
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM governance.knowledge_version LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("E5 migration is not available")


def _finish_segment(import_job_id, store):
    for _ in range(100):
        result = process_next_segment(store=store)
        if result is None:
            break
        if result.import_job_id == import_job_id:
            assert result.status == "SEGMENTED"
            return
    pytest.fail("target segment job did not complete")


def test_review_snapshot_and_index_publish_barrier(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    path = tmp_path / "review.txt"
    path.write_text("太阳之为病，脉浮。", encoding="utf-8")
    imported = import_file(
        path, SourceMetadata(source_type="CLASSIC", title="审核测试古籍"),
        request_key=f"review:{uuid4()}", store=store,
    )
    assert process_next_import(store=store).status == "PARSED"
    _finish_segment(imported.import_job_id, store)
    with SessionLocal() as session:
        segment = session.scalar(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == imported.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        ))
    evidence_id = create_evidence([segment.id], strength="DIRECT")
    issue_id = open_quality_issue(
        "evidence_revision", evidence_id,
        issue_type="INVALID_EVIDENCE_LOCATION", severity="BLOCKER",
        description="待人工核对定位",
    )
    with pytest.raises(ValueError, match="blocker"):
        review_object(
            "evidence_revision", evidence_id,
            reviewer_id="expert-1", decision="APPROVE", note="核对后可引用",
        )
    resolve_quality_issue(issue_id, reviewer_id="expert-1", note="已核对原文及页码")
    review_id = review_object(
        "evidence_revision", evidence_id,
        reviewer_id="expert-1", decision="APPROVE", note="原文核对通过",
    )
    concept_id = create_concept(
        "太阳病", concept_type="DISEASE", evidence_revision_id=evidence_id
    )
    review_object(
        "concept", concept_id, reviewer_id="expert-1", decision="APPROVE",
        note="术语归一核对通过",
    )
    version_id = create_knowledge_version()
    build_id = create_index_build(version_id, configuration={"strategy": "hybrid-v1"})

    with pytest.raises(ValueError, match="FTS and vector"):
        activate_knowledge_version(version_id, build_id)
    with SessionLocal() as session:
        assert session.get(QualityIssue, issue_id).status == "RESOLVED"
        assert session.get(HumanReview, review_id).decision == "APPROVE"
        assert session.get(EvidenceRevision, evidence_id).status == "REVIEWED"
        assert session.get(KnowledgeVersion, version_id).status == "INDEXING"
        assert session.get(IndexBuild, build_id).status == "PENDING"
        assert session.get(KnowledgeRuntimeState, 1).active_knowledge_version_id is None
    assert compare_knowledge_versions(version_id, version_id)["evidence_revision"] == {
        "added": [], "removed": []
    }
