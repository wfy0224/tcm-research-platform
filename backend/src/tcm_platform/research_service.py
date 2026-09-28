"""Frozen research tasks, version-bound evidence pool and first-round claim gate."""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.enums import JobStatus, ResourceClass
from tcm_platform.ids import new_id
from tcm_platform.jobs import enqueue_job
from tcm_platform.knowledge_service import trace_evidence
from tcm_platform.models import (
    AgentRun,
    Claim,
    ClaimEvidence,
    Evidence,
    EvidenceRequest,
    EvidenceRetrievalEvent,
    EvidenceRevision,
    IndexBuild,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    KnowledgeVersionItem,
    ResearchSubquestion,
    ResearchTask,
    SourceDocument,
    SourceRevision,
    TaskEvidenceRef,
    TaskJob,
    utc_now,
)
from tcm_platform.retrieval import Embedder, Reranker, search_published

RESEARCH_ROLES = ("Classicist", "HistoricalScholar", "Theorist")
LeaseGuard = Callable[[Session], None]
CLAIM_TYPES = {
    "Classicist": {"DIRECT_TEXT", "TEXTUAL_RELATION"},
    "HistoricalScholar": {"HISTORICAL_FACT", "LATER_INTERPRETATION"},
    "Theorist": {"THEORETICAL_INFERENCE", "TEXTUAL_RELATION"},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class PlannerOutput(StrictModel):
    subquestions: list[str] = Field(min_length=1, max_length=8)

    @field_validator("subquestions")
    @classmethod
    def valid_subquestions(cls, items: list[str]) -> list[str]:
        normalized = [item.strip() for item in items]
        if any(not item or len(item) > 1_000 for item in normalized):
            raise ValueError("subquestions must be nonempty and at most 1000 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate subquestions are not allowed")
        return normalized


class ClaimProposal(StrictModel):
    client_ref: str = Field(min_length=1, max_length=80)
    claim_type: str
    assertion_text: str = Field(min_length=1, max_length=4_000)
    rationale_summary: str = Field(min_length=1, max_length=2_000)
    evidence_revision_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("client_ref", "assertion_text", "rationale_summary")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Agent text fields cannot be blank")
        return value.strip()


class ResearchAgentOutput(StrictModel):
    claims: list[ClaimProposal] = Field(max_length=5)


def _fingerprint(context: dict) -> str:
    encoded = json.dumps(context, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_research_task(
    question: str, *, source_ids: Sequence[UUID] = (), actor_id: str = "local-researcher"
) -> UUID:
    question = question.strip()
    if not 1 <= len(question) <= 2_000:
        raise ValueError("research question must be 1-2000 characters")
    if len(source_ids) > 100 or len(set(source_ids)) != len(source_ids):
        raise ValueError("research scope must contain at most 100 unique sources")
    with SessionLocal.begin() as session:
        if any(session.get(SourceDocument, source_id) is None for source_id in source_ids):
            raise ValueError("research scope contains an unknown source")
        task_id = new_id()
        session.add(ResearchTask(
            id=task_id, public_id=f"RT-{task_id}", question=question,
            status="CREATED", draft_scope={"source_ids": [str(item) for item in source_ids]},
        ))
        append_event(session, event_type="research_task.created", actor_id=actor_id,
                     aggregate_id=task_id, payload={"source_count": len(source_ids)})
        return task_id


def start_research_task(
    task_id: UUID, *, model_version: str, actor_id: str = "local-researcher",
    workflow_config: object | None = None,
    question_outbound_authorized: bool = False,
) -> str:
    """Freeze all version and model choices before any Agent receives context."""
    if not model_version.strip() or len(model_version) > 200:
        raise ValueError("a configured cloud generation model is required")
    from tcm_platform.research_runtime import frozen_prompts
    from tcm_platform.stop_service import WorkflowConfig
    config = workflow_config or WorkflowConfig()
    if not isinstance(config, WorkflowConfig):
        config = WorkflowConfig.model_validate(config)
    with SessionLocal.begin() as session:
        task = session.scalar(select(ResearchTask).where(ResearchTask.id == task_id).with_for_update())
        if task is None or task.status != "CREATED":
            raise ValueError("only a CREATED research task can start")
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime is None or runtime.active_knowledge_version_id is None:
            raise ValueError("no published knowledge version is active")
        version = session.get(KnowledgeVersion, runtime.active_knowledge_version_id)
        build = session.get(IndexBuild, runtime.active_index_build_id)
        if (version is None or build is None or version.status != "READY"
                or build.status != "READY" or build.knowledge_version_id != version.id):
            raise ValueError("active knowledge and index versions are inconsistent")
        context = {
            "task_id": str(task.id), "question": task.question,
            "source_ids": task.draft_scope["source_ids"],
            "knowledge_version_id": str(version.id),
            "index_build_id": str(build.id),
            "workflow_version": "research-v1",
            "workflow_config": config.model_dump(mode="json"),
            "retrieval_profile_version": build.configuration.get("strategy", "hybrid-rrf-v1"),
            "embedding_model": build.configuration["embedding_model"],
            "rerank_model": build.configuration.get("rerank_model"),
            "generation_model": model_version,
            "outbound_mode": build.configuration.get("outbound_mode", "LOCAL_ONLY"),
            "outbound_policy_version": build.configuration.get("outbound_policy_version"),
            "outbound_source_ids": build.configuration.get("outbound_source_ids", []),
            "question_outbound_authorized": question_outbound_authorized,
            "roles": list(RESEARCH_ROLES),
            "prompt_versions": {"Planner": "planner-v1", "Judge": "judge-v1",
                                "EvidenceAuditor": "evidence-auditor-v1",
                                "Critic": "critic-v1", "Rebuttal": "rebuttal-v1",
                                **{role: f"{role.lower()}-v1" for role in RESEARCH_ROLES}},
            "frozen_prompts": frozen_prompts(),
            "agent_schema": "research-agent-output/v1",
        }
        task.execution_context = context
        task.run_fingerprint = _fingerprint(context)
        task.status = "PLANNING"
        task.started_at = utc_now()
        append_event(session, event_type="research_task.started", actor_id=actor_id,
                     aggregate_id=task_id,
                     payload={"run_fingerprint": task.run_fingerprint,
                              "knowledge_version_id": str(version.id),
                              "index_build_id": str(build.id)})
        enqueue_job(
            session, idempotency_key=f"research:{task_id}:run:v1",
            job_type="research.run", payload={"task_id": str(task_id),
                                              "run_fingerprint": task.run_fingerprint},
            resource_class=ResourceClass.LLM_REMOTE, actor_id=actor_id,
        )
        return task.run_fingerprint


def _lock_research_control(session: Session, task_id: UUID) -> tuple[TaskJob, ResearchTask]:
    job = session.scalar(select(TaskJob).where(
        TaskJob.idempotency_key == f"research:{task_id}:run:v1"
    ).with_for_update())
    task = session.scalar(select(ResearchTask).where(
        ResearchTask.id == task_id
    ).with_for_update())
    if job is None or task is None or task.status in {
        "CREATED", "COMPLETED", "CANCELLED",
    }:
        raise ValueError("research task is not controllable")
    return job, task


def request_research_pause(task_id: UUID, *, actor_id: str = "local-researcher") -> str:
    with SessionLocal.begin() as session:
        job, task = _lock_research_control(session, task_id)
        if task.control_state in {"PAUSED", "PAUSE_REQUESTED"}:
            return task.control_state
        if task.control_state != "ACTIVE":
            raise ValueError("research task cannot be paused")
        if job.status == JobStatus.RUNNING.value:
            task.control_state = "PAUSE_REQUESTED"
        elif job.status in {JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value}:
            task.control_state = "PAUSED"
            job.status = JobStatus.PAUSED.value
            job.updated_at = utc_now()
        else:
            raise ValueError("research job cannot be paused")
        append_event(session, event_type="research_task.pause_requested", actor_id=actor_id,
                     aggregate_id=task_id, payload={"control_state": task.control_state})
        return task.control_state


def resume_research_task(task_id: UUID, *, actor_id: str = "local-researcher") -> str:
    with SessionLocal.begin() as session:
        job, task = _lock_research_control(session, task_id)
        if task.control_state == "PAUSE_REQUESTED" and job.status == JobStatus.RUNNING.value:
            task.control_state = "ACTIVE"
        elif task.control_state == "PAUSED" and job.status == JobStatus.PAUSED.value:
            task.control_state = "ACTIVE"
            job.status = JobStatus.PENDING.value
            job.available_at = utc_now()
            job.updated_at = utc_now()
        else:
            raise ValueError("research task is not paused")
        append_event(session, event_type="research_task.resumed", actor_id=actor_id,
                     aggregate_id=task_id, payload={"phase": task.status})
        return task.status


def cancel_research_task(task_id: UUID, *, actor_id: str = "local-researcher") -> str:
    with SessionLocal.begin() as session:
        job, task = _lock_research_control(session, task_id)
        if task.control_state == "CANCEL_REQUESTED":
            return task.control_state
        if job.status == JobStatus.RUNNING.value:
            task.control_state = "CANCEL_REQUESTED"
        elif job.status in {JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value,
                            JobStatus.PAUSED.value}:
            task.control_state = "CANCELLED"
            task.status = "CANCELLED"
            job.status = JobStatus.CANCELLED.value
            job.updated_at = utc_now()
        else:
            raise ValueError("research job cannot be cancelled")
        append_event(session, event_type="research_task.cancel_requested", actor_id=actor_id,
                     aggregate_id=task_id, payload={"control_state": task.control_state})
        return task.control_state


def save_research_plan(
    task_id: UUID, payload: Mapping, *, actor_id: str = "planner",
    lease_guard: LeaseGuard | None = None,
) -> list[UUID]:
    output = PlannerOutput.model_validate(payload)
    with SessionLocal.begin() as session:
        if lease_guard is not None:
            lease_guard(session)
        task = session.scalar(select(ResearchTask).where(ResearchTask.id == task_id).with_for_update())
        if task is None or task.status != "PLANNING" or task.execution_context is None:
            raise ValueError("research task is not planning")
        ids = [new_id() for _ in output.subquestions]
        session.add_all([
            ResearchSubquestion(id=item_id, task_id=task_id, sequence_no=index,
                                question_text=value)
            for index, (item_id, value) in enumerate(zip(ids, output.subquestions, strict=True), 1)
        ])
        task.status = "RETRIEVING"
        append_event(session, event_type="research_task.planned", actor_id=actor_id,
                     aggregate_id=task_id, payload={"subquestion_count": len(ids)})
        return ids


def add_task_evidence(
    task_id: UUID, query: str, results: Sequence[dict], *,
    actor_id: str = "retrieval-service",
    lease_guard: LeaseGuard | None = None,
    evidence_request_id: UUID | None = None,
) -> int:
    """Store pool membership and every retrieval occurrence in separate tables."""
    with SessionLocal.begin() as session:
        if lease_guard is not None:
            lease_guard(session)
        task = session.scalar(select(ResearchTask).where(ResearchTask.id == task_id).with_for_update())
        if task is None or task.status not in {"RETRIEVING", "DEBATING"}:
            raise ValueError("research task is not retrieving")
        if task.status == "DEBATING" and task.control_state != "ACTIVE":
            raise ValueError("research task is not active")
        if task.status == "DEBATING" and evidence_request_id is None:
            raise ValueError("debate retrieval requires an EvidenceRequest")
        if evidence_request_id is not None:
            request = session.get(EvidenceRequest, evidence_request_id)
            if (task.status != "DEBATING" or request is None or request.task_id != task_id
                    or request.query_text != query):
                raise ValueError("EvidenceRequest is outside the active debate retrieval")
            if request.status in {"RETRIEVED", "NO_RESULT"}:
                return 0
            if request.status != "PENDING":
                raise ValueError("EvidenceRequest is not pending")
        context = task.execution_context
        version_id = UUID(context["knowledge_version_id"])
        scoped_sources = {UUID(value) for value in context["source_ids"]}
        existing = {row.evidence_revision_id for row in session.scalars(
            select(TaskEvidenceRef).where(TaskEvidenceRef.task_id == task_id)
        )}
        recorded = {row.evidence_revision_id for row in session.scalars(
            select(EvidenceRetrievalEvent).where(
                EvidenceRetrievalEvent.task_id == task_id,
                EvidenceRetrievalEvent.query_text == query,
                EvidenceRetrievalEvent.evidence_request_id == evidence_request_id,
            )
        )}
        new_count = 0
        for rank, result in enumerate(results, 1):
            revision_id = UUID(result["evidence_revision_id"])
            revision = session.get(EvidenceRevision, revision_id)
            evidence = session.get(Evidence, revision.evidence_id) if revision else None
            is_version_member = session.scalar(select(KnowledgeVersionItem.id).where(
                KnowledgeVersionItem.knowledge_version_id == version_id,
                KnowledgeVersionItem.evidence_revision_id == revision_id,
            )) is not None
            if (revision is None or revision.status != "REVIEWED" or evidence is None
                    or not is_version_member
                    or (scoped_sources and evidence.source_id not in scoped_sources)):
                raise ValueError("retrieved EvidenceRevision is outside the frozen task scope")
            if revision_id not in existing:
                session.add(TaskEvidenceRef(id=new_id(), task_id=task_id,
                                            evidence_revision_id=revision_id))
                existing.add(revision_id)
                new_count += 1
            if revision_id not in recorded:
                session.add(EvidenceRetrievalEvent(
                    id=new_id(), task_id=task_id, evidence_revision_id=revision_id,
                    evidence_request_id=evidence_request_id,
                    query_text=query, rank=rank, channels=result.get("matched_channels", []),
                ))
                recorded.add(revision_id)
        append_event(session, event_type="research_task.evidence_retrieved", actor_id=actor_id,
                     aggregate_id=task_id,
                     payload={"query": query, "result_count": len(results), "new_count": new_count})
        if evidence_request_id is not None:
            request.status = "RETRIEVED" if results else "NO_RESULT"
            request.result_count = len(recorded)
            append_event(session, event_type="evidence_request.resolved", actor_id=actor_id,
                         aggregate_id=evidence_request_id,
                         payload={"result_count": request.result_count})
        return new_count


def retrieve_for_task(
    task_id: UUID, *, embedder: Embedder, reranker: Reranker | None = None,
    limit: int = 10, lease_guard: LeaseGuard | None = None,
) -> int:
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        if task is None or task.status != "RETRIEVING":
            raise ValueError("research task is not retrieving")
        context = task.execution_context
        if (context["embedding_model"] != embedder.model_version
                or ((context["rerank_model"] is None) != (reranker is None))
                or (reranker is not None
                    and context["rerank_model"] != reranker.model_version)):
            raise ValueError("retrieval models differ from frozen task context")
        subquestions = list(session.scalars(select(ResearchSubquestion.question_text).where(
            ResearchSubquestion.task_id == task_id
        ).order_by(ResearchSubquestion.sequence_no)))
        queries = [task.question, *subquestions]
    total = 0
    for query in queries:
        results = search_published(
            query, embedder=embedder, reranker=reranker, limit=limit,
            source_ids=[UUID(value) for value in context["source_ids"]] or None,
            knowledge_version_id=UUID(context["knowledge_version_id"]),
            index_build_id=UUID(context["index_build_id"]),
            query_outbound_authorized=context.get("question_outbound_authorized", False),
            task_id=task_id,
        )
        total += add_task_evidence(task_id, query, results, lease_guard=lease_guard)
    return total


def prepare_first_round(task_id: UUID, *, actor_id: str = "research-runtime",
                        lease_guard: LeaseGuard | None = None) -> list[UUID]:
    """Freeze all role inputs before any role can submit a Claim."""
    with SessionLocal.begin() as session:
        if lease_guard is not None:
            lease_guard(session)
        task = session.scalar(select(ResearchTask).where(ResearchTask.id == task_id).with_for_update())
        if task is None or task.status != "RETRIEVING":
            raise ValueError("research task is not ready for first round")
        evidence_ids = list(session.scalars(select(TaskEvidenceRef.evidence_revision_id).where(
            TaskEvidenceRef.task_id == task_id
        ).order_by(TaskEvidenceRef.evidence_revision_id)))
        if not evidence_ids:
            raise ValueError("first round requires a verified evidence pool")
        subquestions = list(session.scalars(select(ResearchSubquestion.question_text).where(
            ResearchSubquestion.task_id == task_id
        ).order_by(ResearchSubquestion.sequence_no)))
        # All roles receive frozen IDs and questions before any peer Claim exists.
        context = task.execution_context
        ids = [new_id() for _ in RESEARCH_ROLES]
        session.add_all([
            AgentRun(
                id=run_id, task_id=task_id, role=role, round_no=1, status="PENDING",
                input_snapshot={"question": task.question, "subquestions": subquestions,
                                "evidence_revision_ids": [str(item) for item in evidence_ids],
                                "run_fingerprint": task.run_fingerprint,
                                "knowledge_version_id": context["knowledge_version_id"],
                                "prompt_version": context["prompt_versions"][role]},
                visible_evidence_ids=[str(item) for item in evidence_ids],
                model_version=context["generation_model"],
            )
            for role, run_id in zip(RESEARCH_ROLES, ids, strict=True)
        ])
        task.status = "RESEARCHING"
        append_event(session, event_type="research_task.first_round_prepared", actor_id=actor_id,
                     aggregate_id=task_id,
                     payload={"roles": list(RESEARCH_ROLES), "visible_evidence_count": len(evidence_ids)})
        return ids


def agent_visible_context(run_id: UUID) -> dict:
    """Return this role's frozen evidence, without any other Agent's output."""
    with SessionLocal() as session:
        run = session.get(AgentRun, run_id)
        if run is None or run.round_no != 1:
            raise ValueError("first-round AgentRun does not exist")
        snapshot = dict(run.input_snapshot)
        visible = [UUID(value) for value in run.visible_evidence_ids]
        return {**snapshot, "role": run.role,
                "evidence": [trace_evidence(item) for item in visible]}


def submit_first_round_output(
    run_id: UUID, payload: Mapping, *, actor_id: str = "agent-runtime",
    lease_guard: LeaseGuard | None = None,
) -> list[UUID]:
    """Validate the entire Agent output before persisting any Claim."""
    output = ResearchAgentOutput.model_validate(payload)
    refs = [claim.client_ref for claim in output.claims]
    if len(set(refs)) != len(refs):
        raise ValueError("Agent output contains duplicate client_ref")
    with SessionLocal.begin() as session:
        if lease_guard is not None:
            lease_guard(session)
        run = session.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None or run.status != "PENDING" or run.round_no != 1:
            raise ValueError("AgentRun is not accepting first-round output")
        task = session.scalar(select(ResearchTask).where(
            ResearchTask.id == run.task_id
        ).with_for_update())
        if task.status != "RESEARCHING" or run.model_version != task.execution_context["generation_model"]:
            raise ValueError("AgentRun differs from frozen task context")
        visible = {UUID(value) for value in run.visible_evidence_ids}
        if run.role == "HistoricalScholar" and output.claims:
            historical_source = session.scalar(
                select(SourceDocument.id)
                .join(SourceRevision, SourceRevision.source_id == SourceDocument.id)
                .join(EvidenceRevision, EvidenceRevision.source_revision_id == SourceRevision.id)
                .where(
                    EvidenceRevision.id.in_(visible),
                    or_(
                        SourceDocument.author.is_not(None),
                        SourceDocument.era.is_not(None),
                        SourceDocument.school.is_not(None),
                        SourceDocument.edition.is_not(None),
                        SourceDocument.publication_year.is_not(None),
                    ),
                )
            )
            if historical_source is None:
                raise ValueError("HistoricalScholar requires explicit source history metadata")
        pool = {row.evidence_revision_id: row.id for row in session.scalars(
            select(TaskEvidenceRef).where(TaskEvidenceRef.task_id == run.task_id)
        )}
        version_id = UUID(task.execution_context["knowledge_version_id"])
        prepared: list[tuple[ClaimProposal, list[UUID]]] = []
        for proposal in output.claims:
            if proposal.claim_type not in CLAIM_TYPES[run.role]:
                raise ValueError("claim type is not allowed for this Agent role")
            try:
                evidence_ids = [UUID(value) for value in proposal.evidence_revision_ids]
            except ValueError as exc:
                raise ValueError("Agent output contains an invalid EvidenceRevision ID") from exc
            if len(set(evidence_ids)) != len(evidence_ids):
                raise ValueError("Claim repeats an EvidenceRevision ID")
            for revision_id in evidence_ids:
                is_member = session.scalar(select(KnowledgeVersionItem.id).where(
                    KnowledgeVersionItem.knowledge_version_id == version_id,
                    KnowledgeVersionItem.evidence_revision_id == revision_id,
                )) is not None
                revision = session.get(EvidenceRevision, revision_id)
                if (revision_id not in visible or revision_id not in pool or not is_member
                        or revision is None or revision.status != "REVIEWED"):
                    raise ValueError("Agent cited Evidence outside visible, pooled, published revisions")
            prepared.append((proposal, evidence_ids))
        claim_ids = [new_id() for _ in prepared]
        session.add_all([
            Claim(
                id=claim_id, task_id=run.task_id, agent_run_id=run.id,
                agent_role=run.role, claim_type=proposal.claim_type,
                assertion_text=proposal.assertion_text.strip(),
                rationale_summary=proposal.rationale_summary.strip(), status="ACTIVE",
            )
            for claim_id, (proposal, _) in zip(claim_ids, prepared, strict=True)
        ])
        session.flush()
        session.add_all([
            ClaimEvidence(id=new_id(), claim_id=claim_id,
                          task_evidence_ref_id=pool[evidence_id])
            for claim_id, (_, evidence_ids) in zip(claim_ids, prepared, strict=True)
            for evidence_id in evidence_ids
        ])
        run.status = "COMPLETED"
        run.output = output.model_dump(mode="json")
        run.completed_at = utc_now()
        session.flush()
        remaining = session.scalar(select(AgentRun.id).where(
            AgentRun.task_id == run.task_id,
            AgentRun.round_no == 1,
            AgentRun.status == "PENDING",
        ).limit(1))
        if remaining is None:
            task.status = "FIRST_ROUND_COMPLETE"
        append_event(session, event_type="agent_run.first_round_completed", actor_id=actor_id,
                     aggregate_id=run.id,
                     payload={"task_id": str(run.task_id), "role": run.role,
                              "claim_count": len(claim_ids)})
        return claim_ids
