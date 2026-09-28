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
    supersede_reviewed_object,
)
from tcm_platform.knowledge_service import create_concept, create_evidence, create_relation
from tcm_platform.main import _public_retrieval_result
from tcm_platform.models import (
    EmbeddingRecord,
    EventLog,
    EvidenceRevision,
    HumanReview,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    KnowledgeVersionItem,
    KnowledgeVersionReference,
    QualityIssue,
    ResearchTask,
    TaskEvidenceRef,
    TextSegmentRevision,
)
from tcm_platform.research_runtime import execute_planner
from tcm_platform.research_service import (
    create_research_task,
    retrieve_for_task,
    start_research_task,
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


class FakePlanner:
    model_version = "test/frozen-task-planner-v1"

    def complete_json(self, _system_prompt, input_payload):
        return {"subquestions": [input_payload["question"]]}


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
    related_concept_id = create_concept(
        "表证", concept_type="PATTERN", evidence_revision_id=evidence_id
    )
    review_object(
        "concept", related_concept_id, reviewer_id="expert-1", decision="APPROVE",
        note="术语归一核对通过",
    )
    relation_id = create_relation(
        concept_id, related_concept_id, relation_type="RELATED_TO",
        assertion_text="太阳病与表证相关", evidence_revision_id=evidence_id,
    )
    review_object(
        "relation", relation_id, reviewer_id="expert-1", decision="APPROVE",
        note="关系及引用核对通过",
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
    frozen_task_id = create_research_task(
        "太阳之为病", source_ids=[imported.source_id]
    )
    start_research_task(frozen_task_id, model_version=FakePlanner.model_version)
    revised_evidence_id = create_evidence(
        [segment.id], strength="INDIRECT", evidence_id=stable_evidence_id
    )
    review_object(
        "evidence_revision", revised_evidence_id,
        reviewer_id="expert-1", decision="APPROVE", note="校订引用强度",
    )
    revised_version_id = create_knowledge_version()
    comparison = compare_knowledge_versions(version_id, revised_version_id)
    historical = comparison["historical_reference_changes"]["added"]
    assert {item["object_id"] for item in historical if
            item["evidence_revision_id"] == str(evidence_id)} >= {
        str(concept_id), str(related_concept_id), str(relation_id)
    }
    evidence_change = comparison["revision_changes"]["evidence_revision"]
    assert len(evidence_change) == 1
    assert evidence_change[0]["identity_id"] == str(stable_evidence_id)
    assert evidence_change[0]["from_revision_id"] == str(evidence_id)
    assert evidence_change[0]["to_revision_id"] == str(revised_evidence_id)
    assert {item["object_id"] for item in evidence_change[0]["citation_impact"]} == {
        str(concept_id), str(related_concept_id), str(relation_id)
    }
    revised_build_id = create_index_build(revised_version_id, configuration={
        "strategy": "hybrid-v1", "embedding_model": FakeEmbedder.model_version,
    })
    build_retrieval_index(revised_build_id, embedder=FakeEmbedder())
    activate_knowledge_version(revised_version_id, revised_build_id)
    revised_results = search_published(
        "太阳之为病", embedder=FakeEmbedder(), source_ids=[imported.source_id]
    )
    assert revised_results
    assert {result["evidence_revision_id"] for result in revised_results} == {
        str(revised_evidence_id)
    }
    execute_planner(frozen_task_id, model=FakePlanner())
    assert retrieve_for_task(frozen_task_id, embedder=FakeEmbedder()) == 1
    with SessionLocal() as session:
        frozen_task = session.get(ResearchTask, frozen_task_id)
        assert frozen_task.execution_context["knowledge_version_id"] == str(version_id)
        assert frozen_task.execution_context["index_build_id"] == str(build_id)
        frozen_evidence = set(session.scalars(select(TaskEvidenceRef.evidence_revision_id).where(
            TaskEvidenceRef.task_id == frozen_task_id,
        )))
        assert frozen_evidence == {evidence_id}
    activate_knowledge_version(version_id, build_id)
    replacement_concept_id = create_concept(
        "太阳病校订", concept_type="DISEASE", evidence_revision_id=revised_evidence_id
    )
    review_object(
        "concept", replacement_concept_id, reviewer_id="expert-1",
        decision="APPROVE", note="校订证据引用",
    )
    assert supersede_reviewed_object("concept", concept_id, replacement_concept_id) == 2
    with pytest.raises(ValueError, match="already superseded"):
        supersede_reviewed_object("concept", concept_id, replacement_concept_id)
    with pytest.raises(ValueError, match="relation still points"):
        create_knowledge_version()
    replacement_related_id = create_concept(
        "表证校订", concept_type="PATTERN", evidence_revision_id=revised_evidence_id
    )
    review_object(
        "concept", replacement_related_id, reviewer_id="expert-1",
        decision="APPROVE", note="校订证据引用",
    )
    assert supersede_reviewed_object("concept", related_concept_id, replacement_related_id) == 2
    replacement_relation_id = create_relation(
        replacement_concept_id, replacement_related_id, relation_type="RELATED_TO",
        assertion_text="校订后太阳病与表证相关", evidence_revision_id=revised_evidence_id,
    )
    review_object(
        "relation", replacement_relation_id, reviewer_id="expert-1", decision="APPROVE",
        note="关系及新版证据核对通过",
    )
    assert supersede_reviewed_object("relation", relation_id, replacement_relation_id) == 2
    corrected_version_id = create_knowledge_version()
    corrected = compare_knowledge_versions(version_id, corrected_version_id)
    assert str(concept_id) in corrected["concept"]["removed"]
    assert str(replacement_concept_id) in corrected["concept"]["added"]
    assert corrected["revision_changes"]["relation"][0]["revision_no"] == 2
    assert {item["to_revision_id"] for item in
            corrected["revision_changes"]["concept"]} == {
        str(replacement_concept_id), str(replacement_related_id)
    }
    with SessionLocal() as session:
        original_items = list(session.scalars(select(KnowledgeVersionItem).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.concept_id == concept_id,
        )))
        assert len(original_items) == 1
        corrected_refs = list(session.scalars(select(KnowledgeVersionReference).where(
            KnowledgeVersionReference.knowledge_version_id == corrected_version_id,
            KnowledgeVersionReference.target_id.in_([
                concept_id, related_concept_id, relation_id,
                replacement_concept_id, replacement_related_id, replacement_relation_id,
            ]),
        )))
        assert not corrected_refs
    corrected_build_id = create_index_build(corrected_version_id, configuration={
        "strategy": "hybrid-v1", "embedding_model": FakeEmbedder.model_version,
    })
    build_retrieval_index(corrected_build_id, embedder=FakeEmbedder())
    activate_knowledge_version(corrected_version_id, corrected_build_id)
    activate_knowledge_version(version_id, build_id)
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert (runtime.active_knowledge_version_id, runtime.active_index_build_id) == (
            version_id, build_id
        )
