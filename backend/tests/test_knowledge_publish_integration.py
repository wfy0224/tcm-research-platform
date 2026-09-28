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
from tcm_platform.main import _public_retrieval_result
from tcm_platform.models import (
    EmbeddingRecord,
    EventLog,
    EvidenceRevision,
    HumanReview,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    QualityIssue,
    TextSegmentRevision,
)
from tcm_platform.retrieval import build_retrieval_index, search_published
from tcm_platform.retrieval_benchmark import create_golden_query, run_benchmark
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


class FakeEmbedder:
    model_version = "test/fixed-embedding-v1"
    max_batch_size = 10

    def embed(self, texts):
        return [[1.0, float(len(value) % 7 + 1), 2.0] for value in texts]


def test_review_snapshot_and_index_publish_barrier(tmp_path):
    with SessionLocal() as session:
        previous_version_id = session.get(KnowledgeRuntimeState, 1).active_knowledge_version_id
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
    build_id = create_index_build(version_id, configuration={
        "strategy": "hybrid-v1", "embedding_model": FakeEmbedder.model_version,
    })

    with pytest.raises(ValueError, match="FTS and vector"):
        activate_knowledge_version(version_id, build_id)
    with SessionLocal() as session:
        assert session.get(QualityIssue, issue_id).status == "RESOLVED"
        assert session.get(HumanReview, review_id).decision == "APPROVE"
        assert session.get(EvidenceRevision, evidence_id).status == "REVIEWED"
        assert session.get(KnowledgeVersion, version_id).status == "INDEXING"
        assert session.get(IndexBuild, build_id).status == "PENDING"
        assert session.get(KnowledgeRuntimeState, 1).active_knowledge_version_id == previous_version_id
    assert compare_knowledge_versions(version_id, version_id)["evidence_revision"] == {
        "added": [], "removed": []
    }
    assert build_retrieval_index(build_id, embedder=FakeEmbedder()) >= 1
    activate_knowledge_version(version_id, build_id)
    results = search_published(
        "太阳之为病", embedder=FakeEmbedder(), source_ids=[imported.source_id]
    )
    assert results
    assert results[0]["evidence_revision_id"] == str(evidence_id)
    assert results[0]["quote_text"] == "太阳之为病，脉浮。"
    public_result = _public_retrieval_result(results[0]).model_dump()
    assert public_result["evidence_id"].startswith("EV-")
    assert public_result["evidence_revision_no"] == 1
    assert public_result["source_id"].startswith("SRC-")
    assert all(value.startswith("SEG-") for value in public_result["segment_ids"])
    assert public_result["citation_locator"]["start"] == results[0]["citation_locator"]["start"]
    assert str(evidence_id) not in str(public_result)
    assert str(imported.source_revision_id) not in str(public_result)
    query_id = create_golden_query(
        "太阳之为病", {evidence_id: "GOLD"}, source_ids=[imported.source_id]
    )
    benchmark = run_benchmark(embedder=FakeEmbedder(), k=3)
    measured = next(row for row in benchmark["queries"] if row["query_id"] == str(query_id))
    assert measured["recall_at_k"] == 1
    assert measured["evidence_resolution_rate"] == 1
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert runtime.active_knowledge_version_id == version_id
        assert runtime.active_index_build_id == build_id

    newer_version_id = create_knowledge_version()
    newer_build_id = create_index_build(newer_version_id, configuration={
        "strategy": "hybrid-v1", "embedding_model": FakeEmbedder.model_version,
    })
    build_retrieval_index(newer_build_id, embedder=FakeEmbedder())
    activate_knowledge_version(newer_version_id, newer_build_id)
    activate_knowledge_version(version_id, build_id)
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert (runtime.active_knowledge_version_id, runtime.active_index_build_id) == (
            version_id, build_id
        )

        event = session.scalar(select(EventLog).where(
            EventLog.event_type == "knowledge_version.activated",
            EventLog.aggregate_id == str(version_id),
        ).order_by(EventLog.sequence_no.desc()))
        assert event.payload["previous_knowledge_version_id"] == str(newer_version_id)
        assert event.payload["previous_index_build_id"] == str(newer_build_id)
        assert event.payload["historical_switch"] is True

    with SessionLocal.begin() as session:
        record = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == newer_build_id
        ))
        session.delete(record)
    with pytest.raises(ValueError, match="target FTS/vector index is incomplete"):
        activate_knowledge_version(newer_version_id, newer_build_id)
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert (runtime.active_knowledge_version_id, runtime.active_index_build_id) == (
            version_id, build_id
        )

    with SessionLocal() as session:
        stable_evidence_id = session.get(EvidenceRevision, evidence_id).evidence_id
    revised_evidence_id = create_evidence(
        [segment.id], strength="INDIRECT", evidence_id=stable_evidence_id
    )
    review_object(
        "evidence_revision", revised_evidence_id,
        reviewer_id="expert-1", decision="APPROVE", note="校订引用强度",
    )
    revised_version_id = create_knowledge_version()
    comparison = compare_knowledge_versions(version_id, revised_version_id)
    assert comparison["revision_changes"]["evidence_revision"] == [{
        "identity_id": str(stable_evidence_id),
        "from_revision_id": str(evidence_id),
        "to_revision_id": str(revised_evidence_id),
        "citation_impact": [{
            "kind": "concept", "object_id": str(concept_id), "retained_in_target": True,
        }],
    }]
