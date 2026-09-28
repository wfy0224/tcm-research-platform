from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.audit_service import mechanical_audit_claim, semantic_audit_claim
from tcm_platform.claim_normalization import normalize_task_claims
from tcm_platform.db import SessionLocal, engine
from tcm_platform.debate_service import (
    audit_revised_claims,
    execute_critic,
    execute_rebuttal,
    prepare_critic_round,
    prepare_rebuttal_round,
    retrieve_evidence_requests,
    submit_critic_output,
    submit_rebuttal_output,
)
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.models import (
    AgentRun,
    AuditResult,
    CanonicalClaim,
    CanonicalClaimMember,
    Claim,
    ClaimEvidence,
    Critique,
    Dispute,
    EmbeddingRecord,
    EventLog,
    EvidenceGap,
    EvidenceRequest,
    EvidenceRetrievalEvent,
    HumanReviewRequest,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersionItem,
    ModelInvocation,
    Rebuttal,
    ResearchSubquestion,
    ResearchSynthesis,
    ResearchTask,
    StopEvaluation,
    StructuredReport,
    TaskCheckpoint,
    TaskEvidenceRef,
    TaskJob,
    utc_now,
)
from tcm_platform.research_runtime import execute_first_round, execute_planner
from tcm_platform.research_service import (
    add_task_evidence,
    agent_visible_context,
    cancel_research_task,
    create_research_task,
    prepare_first_round,
    request_research_pause,
    resume_research_task,
    retrieve_for_task,
    start_research_task,
    submit_first_round_output,
)
from tcm_platform.research_worker import run_next_research_job
from tcm_platform.stop_service import WorkflowConfig, evaluate_snapshot, resolve_human_review


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
        if "证据审计员" in system_prompt:
            return {"verdict": "SUPPORTED", "rationale_summary": "原文支持断言",
                    "cited_evidence_revision_ids": [
                        input_payload["evidence"][0]["evidence_revision_id"]]}
        if "Critic" in system_prompt:
            return {"critiques": []}
        if "Judge" in system_prompt:
            return {"findings": [{"claim_id": claim["claim_id"],
                                  "category": claim["allowed_category"],
                                  "reason_id": claim["allowed_reason_ids"][0]}
                                 for claim in input_payload["claims"]]}
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


class DebateGenerator(FakeGenerator):
    def complete_json(self, system_prompt, input_payload):
        if "证据审计员" in system_prompt:
            verdict = ("NOT_VERIFIABLE" if input_payload["assertion_text"].startswith("修订：")
                       else "SUPPORTED")
            return {"verdict": verdict, "rationale_summary": "按可见原文审计",
                    "cited_evidence_revision_ids": [
                        input_payload["evidence"][0]["evidence_revision_id"]]}
        if "Critic" in system_prompt:
            return {"critiques": [{
                "client_ref": "c1", "target_claim_id": input_payload["claims"][0]["claim_id"],
                "issue_type": "OVERCLAIM", "rationale_summary": "需限定断言",
                "evidence_request_query": "太阳病脉象",
            }]}
        if "研究反驳 Agent" in system_prompt:
            critique = input_payload["critiques"][0]
            evidence_id = input_payload["evidence"][0]["evidence_revision_id"]
            return {"rebuttals": [{
                "critique_id": critique["critique_id"], "action": "REVISE",
                "rationale_summary": "接受限定意见", "evidence_revision_ids": [evidence_id],
                "revised_claim": {
                    "claim_type": critique["claim_type"],
                    "assertion_text": "修订：只保留可见原文所述内容",
                    "rationale_summary": "删去不能验证的部分",
                },
            }]}
        return super().complete_json(system_prompt, input_payload)


def new_worker_task(workflow_config=None):
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime.active_knowledge_version_id is None:
            pytest.skip("no published sample knowledge version")
        build = session.get(IndexBuild, runtime.active_index_build_id)
        vector = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build.id
        ))
        item = session.scalar(select(KnowledgeVersionItem).where(
            KnowledgeVersionItem.knowledge_version_id == build.knowledge_version_id,
            KnowledgeVersionItem.evidence_revision_id.is_not(None),
        ))
        embedder = FakeEmbedder(build.configuration["embedding_model"], vector.dimensions)
        reranker = (FakeReranker(build.configuration["rerank_model"])
                    if build.configuration.get("rerank_model") else None)
    provenance = trace_evidence(item.evidence_revision_id)
    task_id = create_research_task(
        provenance["quote_text"], source_ids=[UUID(provenance["source_id"])]
    )
    start_research_task(task_id, model_version=FakeGenerator.model_version,
                        workflow_config=workflow_config)
    return task_id, embedder, reranker


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
        invocations = list(session.scalars(select(ModelInvocation).where(
            ModelInvocation.task_id == task_id
        )))
        assert len(invocations) == 1 + expected_claims
        assert {item.purpose for item in invocations} == (
            {"Planner", "Classicist", "Theorist"} |
            ({"HistoricalScholar"} if has_history else set())
        )
        assert all(item.status == "COMPLETED" and len(item.request_hash) == 64
                   and item.output_hash and item.latency_ms >= 0 for item in invocations)
    job_id = run_next_research_job(
        worker_id="test-reconciler", model=model, embedder=embedder,
        reranker=reranker, task_id=task_id,
    )
    assert job_id is not None


def test_research_worker_resumes_from_frozen_task_and_checkpoints():
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime.active_knowledge_version_id is None:
            pytest.skip("no published sample knowledge version")
        build = session.get(IndexBuild, runtime.active_index_build_id)
        vector = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build.id
        ))
        item = session.scalar(select(KnowledgeVersionItem).where(
            KnowledgeVersionItem.knowledge_version_id == build.knowledge_version_id,
            KnowledgeVersionItem.evidence_revision_id.is_not(None),
        ))
        embedder = FakeEmbedder(build.configuration["embedding_model"], vector.dimensions)
        reranker = (FakeReranker(build.configuration["rerank_model"])
                    if build.configuration.get("rerank_model") else None)
    provenance = trace_evidence(item.evidence_revision_id)
    task_id = create_research_task(
        provenance["quote_text"], source_ids=[UUID(provenance["source_id"])]
    )
    model = FakeGenerator()
    start_research_task(task_id, model_version=model.model_version)
    execute_planner(task_id, model=model)
    retrieve_for_task(task_id, embedder=embedder, reranker=reranker)
    prepare_first_round(task_id)
    execute_first_round(task_id, model=model)
    with SessionLocal() as session:
        job_id = session.scalar(select(TaskJob.id).where(
            TaskJob.idempotency_key == f"research:{task_id}:run:v1"
        ))
    assert job_id is not None
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.get(TaskJob, job_id)
        checkpoint = session.scalar(select(TaskCheckpoint).where(
            TaskCheckpoint.job_id == job_id
        ))
        assert task.status == "FIRST_ROUND_COMPLETE"
        assert job.status == "PENDING"
        assert checkpoint is None
        claims = list(session.scalars(select(Claim).where(Claim.task_id == task_id)))
        assert len(claims) >= 2
        audited_claim_id = claims[0].id
        unaudited_claim_id = claims[1].id
    first_audit = mechanical_audit_claim(audited_claim_id)
    second_audit = mechanical_audit_claim(audited_claim_id)
    assert first_audit["verdict"] == second_audit["verdict"] == "PASS"
    with SessionLocal() as session:
        history = list(session.scalars(select(AuditResult).where(
            AuditResult.claim_id == audited_claim_id
        ).order_by(AuditResult.sequence_no)))
        assert [item.sequence_no for item in history] == [1, 2]
        assert session.get(Claim, audited_claim_id).audit_status == "PENDING_SEMANTIC"
        evidence_id = history[-1].evidence_revision_ids[0]

    class FakeAuditor:
        model_version = FakeGenerator.model_version

        def __init__(self, cited_id):
            self.cited_id = cited_id

        def complete_json(self, system_prompt, input_payload):
            assert "证据审计员" in system_prompt
            assert input_payload["claim_id"] == str(audited_claim_id)
            return {"verdict": "SUPPORTED", "rationale_summary": "原文可支持断言",
                    "cited_evidence_revision_ids": [self.cited_id]}

    with pytest.raises(ValueError, match="outside the audited Claim"):
        semantic_audit_claim(audited_claim_id, model=FakeAuditor(str(uuid4())))
    with SessionLocal() as session:
        assert session.get(Claim, audited_claim_id).audit_status == "PENDING_SEMANTIC"
        assert session.scalar(select(AuditResult.id).where(
            AuditResult.claim_id == audited_claim_id,
            AuditResult.stage == "SEMANTIC",
        )) is None
    result = semantic_audit_claim(audited_claim_id, model=FakeAuditor(evidence_id))
    assert result["verdict"] == "SUPPORTED"
    with SessionLocal() as session:
        assert session.get(Claim, audited_claim_id).audit_status == "SUPPORTED"
        assert len(list(session.scalars(select(AuditResult).where(
            AuditResult.claim_id == audited_claim_id
        )))) == 3
    critic_run_id = prepare_critic_round(task_id)
    invalid_critique = {"critiques": [
        {"client_ref": "valid", "target_claim_id": str(audited_claim_id),
         "issue_type": "EVIDENCE_GAP", "rationale_summary": "需补证",
         "evidence_request_query": "太阳病脉象"},
        {"client_ref": "invalid", "target_claim_id": str(unaudited_claim_id),
         "issue_type": "EVIDENCE_GAP", "rationale_summary": "越界",
         "evidence_request_query": None},
    ]}
    with pytest.raises(ValueError, match="outside its visible task"):
        submit_critic_output(critic_run_id, invalid_critique)
    with SessionLocal() as session:
        assert not list(session.scalars(select(Critique).where(Critique.task_id == task_id)))

    class FakeCritic:
        model_version = FakeGenerator.model_version

        def complete_json(self, system_prompt, input_payload):
            assert "Critic" in system_prompt
            assert [item["claim_id"] for item in input_payload["claims"]] == [str(audited_claim_id)]
            assert input_payload["claims"][0]["audit_status"] == "SUPPORTED"
            return {"critiques": [
                {"client_ref": "c1", "target_claim_id": str(audited_claim_id),
                 "issue_type": "EVIDENCE_GAP", "rationale_summary": "需核对更多原文",
                 "evidence_request_query": "太阳病脉象"},
                {"client_ref": "c2", "target_claim_id": str(audited_claim_id),
                 "issue_type": "OVERCLAIM", "rationale_summary": "可能过度推断",
                 "evidence_request_query": None},
                {"client_ref": "c3", "target_claim_id": str(audited_claim_id),
                 "issue_type": "HISTORICAL_SCOPE", "rationale_summary": "时代边界待限定",
                 "evidence_request_query": None},
                {"client_ref": "c4", "target_claim_id": str(audited_claim_id),
                 "issue_type": "TEXTUAL_MISREAD", "rationale_summary": "原文可能误读",
                 "evidence_request_query": None},
            ]}

    critique_ids = execute_critic(critic_run_id, model=FakeCritic())
    assert len(critique_ids) == 4
    with SessionLocal() as session:
        request_id = session.scalar(select(EvidenceRequest.id).where(
            EvidenceRequest.critique_id == critique_ids[0]
        ))
        query = session.get(EvidenceRequest, request_id).query_text
    with pytest.raises(ValueError, match="EvidenceRequests must resolve"):
        prepare_rebuttal_round(task_id)
    with pytest.raises(ValueError, match="outside the frozen task scope"):
        add_task_evidence(task_id, query, [{"evidence_revision_id": str(uuid4())}],
                          evidence_request_id=request_id)
    with SessionLocal() as session:
        assert session.get(EvidenceRequest, request_id).status == "PENDING"
        assert not list(session.scalars(select(EvidenceRetrievalEvent).where(
            EvidenceRetrievalEvent.evidence_request_id == request_id
        )))
    assert retrieve_evidence_requests(
        task_id, embedder=embedder, reranker=reranker, limit=1,
    ) >= 0
    with SessionLocal() as session:
        resolved_events = list(session.scalars(select(EventLog).where(
            EventLog.event_type == "evidence_request.resolved",
            EventLog.aggregate_id == str(request_id),
        )))
        assert len(resolved_events) == 1
    assert retrieve_evidence_requests(
        task_id, embedder=embedder, reranker=reranker, limit=1,
    ) == 0
    with SessionLocal() as session:
        assert len(list(session.scalars(select(EventLog).where(
            EventLog.event_type == "evidence_request.resolved",
            EventLog.aggregate_id == str(request_id),
        )))) == 1
        request = session.scalar(select(EvidenceRequest).where(
            EvidenceRequest.critique_id == critique_ids[0]
        ))
        assert request.status in {"RETRIEVED", "NO_RESULT"}
        events = list(session.scalars(select(EvidenceRetrievalEvent).where(
            EvidenceRetrievalEvent.evidence_request_id == request.id
        )))
        assert len(events) == request.result_count

    rebuttal_run_id = prepare_rebuttal_round(task_id)
    assert prepare_rebuttal_round(task_id) == rebuttal_run_id
    with SessionLocal() as session:
        original = session.get(Claim, audited_claim_id)
        original_text = original.assertion_text
        original_audit = original.audit_status
        original_claim_type = original.claim_type
        rebuttal_run = session.get(AgentRun, rebuttal_run_id)
        assert str(critique_ids[0]) == rebuttal_run.input_snapshot["critiques"][0]["critique_id"]
        assert evidence_id in rebuttal_run.visible_evidence_ids

    def revision_payload(evidence_ids):
        return {"rebuttals": [
            {"critique_id": str(critique_ids[0]), "action": "REVISE",
             "rationale_summary": "接受需要限定的质疑并修订断言",
             "evidence_revision_ids": evidence_ids,
             "revised_claim": {
                 "claim_type": original_claim_type, "assertion_text": "只陈述证据所见原文",
                 "rationale_summary": "删除原断言中无法核验的解释",
             }},
            {"critique_id": str(critique_ids[1]), "action": "ACCEPT",
             "rationale_summary": "接受该质疑", "evidence_revision_ids": [],
             "revised_claim": None},
            {"critique_id": str(critique_ids[2]), "action": "PARTIAL_ACCEPT",
             "rationale_summary": "接受部分时代边界意见", "evidence_revision_ids": [],
             "revised_claim": None},
            {"critique_id": str(critique_ids[3]), "action": "REJECT",
             "rationale_summary": "原文可反驳误读质疑",
             "evidence_revision_ids": [evidence_id], "revised_claim": None},
        ]}

    with pytest.raises(ValueError, match="outside visible"):
        submit_rebuttal_output(rebuttal_run_id, revision_payload([str(uuid4())]))
    cross_task_payload = revision_payload([evidence_id])
    cross_task_payload["rebuttals"][1]["critique_id"] = str(uuid4())
    with pytest.raises(ValueError, match="exactly once"):
        submit_rebuttal_output(rebuttal_run_id, cross_task_payload)
    with pytest.raises(ValueError, match="exactly once"):
        submit_rebuttal_output(rebuttal_run_id, {"rebuttals": []})
    with SessionLocal() as session:
        assert session.scalar(select(Rebuttal.id).where(Rebuttal.task_id == task_id)) is None
        assert session.scalar(select(Claim.id).where(
            Claim.parent_claim_id == audited_claim_id
        )) is None
        assert session.get(AgentRun, rebuttal_run_id).status == "PENDING"
    with SessionLocal.begin() as session:
        session.get(Claim, audited_claim_id).assertion_text = "冻结后被修改的断言"
    with pytest.raises(ValueError, match="target changed after input freeze"):
        submit_rebuttal_output(rebuttal_run_id, revision_payload([evidence_id]))
    with SessionLocal.begin() as session:
        session.get(Claim, audited_claim_id).assertion_text = original_text

    class FakeRebuttal:
        model_version = FakeGenerator.model_version

        def complete_json(self, system_prompt, input_payload):
            assert "研究反驳 Agent" in system_prompt
            assert input_payload["critiques"][0]["target_claim_id"] == str(audited_claim_id)
            return revision_payload([evidence_id])

    rebuttal_ids = execute_rebuttal(rebuttal_run_id, model=FakeRebuttal())
    assert len(rebuttal_ids) == 4
    assert submit_rebuttal_output(rebuttal_run_id, revision_payload([evidence_id])) == rebuttal_ids
    with SessionLocal() as session:
        assert len(list(session.scalars(select(Rebuttal).where(
            Rebuttal.task_id == task_id
        )))) == 4
        assert len(list(session.scalars(select(Claim).where(
            Claim.parent_claim_id == audited_claim_id
        )))) == 1
        rebuttal = session.get(Rebuttal, rebuttal_ids[0])
        revised = session.get(Claim, rebuttal.revised_claim_id)
        original = session.get(Claim, audited_claim_id)
        assert rebuttal.critique_id == critique_ids[0] and rebuttal.action == "REVISE"
        assert [session.get(Rebuttal, value).action for value in rebuttal_ids] == [
            "REVISE", "ACCEPT", "PARTIAL_ACCEPT", "REJECT",
        ]
        assert revised.parent_claim_id == original.id
        assert revised.agent_run_id == rebuttal_run_id
        assert revised.agent_role == original.agent_role
        assert revised.audit_status == "PENDING"
        assert original.assertion_text == original_text and original.audit_status == original_audit
        revised_id = revised.id

    class FakeRevisionAuditor:
        model_version = FakeGenerator.model_version

        def complete_json(self, system_prompt, input_payload):
            assert input_payload["claim_id"] == str(revised_id)
            return {"verdict": "NOT_VERIFIABLE",
                    "rationale_summary": "原文不足以确认修订断言，也不能据此判假",
                    "cited_evidence_revision_ids": [evidence_id]}

    class FakeInvalidRevisionAuditor:
        model_version = FakeGenerator.model_version

        def complete_json(self, system_prompt, input_payload):
            return {"verdict": "SUPPORTED", "rationale_summary": "引用池外证据",
                    "cited_evidence_revision_ids": [str(uuid4())]}

    with pytest.raises(ValueError, match="outside the audited Claim"):
        audit_revised_claims(task_id, model=FakeInvalidRevisionAuditor())
    with SessionLocal() as session:
        assert session.get(Claim, revised_id).audit_status == "PENDING_SEMANTIC"
        history = list(session.scalars(select(AuditResult).where(
            AuditResult.claim_id == revised_id
        )))
        assert len(history) == 1 and history[0].stage == "MECHANICAL"

    audit_results = audit_revised_claims(task_id, model=FakeRevisionAuditor())
    assert audit_results[0]["claim_id"] == str(revised_id)
    assert audit_results[0]["verdict"] == "NOT_VERIFIABLE"
    assert audit_revised_claims(task_id, model=FakeRevisionAuditor()) == []
    with SessionLocal() as session:
        history = list(session.scalars(select(AuditResult).where(
            AuditResult.claim_id == revised_id
        ).order_by(AuditResult.sequence_no)))
        assert [(item.stage, item.verdict) for item in history] == [
            ("MECHANICAL", "PASS"), ("SEMANTIC", "NOT_VERIFIABLE"),
        ]
        assert session.get(Claim, revised_id).audit_status == "NOT_VERIFIABLE"
        assert session.get(Claim, audited_claim_id).assertion_text == original_text
    assert run_next_research_job(
        worker_id="test-research-worker", model=model, embedder=embedder,
        reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        assert session.get(TaskJob, job_id).status == "COMPLETED"


def test_research_pause_discarded_planner_output_and_resume():
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime.active_knowledge_version_id is None:
            pytest.skip("no published sample knowledge version")
        build = session.get(IndexBuild, runtime.active_index_build_id)
        vector = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build.id
        ))
        embedder = FakeEmbedder(build.configuration["embedding_model"], vector.dimensions)
        reranker = (FakeReranker(build.configuration["rerank_model"])
                    if build.configuration.get("rerank_model") else None)
    task_id = create_research_task("太阳病脉象")
    normal_model = FakeGenerator()
    start_research_task(task_id, model_version=normal_model.model_version)
    assert request_research_pause(task_id) == "PAUSED"
    with SessionLocal() as session:
        job = session.scalar(select(TaskJob).where(
            TaskJob.idempotency_key == f"research:{task_id}:run:v1"
        ))
        assert job.status == "PAUSED"
    assert resume_research_task(task_id) == "PLANNING"

    class PausingGenerator(FakeGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Planner" in system_prompt:
                assert request_research_pause(task_id) == "PAUSE_REQUESTED"
            return super().complete_json(system_prompt, input_payload)

    job_id = run_next_research_job(
        worker_id="test-pause-worker", model=PausingGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.get(TaskJob, job_id)
        checkpoints = list(session.scalars(select(TaskCheckpoint).where(
            TaskCheckpoint.job_id == job_id
        )))
        assert task.control_state == "PAUSED" and task.status == "PLANNING"
        assert job.status == "PAUSED" and job.attempts == 0
        assert checkpoints[0].result["phase"] == "PLANNING"
        assert not list(session.scalars(select(ResearchSubquestion).where(
            ResearchSubquestion.task_id == task_id
        )))
    assert resume_research_task(task_id) == "PLANNING"
    assert run_next_research_job(
        worker_id="test-pause-worker", model=normal_model,
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        assert session.get(TaskJob, job_id).status == "COMPLETED"


def test_research_cancel_before_worker_claims_job():
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime.active_knowledge_version_id is None:
            pytest.skip("no published sample knowledge version")
    task_id = create_research_task("太阳病脉象")
    start_research_task(task_id, model_version=FakeGenerator.model_version)
    assert cancel_research_task(task_id) == "CANCELLED"
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.scalar(select(TaskJob).where(
            TaskJob.idempotency_key == f"research:{task_id}:run:v1"
        ))
        assert task.status == "CANCELLED" and task.control_state == "CANCELLED"
        assert job.status == "CANCELLED"


def test_research_cancel_during_planner_discards_returned_output():
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime.active_knowledge_version_id is None:
            pytest.skip("no published sample knowledge version")
        build = session.get(IndexBuild, runtime.active_index_build_id)
        vector = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build.id
        ))
        embedder = FakeEmbedder(build.configuration["embedding_model"], vector.dimensions)
        reranker = (FakeReranker(build.configuration["rerank_model"])
                    if build.configuration.get("rerank_model") else None)
    task_id = create_research_task("太阳病脉象")
    start_research_task(task_id, model_version=FakeGenerator.model_version)

    class CancellingGenerator(FakeGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Planner" in system_prompt:
                assert cancel_research_task(task_id) == "CANCEL_REQUESTED"
            return super().complete_json(system_prompt, input_payload)

    job_id = run_next_research_job(
        worker_id="test-cancel-worker", model=CancellingGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        assert task.status == "CANCELLED" and task.control_state == "CANCELLED"
        assert session.get(TaskJob, job_id).status == "CANCELLED"
        assert not list(session.scalars(select(ResearchSubquestion).where(
            ResearchSubquestion.task_id == task_id
        )))


def test_worker_completes_audited_debate_without_manual_cli_steps():
    task_id, embedder, reranker = new_worker_task()
    job_id = run_next_research_job(
        worker_id="test-debate-worker", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.get(TaskJob, job_id)
        assert task.status == "COMPLETED"
        assert job.status == "COMPLETED" and job.attempts == 1
        runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id == task_id)))
        assert sum(run.round_no == 1 for run in runs) == 3
        assert {run.role for run in runs if run.round_no == 2} == {"Critic", "Rebuttal"}
        critiques = list(session.scalars(select(Critique).where(Critique.task_id == task_id)))
        rebuttals = list(session.scalars(select(Rebuttal).where(Rebuttal.task_id == task_id)))
        assert len(critiques) == len(rebuttals) == 1
        assert critiques[0].status == "RESPONDED"
        assert rebuttals[0].critique_id == critiques[0].id
        revised = session.get(Claim, rebuttals[0].revised_claim_id)
        original = session.get(Claim, revised.parent_claim_id)
        assert original.assertion_text != revised.assertion_text
        assert original.audit_status == "SUPPORTED"
        assert revised.audit_status == "NOT_VERIFIABLE"
        members = list(session.scalars(select(CanonicalClaimMember).join(
            Claim, Claim.id == CanonicalClaimMember.claim_id
        ).where(Claim.task_id == task_id)))
        assert len(members) == len(list(session.scalars(select(Claim).where(
            Claim.task_id == task_id
        ))))
        member_by_claim = {item.claim_id: item for item in members}
        assert member_by_claim[original.id].canonical_claim_id != (
            member_by_claim[revised.id].canonical_claim_id
        )
        assert session.get(CanonicalClaim, member_by_claim[original.id].canonical_claim_id)
        assert session.scalar(select(EvidenceGap.id).where(
            EvidenceGap.task_id == task_id, EvidenceGap.claim_id == revised.id,
            EvidenceGap.reason_code == "NOT_VERIFIABLE",
        )) is not None
        audits = list(session.scalars(select(AuditResult).where(
            AuditResult.claim_id == revised.id
        ).order_by(AuditResult.sequence_no)))
        assert [(item.stage, item.verdict) for item in audits] == [
            ("MECHANICAL", "PASS"), ("SEMANTIC", "NOT_VERIFIABLE"),
        ]
        request = session.scalar(select(EvidenceRequest).where(
            EvidenceRequest.task_id == task_id
        ))
        assert request.status in {"RETRIEVED", "NO_RESULT"}
        events = list(session.scalars(select(EvidenceRetrievalEvent).where(
            EvidenceRetrievalEvent.evidence_request_id == request.id
        )))
        assert len(events) == request.result_count
        checkpoints = list(session.scalars(select(TaskCheckpoint).where(
            TaskCheckpoint.job_id == job_id
        )))
        phases = {item.result.get("phase") for item in checkpoints}
        assert {"FIRST_ROUND_MECHANICAL_AUDIT", "FIRST_ROUND_SEMANTIC_AUDIT",
                "CRITIC_PREPARED", "CRITIC_SUBMITTED", "EVIDENCE_REQUEST_RESOLVED",
                "REBUTTAL_PREPARED", "REBUTTAL_SUBMITTED", "REVISED_CLAIM_AUDITED"} <= phases
        assert any(item.result.get("status") == "DEBATE_ROUND_COMPLETE"
                   for item in checkpoints)
    assert run_next_research_job(
        worker_id="test-debate-worker", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) is None


def test_claim_normalization_preserves_conflict_and_replays_without_duplicates():
    class ConflictGenerator(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "证据审计员" in system_prompt:
                assertion = input_payload["assertion_text"]
                verdict = ("CONTRADICTED" if assertion.startswith("Classicist")
                           else "NOT_VERIFIABLE" if assertion.startswith("Theorist")
                           else "SUPPORTED")
                return {"verdict": verdict, "rationale_summary": "按原文审计",
                        "cited_evidence_revision_ids": [
                            input_payload["evidence"][0]["evidence_revision_id"]]}
            if "Critic" in system_prompt:
                return {"critiques": [{
                    "client_ref": "c1", "target_claim_id": input_payload["claims"][0]["claim_id"],
                    "issue_type": "CONTRADICTION", "rationale_summary": "存在相反解释",
                    "evidence_request_query": None,
                }]}
            return super().complete_json(system_prompt, input_payload)

    task_id, embedder, reranker = new_worker_task()
    run_next_research_job(worker_id="test-conflict-normalizer", model=ConflictGenerator(),
                          embedder=embedder, reranker=reranker, task_id=task_id)
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        disputes = list(session.scalars(select(Dispute).where(Dispute.task_id == task_id)))
        assert {item.reason_code for item in disputes} == {
            "AUDIT_CONTRADICTION", "CRITIQUE_CONTRADICTION",
        }
        assert any(item.opposing_evidence_ids for item in disputes)
        assert any(item.supporting_evidence_ids == [] for item in disputes)
        gaps = list(session.scalars(select(EvidenceGap).where(
            EvidenceGap.task_id == task_id
        )))
        assert any(item.reason_code == "NOT_VERIFIABLE" for item in gaps)
        assert any(item.reason_code == "SUPPORTING_EVIDENCE_UNVERIFIED" for item in gaps)
        report = session.scalar(select(StructuredReport).where(
            StructuredReport.task_id == task_id))
        assert report.content["counts"]["DISPUTED"] >= 1
        assert report.content["counts"]["UNRESOLVED"] >= 1
        assert report.content["open_disputes"]
        assert report.content["unresolved_gaps"]
        counts = (len(list(session.scalars(select(CanonicalClaim).where(
            CanonicalClaim.task_id == task_id
        )))), len(disputes), len(gaps))
    assert normalize_task_claims(task_id) == {
        "canonical_claims": 0, "members": 0, "disputes": 0, "gaps": 0,
        "superseded": 0,
    }
    with SessionLocal() as session:
        assert counts == (
            len(list(session.scalars(select(CanonicalClaim).where(
                CanonicalClaim.task_id == task_id
            )))),
            len(list(session.scalars(select(Dispute).where(Dispute.task_id == task_id)))),
            len(list(session.scalars(select(EvidenceGap).where(EvidenceGap.task_id == task_id)))),
        )
    with SessionLocal.begin() as session:
        critique = session.scalar(select(Critique).where(Critique.task_id == task_id))
        target = session.get(Claim, critique.target_claim_id)
        prior = session.scalar(select(AuditResult).where(
            AuditResult.claim_id == target.id
        ).order_by(AuditResult.sequence_no.desc()).limit(1))
        assert prior.verdict == "CONTRADICTED"
        session.add(AuditResult(
            id=uuid4(), task_id=task_id, claim_id=target.id,
            sequence_no=prior.sequence_no + 1, stage="SEMANTIC",
            verdict="SUPPORTED", rationale_summary="复核后有支持",
            evidence_revision_ids=prior.evidence_revision_ids,
            model_version=prior.model_version,
        ))
        target.audit_status = "SUPPORTED"
    replay = normalize_task_claims(task_id)
    assert replay["canonical_claims"] == replay["members"] == 0
    assert replay["disputes"] == replay["gaps"] == 1
    assert replay["superseded"] >= 2
    with SessionLocal() as session:
        assert session.scalar(select(Dispute.id).where(
            Dispute.task_id == task_id,
            Dispute.reason_code == "AUDIT_CONTRADICTION",
            Dispute.status == "OPEN",
        )) is None
        assert session.scalar(select(Dispute.id).where(
            Dispute.task_id == task_id,
            Dispute.reason_code == "CRITIQUE_CONTRADICTION",
            Dispute.status == "OPEN",
        )) is not None


def test_canonical_claim_groups_duplicate_assertions_without_removing_claims():
    class DuplicateGenerator(FakeGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Critic" in system_prompt:
                return {"critiques": []}
            if input_payload.get("role") == "Classicist":
                evidence_id = input_payload["evidence"][0]["evidence_revision_id"]
                return {"claims": [{
                    "client_ref": ref, "claim_type": "DIRECT_TEXT",
                    "assertion_text": "同一原文断言", "rationale_summary": "同一证据",
                    "evidence_revision_ids": [evidence_id],
                } for ref in ("first", "second")]}
            return super().complete_json(system_prompt, input_payload)

    task_id, embedder, reranker = new_worker_task()
    run_next_research_job(worker_id="test-duplicate-normalizer", model=DuplicateGenerator(),
                          embedder=embedder, reranker=reranker, task_id=task_id)
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        claims = list(session.scalars(select(Claim).where(
            Claim.task_id == task_id, Claim.assertion_text == "同一原文断言"
        )))
        assert len(claims) == 2
        members = list(session.scalars(select(CanonicalClaimMember).where(
            CanonicalClaimMember.claim_id.in_([item.id for item in claims])
        )))
        assert len(members) == 2
        assert members[0].canonical_claim_id == members[1].canonical_claim_id


def test_worker_retries_invalid_critic_output_without_partial_debate():
    task_id, embedder, reranker = new_worker_task()

    class InvalidCritic(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Critic" in system_prompt:
                payload = super().complete_json(system_prompt, input_payload)
                payload["critiques"].append({
                    "client_ref": "bad", "target_claim_id": str(uuid4()),
                    "issue_type": "OVERCLAIM", "rationale_summary": "池外 Claim",
                    "evidence_request_query": None,
                })
                return payload
            return super().complete_json(system_prompt, input_payload)

    job_id = run_next_research_job(
        worker_id="test-invalid-critic", model=InvalidCritic(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal.begin() as session:
        job = session.get(TaskJob, job_id)
        assert job.status == "RETRY_WAIT"
        assert session.scalar(select(Critique.id).where(Critique.task_id == task_id)) is None
        checkpoints = list(session.scalars(select(TaskCheckpoint).where(
            TaskCheckpoint.job_id == job_id
        )))
        assert all(item.result.get("phase") != "CRITIC_SUBMITTED" for item in checkpoints)
        job.available_at = utc_now()
    assert run_next_research_job(
        worker_id="test-invalid-critic", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(TaskJob, job_id).status == "COMPLETED"
        assert session.get(TaskJob, job_id).attempts == 2
        assert len(list(session.scalars(select(Critique).where(Critique.task_id == task_id)))) == 1
        assert len(list(session.scalars(select(Claim).where(
            Claim.task_id == task_id, Claim.parent_claim_id.is_not(None)
        )))) == 1


def test_worker_resumes_revised_claim_semantic_audit_without_duplicate_revision():
    task_id, embedder, reranker = new_worker_task()

    class InvalidRevisionAudit(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if ("证据审计员" in system_prompt
                    and input_payload["assertion_text"].startswith("修订：")):
                return {"verdict": "SUPPORTED", "rationale_summary": "非法池外引用",
                        "cited_evidence_revision_ids": [str(uuid4())]}
            return super().complete_json(system_prompt, input_payload)

    job_id = run_next_research_job(
        worker_id="test-revision-retry", model=InvalidRevisionAudit(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal.begin() as session:
        job = session.get(TaskJob, job_id)
        assert job.status == "RETRY_WAIT"
        revised = list(session.scalars(select(Claim).where(
            Claim.task_id == task_id, Claim.parent_claim_id.is_not(None)
        )))
        assert len(revised) == 1 and revised[0].audit_status == "PENDING_SEMANTIC"
        assert len(list(session.scalars(select(Rebuttal).where(
            Rebuttal.task_id == task_id
        )))) == 1
        job.available_at = utc_now()
        revised_id = revised[0].id
    assert run_next_research_job(
        worker_id="test-revision-retry", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(TaskJob, job_id).status == "COMPLETED"
        revised = list(session.scalars(select(Claim).where(
            Claim.task_id == task_id, Claim.parent_claim_id.is_not(None)
        )))
        assert len(revised) == 1 and revised[0].id == revised_id
        assert revised[0].audit_status == "NOT_VERIFIABLE"
        assert len(list(session.scalars(select(Rebuttal).where(
            Rebuttal.task_id == task_id
        )))) == 1
        audits = list(session.scalars(select(AuditResult).where(
            AuditResult.claim_id == revised_id
        ).order_by(AuditResult.sequence_no)))
        assert [item.stage for item in audits] == ["MECHANICAL", "SEMANTIC"]


def test_worker_pause_and_cancel_discard_debate_model_output():
    paused_id, embedder, reranker = new_worker_task()

    class PausingCritic(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Critic" in system_prompt:
                assert request_research_pause(paused_id) == "PAUSE_REQUESTED"
            return super().complete_json(system_prompt, input_payload)

    paused_job = run_next_research_job(
        worker_id="test-pause-debate", model=PausingCritic(),
        embedder=embedder, reranker=reranker, task_id=paused_id,
    )
    with SessionLocal() as session:
        assert session.get(TaskJob, paused_job).status == "PAUSED"
        assert session.scalar(select(Critique.id).where(Critique.task_id == paused_id)) is None
    assert resume_research_task(paused_id) == "DEBATING"
    assert run_next_research_job(
        worker_id="test-pause-debate", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=paused_id,
    ) == paused_job

    cancelled_id, embedder, reranker = new_worker_task()

    class CancellingRebuttal(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "研究反驳 Agent" in system_prompt:
                assert cancel_research_task(cancelled_id) == "CANCEL_REQUESTED"
            return super().complete_json(system_prompt, input_payload)

    cancelled_job = run_next_research_job(
        worker_id="test-cancel-debate", model=CancellingRebuttal(),
        embedder=embedder, reranker=reranker, task_id=cancelled_id,
    )
    with SessionLocal() as session:
        assert session.get(TaskJob, cancelled_job).status == "CANCELLED"
        assert session.get(ResearchTask, cancelled_id).status == "CANCELLED"
        assert session.scalar(select(Rebuttal.id).where(Rebuttal.task_id == cancelled_id)) is None
        assert session.scalar(select(Claim.id).where(
            Claim.task_id == cancelled_id, Claim.parent_claim_id.is_not(None)
        )) is None


def test_worker_recovers_expired_lease_after_node_checkpoints():
    task_id, embedder, reranker = new_worker_task()

    class ExpiringCritic(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Critic" in system_prompt:
                with SessionLocal.begin() as session:
                    job = session.scalar(select(TaskJob).where(
                        TaskJob.idempotency_key == f"research:{task_id}:run:v1"
                    ).with_for_update())
                    job.lease_expires_at = utc_now() - timedelta(seconds=1)
            return super().complete_json(system_prompt, input_payload)

    job_id = run_next_research_job(
        worker_id="test-expired-debate", model=ExpiringCritic(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        assert session.get(TaskJob, job_id).status == "RUNNING"
        assert session.scalar(select(Critique.id).where(Critique.task_id == task_id)) is None
        assert session.scalar(select(TaskCheckpoint.id).where(
            TaskCheckpoint.job_id == job_id
        )) is not None
    assert run_next_research_job(
        worker_id="test-expired-debate", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        job = session.get(TaskJob, job_id)
        assert job.status == "COMPLETED" and job.execution_generation == 2
        assert len(list(session.scalars(select(Critique).where(Critique.task_id == task_id)))) == 1

    changed_id, embedder, reranker = new_worker_task()

    class ChangingGenerationCritic(DebateGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Critic" in system_prompt:
                with SessionLocal.begin() as session:
                    job = session.scalar(select(TaskJob).where(
                        TaskJob.idempotency_key == f"research:{changed_id}:run:v1"
                    ).with_for_update())
                    job.execution_generation += 1
                    job.lease_expires_at = utc_now() - timedelta(seconds=1)
            return super().complete_json(system_prompt, input_payload)

    changed_job = run_next_research_job(
        worker_id="test-changed-generation", model=ChangingGenerationCritic(),
        embedder=embedder, reranker=reranker, task_id=changed_id,
    )
    with SessionLocal() as session:
        assert session.scalar(select(Critique.id).where(Critique.task_id == changed_id)) is None
        assert session.get(TaskJob, changed_job).execution_generation == 2
    assert run_next_research_job(
        worker_id="test-changed-generation", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=changed_id,
    ) == changed_job
    with SessionLocal() as session:
        assert session.get(TaskJob, changed_job).status == "COMPLETED"
        assert session.get(TaskJob, changed_job).execution_generation == 3
def test_frozen_round_limit_replays_from_persisted_evidence():
    task_id, embedder, reranker = new_worker_task(
        WorkflowConfig(min_debate_rounds=2, max_debate_rounds=2)
    )
    job_id = run_next_research_job(
        worker_id="test-multi-round", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.get(TaskJob, job_id)
        runs = list(session.scalars(select(AgentRun).where(AgentRun.task_id == task_id)))
        decisions = list(session.scalars(select(StopEvaluation).where(
            StopEvaluation.task_id == task_id).order_by(StopEvaluation.round_no)))
        assert task.status == "COMPLETED" and job.status == "COMPLETED"
        assert sum(run.round_no == 1 for run in runs) == 3
        assert {run.round_no for run in runs if run.role == "Critic"} == {2, 3}
        assert {run.round_no for run in runs if run.role == "Rebuttal"} == {2, 3}
        assert [(item.decision, item.reason_code) for item in decisions] == [
            ("CONTINUE", "MIN_ROUNDS"), ("STOP", "ROUND_LIMIT")]
        assert [(item.decision, item.reason_code) for item in decisions] == [
            evaluate_snapshot(item.input_snapshot) for item in decisions]
        assert task.execution_context["workflow_config"]["max_debate_rounds"] == 2


def test_human_review_releases_lease_and_resumes_stop_stage_only():
    task_id, embedder, reranker = new_worker_task(
        WorkflowConfig(mandatory_human_review=True)
    )
    job_id = run_next_research_job(
        worker_id="test-human-wait", model=FakeGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.get(TaskJob, job_id)
        review = session.scalar(select(HumanReviewRequest).where(
            HumanReviewRequest.task_id == task_id))
        first_runs = list(session.scalars(select(AgentRun.id).where(
            AgentRun.task_id == task_id, AgentRun.round_no == 1)))
        assert task.status == "WAITING_HUMAN"
        assert (task.interrupted_stage, task.resume_stage, task.waiting_reason_code) == (
            "STOP_EVALUATION", "STOP_EVALUATION", "MANDATORY_REVIEW")
        assert job.status == "COMPLETED" and job.lease_owner is None
        assert review.status == "PENDING"
        review_id = review.id
    assert resolve_human_review(review_id, reviewer_id="human-tester", note="审阅完成") == task_id
    with pytest.raises(ValueError, match="not pending"):
        resolve_human_review(review_id, reviewer_id="human-tester", note="duplicate")
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "STOP_EVALUATION"
        assert session.get(TaskJob, job_id).status == "PENDING"
    assert run_next_research_job(
        worker_id="test-human-resume", model=FakeGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        assert session.get(TaskJob, job_id).status == "COMPLETED"
        assert list(session.scalars(select(AgentRun.id).where(
            AgentRun.task_id == task_id, AgentRun.round_no == 1))) == first_runs
        decisions = list(session.scalars(select(StopEvaluation).where(
            StopEvaluation.task_id == task_id).order_by(StopEvaluation.created_at)))
        assert [(item.decision, item.reason_code) for item in decisions] == [
            ("WAITING_HUMAN", "MANDATORY_REVIEW"), ("STOP", "NO_CRITIQUES")]


def test_judge_report_preserves_citation_chain_and_is_database_immutable():
    task_id, embedder, reranker = new_worker_task()
    job_id = run_next_research_job(
        worker_id="test-judge-report", model=DebateGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        job = session.get(TaskJob, job_id)
        synthesis = session.scalar(select(ResearchSynthesis).where(
            ResearchSynthesis.task_id == task_id))
        report = session.scalar(select(StructuredReport).where(
            StructuredReport.task_id == task_id))
        assert task.status == job.status == "COMPLETED"
        assert report.synthesis_id == synthesis.id
        assert report.context_snapshot == task.execution_context
        assert synthesis.input_snapshot["stop_evaluation_id"] == report.content["stop_evaluation_id"]
        assert set(report.content["sections"]) == {
            "HIGH_CONFIDENCE", "CONDITIONAL", "DISPUTED", "UNSUPPORTED", "UNRESOLVED"}
        assert report.content["counts"]["HIGH_CONFIDENCE"] >= 1
        assert report.content["counts"]["UNRESOLVED"] >= 1
        findings = [row for rows in report.content["sections"].values() for row in rows]
        audited_ids = set(session.scalars(select(Claim.id).where(Claim.task_id == task_id)))
        assert {UUID(row["claim_id"]) for row in findings} == audited_ids
        for row in findings:
            assert session.get(AuditResult, UUID(row["audit_result_id"])) is not None
            for evidence in row["evidence"]:
                assert evidence["quote_text"]
                assert evidence["source_revision_id"]
                assert evidence["citation_locator"]["start"]
        report_id = report.id
        frozen_content = report.content
    with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
        session.execute(text("UPDATE research.structured_report SET content = '{}' "
                             "WHERE id = :id"), {"id": report_id})
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        runtime.active_knowledge_version_id = None
        runtime.active_index_build_id = None
        session.flush()
        assert session.get(StructuredReport, report_id).content == frozen_content
        session.rollback()


def test_invalid_judge_output_retries_without_claim_or_report_writes():
    task_id, embedder, reranker = new_worker_task()

    class InvalidJudge(FakeGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "Judge" in system_prompt:
                output = super().complete_json(system_prompt, input_payload)
                output["findings"][0]["claim_id"] = str(uuid4())
                return output
            return super().complete_json(system_prompt, input_payload)

    job_id = run_next_research_job(
        worker_id="test-invalid-judge", model=InvalidJudge(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal.begin() as session:
        job = session.get(TaskJob, job_id)
        assert job.status == "RETRY_WAIT" and "Judge must classify" in job.last_error
        assert session.get(ResearchTask, task_id).status == "JUDGING"
        assert session.scalar(select(ResearchSynthesis.id).where(
            ResearchSynthesis.task_id == task_id)) is None
        assert session.scalar(select(StructuredReport.id).where(
            StructuredReport.task_id == task_id)) is None
        first_runs = list(session.scalars(select(AgentRun.id).where(
            AgentRun.task_id == task_id, AgentRun.round_no == 1)))
        job.available_at = utc_now()
    assert run_next_research_job(
        worker_id="test-valid-judge-retry", model=FakeGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        assert session.scalar(select(StructuredReport.id).where(
            StructuredReport.task_id == task_id)) is not None
        assert list(session.scalars(select(AgentRun.id).where(
            AgentRun.task_id == task_id, AgentRun.round_no == 1))) == first_runs


def test_report_failure_does_not_complete_task_and_retry_is_idempotent(monkeypatch):
    from tcm_platform import research_worker

    task_id, embedder, reranker = new_worker_task()
    original = research_worker.persist_structured_report

    def fail_after_insert(session, report_task_id):
        original(session, report_task_id)
        raise RuntimeError("simulated report persistence failure")

    monkeypatch.setattr(research_worker, "persist_structured_report", fail_after_insert)
    job_id = run_next_research_job(
        worker_id="test-report-failure", model=FakeGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal.begin() as session:
        job = session.get(TaskJob, job_id)
        assert job.status == "RETRY_WAIT"
        assert session.get(ResearchTask, task_id).status == "REPORTING"
        assert session.scalar(select(ResearchSynthesis.id).where(
            ResearchSynthesis.task_id == task_id)) is not None
        assert session.scalar(select(StructuredReport.id).where(
            StructuredReport.task_id == task_id)) is None
        job.available_at = utc_now()
    monkeypatch.setattr(research_worker, "persist_structured_report", original)
    assert run_next_research_job(
        worker_id="test-report-retry", model=FakeGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    ) == job_id
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        assert session.get(TaskJob, job_id).status == "COMPLETED"
        assert len(list(session.scalars(select(StructuredReport).where(
            StructuredReport.task_id == task_id)))) == 1


def test_report_distinguishes_unsupported_and_conditional_claims():
    class MixedAuditGenerator(FakeGenerator):
        def complete_json(self, system_prompt, input_payload):
            if "证据审计员" in system_prompt:
                assertion = input_payload["assertion_text"]
                verdict = ("UNSUPPORTED" if assertion.startswith("Classicist") else
                           "PARTIALLY_SUPPORTED" if assertion.startswith("Theorist") else
                           "SUPPORTED")
                return {"verdict": verdict, "rationale_summary": "按原文核对",
                        "cited_evidence_revision_ids": [
                            input_payload["evidence"][0]["evidence_revision_id"]]}
            return super().complete_json(system_prompt, input_payload)

    task_id, embedder, reranker = new_worker_task()
    run_next_research_job(worker_id="test-mixed-report", model=MixedAuditGenerator(),
                          embedder=embedder, reranker=reranker, task_id=task_id)
    with SessionLocal() as session:
        report = session.scalar(select(StructuredReport).where(
            StructuredReport.task_id == task_id))
        assert report.content["counts"]["UNSUPPORTED"] == 1
        assert report.content["counts"]["CONDITIONAL"] == 1
        assert sum(report.content["counts"].values()) == 2


def test_all_agents_abstain_still_persists_an_empty_auditable_report():
    class AbstainingGenerator(FakeGenerator):
        def complete_json(self, system_prompt, input_payload):
            if input_payload.get("role"):
                return {"claims": []}
            return super().complete_json(system_prompt, input_payload)

    task_id, embedder, reranker = new_worker_task()
    job_id = run_next_research_job(
        worker_id="test-empty-report", model=AbstainingGenerator(),
        embedder=embedder, reranker=reranker, task_id=task_id,
    )
    with SessionLocal() as session:
        assert session.get(ResearchTask, task_id).status == "COMPLETED"
        assert session.get(TaskJob, job_id).status == "COMPLETED"
        report = session.scalar(select(StructuredReport).where(
            StructuredReport.task_id == task_id))
        assert sum(report.content["counts"].values()) == 0
        stop = session.get(StopEvaluation, UUID(report.content["stop_evaluation_id"]))
        assert stop.reason_code == "NO_FIRST_ROUND_CLAIMS"
