from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.db import SessionLocal, engine
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.models import (
    AgentRun,
    Claim,
    ClaimEvidence,
    EmbeddingRecord,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersionItem,
    TaskEvidenceRef,
)
from tcm_platform.research_runtime import execute_first_round, execute_planner
from tcm_platform.research_service import (
    agent_visible_context,
    create_research_task,
    prepare_first_round,
    retrieve_for_task,
    start_research_task,
    submit_first_round_output,
)


def test_agent_can_abstain_when_visible_evidence_is_insufficient():
    from tcm_platform.research_service import ResearchAgentOutput

    assert ResearchAgentOutput.model_validate({"claims": []}).claims == []


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM research.research_task LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("E7 migration is not available")


class FakeEmbedder:
    max_batch_size = 10

    def __init__(self, model_version: str, dimensions: int):
        self.model_version = model_version
        self.dimensions = dimensions

    def embed(self, texts):
        return [[1.0] * self.dimensions for _ in texts]


class FakeReranker:
    def __init__(self, model_version: str):
        self.model_version = model_version

    def rerank(self, query, documents):
        return [(index, float(len(documents) - index)) for index in range(len(documents))]


class FakeGenerator:
    model_version = "test/cloud-structured-v1"

    def __init__(self):
        self.inputs = []

    def complete_json(self, system_prompt, input_payload):
        self.inputs.append(input_payload)
        if "Planner" in system_prompt:
            return {"subquestions": [input_payload["question"]]}
        role = input_payload["role"]
        claim_type = {
            "Classicist": "DIRECT_TEXT",
            "HistoricalScholar": "HISTORICAL_FACT",
            "Theorist": "THEORETICAL_INFERENCE",
        }[role]
        return {"claims": [{
            "client_ref": "c1", "claim_type": claim_type,
            "assertion_text": f"{role} sample finding",
            "rationale_summary": "Cites the visible source text.",
            "evidence_revision_ids": [input_payload["evidence"][0]["evidence_revision_id"]],
        }]}


def test_first_round_freezes_context_and_rejects_unseen_evidence_atomically():
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime.active_knowledge_version_id is None:
            pytest.skip("no published sample knowledge version")
        item = session.scalar(select(KnowledgeVersionItem).where(
            KnowledgeVersionItem.knowledge_version_id == runtime.active_knowledge_version_id,
            KnowledgeVersionItem.evidence_revision_id.is_not(None),
        ))
        build = session.get(IndexBuild, runtime.active_index_build_id)
        vector = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build.id
        ))
        embedder = FakeEmbedder(build.configuration["embedding_model"], vector.dimensions)
        reranker = (FakeReranker(build.configuration["rerank_model"])
                    if build.configuration.get("rerank_model") else None)
    provenance = trace_evidence(item.evidence_revision_id)
    model = FakeGenerator()
    task_id = create_research_task(
        provenance["quote_text"], source_ids=[UUID(provenance["source_id"])]
    )
    fingerprint = start_research_task(task_id, model_version=model.model_version)
    with pytest.raises(ValueError, match="CREATED"):
        start_research_task(task_id, model_version=model.model_version)
    execute_planner(task_id, model=model)
    assert retrieve_for_task(task_id, embedder=embedder, reranker=reranker, limit=5) >= 1
    run_ids = prepare_first_round(task_id)
    assert len(run_ids) == 3
    with SessionLocal() as session:
        runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id == task_id)))
        assert all(run.input_snapshot["run_fingerprint"] == fingerprint for run in runs)
        assert all("claims" not in run.input_snapshot for run in runs)
        pool = list(session.scalars(select(TaskEvidenceRef).where(TaskEvidenceRef.task_id == task_id)))
        assert pool
    classicist = next(run for run in runs if run.role == "Classicist")
    valid_id = str(pool[0].evidence_revision_id)
    bad_payload = {"claims": [
        {"client_ref": "valid", "claim_type": "DIRECT_TEXT", "assertion_text": "visible",
         "rationale_summary": "source", "evidence_revision_ids": [valid_id]},
        {"client_ref": "invalid", "claim_type": "DIRECT_TEXT", "assertion_text": "unseen",
         "rationale_summary": "source", "evidence_revision_ids": [str(uuid4())]},
    ]}
    with pytest.raises(ValueError, match="outside visible"):
        submit_first_round_output(classicist.id, bad_payload)
    with SessionLocal() as session:
        assert not list(session.scalars(select(Claim).where(Claim.task_id == task_id)))
    historical_run = next(run for run in runs if run.role == "HistoricalScholar")
    history_fields = (
        "source_author", "source_era", "source_school", "source_edition",
        "source_publication_year",
    )
    has_history = any(provenance.get(field) for field in history_fields)
    if not has_history:
        with pytest.raises(ValueError, match="explicit source history metadata"):
            submit_first_round_output(historical_run.id, {
                "claims": [{
                    "client_ref": "h1", "claim_type": "HISTORICAL_FACT",
                    "assertion_text": "unsupported history", "rationale_summary": "no metadata",
                    "evidence_revision_ids": [valid_id],
                }]
            })
    other_run = next(run for run in runs if run.role == "Theorist")
    assert "claims" not in agent_visible_context(other_run.id)
    claim_ids = execute_first_round(task_id, model=model)
    expected_claims = 3 if has_history else 2
    assert len(claim_ids) == expected_claims
    assert all("claims" not in payload for payload in model.inputs)
    with SessionLocal() as session:
        claims = list(session.scalars(select(Claim).where(Claim.task_id == task_id)))
        assert len(claims) == expected_claims
        assert len(list(session.scalars(select(ClaimEvidence).where(
            ClaimEvidence.claim_id.in_(claim_ids)
        )))) == expected_claims
