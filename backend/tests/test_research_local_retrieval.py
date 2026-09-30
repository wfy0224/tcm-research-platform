"""Local research retrieval uses real FTS indexes and retains outbound gates."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tcm_platform.db import SessionLocal
from tcm_platform.debate_service import retrieve_evidence_requests
from tcm_platform.knowledge_publish import (
    activate_knowledge_version,
    create_index_build,
    create_knowledge_version,
    review_object,
)
from tcm_platform.knowledge_service import create_evidence
from tcm_platform.models import (
    AgentRun,
    Claim,
    Critique,
    EmbeddingRecord,
    EvidenceRequest,
    EvidenceRetrievalEvent,
    IndexBuild,
    ResearchTask,
    TaskEvidenceRef,
    TextSegmentRevision,
)
from tcm_platform.publication_config import LOCAL_STRATEGY
from tcm_platform.research_runtime import recorded_complete
from tcm_platform.research_service import (
    create_research_task,
    frozen_retrieval_clients,
    retrieve_for_task,
    save_research_plan,
    start_research_task,
)
from tcm_platform.retrieval import build_retrieval_index
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore

MODEL = "deepseek/deepseek-flash"
QUOTE = "太阳之为病，脉浮，头项强痛而恶寒。"


class UntouchableClient:
    @property
    def model_version(self):
        pytest.fail("local strategy must not inspect or call a cloud retrieval client")


def test_explicit_local_strategy_discards_clients_without_touching_them():
    context = {"retrieval_strategy": LOCAL_STRATEGY,
               "embedding_model": None, "rerank_model": None,
               "outbound_mode": "CLOUD_ALLOWED", "generation_model": MODEL}
    original = dict(context)
    assert frozen_retrieval_clients(
        context, embedder=UntouchableClient(), reranker=UntouchableClient(),
    ) == (None, None)
    assert context == original


@pytest.mark.parametrize("field", ["embedding_model", "rerank_model"])
def test_local_context_with_cloud_model_is_rejected(field):
    context = {"retrieval_strategy": LOCAL_STRATEGY,
               "embedding_model": None, "rerank_model": None, field: "cloud/model"}
    with pytest.raises(ValueError, match="local retrieval context"):
        frozen_retrieval_clients(context, embedder=None)


@pytest.mark.parametrize("strategy", [None, "hybrid-rrf-v1", "hybrid-v1"])
def test_hybrid_and_legacy_contexts_still_require_matching_models(strategy):
    context = {"embedding_model": "test/embed", "rerank_model": "test/rerank"}
    if strategy is not None:
        context["retrieval_strategy"] = strategy
    embedder = SimpleNamespace(model_version="test/embed")
    reranker = SimpleNamespace(model_version="test/rerank")
    assert frozen_retrieval_clients(context, embedder=embedder, reranker=reranker) == (
        embedder, reranker,
    )
    for wrong_embedder, wrong_reranker in (
        (None, None), (embedder, None),
        (SimpleNamespace(model_version="test/other"), reranker),
        (embedder, SimpleNamespace(model_version="test/other")),
    ):
        with pytest.raises(ValueError, match="retrieval models differ"):
            frozen_retrieval_clients(context, embedder=wrong_embedder, reranker=wrong_reranker)


@pytest.fixture
def published_local_source(tmp_path, monkeypatch, request):
    mode = getattr(request, "param", "CLOUD_ALLOWED")
    monkeypatch.setenv("TCM_OUTBOUND_MODE", mode)
    store = ContentAddressedStore(tmp_path / "store")
    path = tmp_path / "local-research.txt"
    path.write_text(QUOTE, encoding="utf-8")
    imported = import_file(
        path, SourceMetadata(source_type="CLASSIC", title=f"本地研究测试 {uuid4()}",
                             data_level="PUBLIC", copyright_status="PUBLIC_DOMAIN",
                             outbound_authorized=True, outbound_reason="工程测试公版摘录"),
        request_key=f"local-research:{uuid4()}", store=store,
    )
    for _ in range(100):
        result = process_next_import(store=store)
        assert result is not None, "target import job did not run"
        if result.import_job_id == imported.import_job_id:
            assert result.status == "PARSED"
            break
    else:
        pytest.fail("target import job did not finish")
    for _ in range(100):
        result = process_next_segment(store=store)
        assert result is not None, "target segmentation job did not run"
        if result.import_job_id == imported.import_job_id:
            assert result.status == "SEGMENTED"
            break
    else:
        pytest.fail("target segmentation job did not finish")
    with SessionLocal() as session:
        segment = session.scalar(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == imported.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        ))
        assert segment is not None
        segment_id = segment.id
    evidence_id = create_evidence([segment_id], strength="DIRECT")
    review_object("evidence_revision", evidence_id, reviewer_id="test-reviewer",
                  decision="APPROVE", note="仅工程测试，原文与定位核验")
    version_id = create_knowledge_version()
    build_id = create_index_build(version_id, configuration={
        "strategy": LOCAL_STRATEGY, "embedding_model": None, "rerank_model": None,
        "embedding_endpoint": None, "rerank_endpoint": None,
    })
    assert build_retrieval_index(build_id) >= 1
    activate_knowledge_version(version_id, build_id)
    with SessionLocal() as session:
        build = session.get(IndexBuild, build_id)
        assert build.fts_status == "READY" and build.vector_status == "NOT_APPLICABLE"
        assert session.scalar(select(EmbeddingRecord.id).where(
            EmbeddingRecord.index_build_id == build_id,
        )) is None
    return imported.source_id, evidence_id, version_id, build_id


def test_real_local_index_research_initial_and_debate_retrieval(published_local_source):
    source_id, evidence_id, version_id, build_id = published_local_source
    task_id = create_research_task("太阳之为病", source_ids=[source_id])
    fingerprint = start_research_task(task_id, model_version=MODEL,
                                      question_outbound_authorized=True)
    with SessionLocal() as session:
        context = session.get(ResearchTask, task_id).execution_context
        assert context["retrieval_strategy"] == LOCAL_STRATEGY
        assert context["outbound_mode"] == "CLOUD_ALLOWED"
        assert context["embedding_model"] is None and context["rerank_model"] is None
        assert context["knowledge_version_id"] == str(version_id)
        assert context["index_build_id"] == str(build_id)
    save_research_plan(task_id, {"subquestions": ["脉浮"]})
    assert retrieve_for_task(task_id) == 1
    with SessionLocal.begin() as session:
        # Persisted debate fixture, not generated research or a customer result.
        task = session.get(ResearchTask, task_id)
        task.status = "DEBATING"
        classicist = AgentRun(task_id=task_id, role="Classicist", round_no=1,
                             status="COMPLETED", input_snapshot={},
                             visible_evidence_ids=[str(evidence_id)], model_version=MODEL)
        critic = AgentRun(task_id=task_id, role="Critic", round_no=2,
                          status="COMPLETED", input_snapshot={},
                          visible_evidence_ids=[str(evidence_id)], model_version=MODEL)
        session.add_all([classicist, critic])
        session.flush()
        claim = Claim(task_id=task_id, agent_run_id=classicist.id, agent_role="Classicist",
                      claim_type="DIRECT_TEXT", assertion_text=QUOTE,
                      rationale_summary="本地补证检索工程测试", audit_status="SUPPORTED")
        session.add(claim)
        session.flush()
        critique = Critique(task_id=task_id, agent_run_id=critic.id,
                            target_claim_id=claim.id, issue_type="EVIDENCE_GAP",
                            rationale_summary="复核原文")
        session.add(critique)
        session.flush()
        evidence_request = EvidenceRequest(task_id=task_id, critique_id=critique.id,
                                           query_text="头项强痛")
        session.add(evidence_request)
        session.flush()
        request_id = evidence_request.id
    assert retrieve_evidence_requests(task_id) == 0  # Already pooled, new request occurrence.
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        assert task.run_fingerprint == fingerprint
        assert task.execution_context == context
        assert list(session.scalars(select(TaskEvidenceRef.evidence_revision_id).where(
            TaskEvidenceRef.task_id == task_id,
        ))) == [evidence_id]
        resolved = session.get(EvidenceRequest, request_id)
        assert resolved.status == "RETRIEVED" and resolved.result_count == 1
        occurrences = list(session.scalars(select(EvidenceRetrievalEvent).where(
            EvidenceRetrievalEvent.task_id == task_id,
        )))
        assert any(row.evidence_request_id == request_id for row in occurrences)
        assert all("vector" not in row.channels and "rerank" not in row.channels
                   for row in occurrences)


@pytest.mark.parametrize("published_local_source,question_authorized", [
    ("LOCAL_ONLY", True), ("CLOUD_ALLOWED", False),
], indirect=["published_local_source"])
def test_local_retrieval_does_not_bypass_generation_authorization(
    published_local_source, question_authorized, monkeypatch,
):
    source_id, _, _, _ = published_local_source
    task_id = create_research_task("太阳之为病", source_ids=[source_id])
    start_research_task(task_id, model_version=MODEL,
                        question_outbound_authorized=question_authorized)
    # Current permission cannot upgrade a historical LOCAL_ONLY frozen build.
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "CLOUD_ALLOWED")

    class ForbiddenRemoteModel:
        model_version = MODEL
        is_remote = True
        api_key = "test-only-never-sent"

        def complete_json(self, *args):
            pytest.fail("unauthorized generation must fail before calling the model")

    with pytest.raises(PermissionError, match="disabled|explicit remote-model authorization"):
        recorded_complete(task_id, None, "Planner", ForbiddenRemoteModel(), "", {})
