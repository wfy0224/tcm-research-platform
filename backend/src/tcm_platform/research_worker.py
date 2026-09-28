"""Lease-guarded research worker through audited debate rounds."""

from threading import Event, Thread
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit import append_event
from tcm_platform.audit_service import mechanical_audit_claim, semantic_audit_claim
from tcm_platform.claim_normalization import normalize_task_claims
from tcm_platform.cloud_models import research_model_for_version
from tcm_platform.db import SessionLocal
from tcm_platform.debate_service import (
    audit_revised_claims,
    execute_critic,
    execute_rebuttal,
    prepare_critic_round,
    prepare_rebuttal_round,
    retrieve_evidence_requests,
)
from tcm_platform.enums import JobStatus
from tcm_platform.jobs import (
    LeaseLostError,
    acquire_job,
    assert_job_lease,
    complete_job,
    fail_job,
    heartbeat,
    recover_expired,
)
from tcm_platform.models import (
    AgentRun,
    Claim,
    Critique,
    EvidenceRequest,
    HumanReviewRequest,
    ResearchTask,
    TaskCheckpoint,
    TaskJob,
    utc_now,
)
from tcm_platform.research_runtime import (
    StructuredGenerator,
    execute_first_round,
    execute_planner,
)
from tcm_platform.research_service import prepare_first_round, retrieve_for_task
from tcm_platform.retrieval import Embedder, Reranker
from tcm_platform.stop_service import evaluate_stop

LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30


class ResearchControlRequested(RuntimeError):
    pass


def _settle_control(task_id: UUID, job_id: UUID, worker_id: str,
                    generation: int) -> bool:
    with SessionLocal.begin() as session:
        assert_job_lease(session, job_id=job_id, worker_id=worker_id,
                         generation=generation)
        job = session.get(TaskJob, job_id)
        task = session.scalar(select(ResearchTask).where(
            ResearchTask.id == task_id
        ).with_for_update())
        if task.control_state not in {"PAUSE_REQUESTED", "CANCEL_REQUESTED"}:
            return False
        paused = task.control_state == "PAUSE_REQUESTED"
        session.add(TaskCheckpoint(
            job_id=job_id, execution_generation=generation,
            result={"task_id": str(task_id), "phase": task.status,
                    "control_state": "PAUSED" if paused else "CANCELLED"},
        ))
        task.control_state = "PAUSED" if paused else "CANCELLED"
        if not paused:
            task.status = "CANCELLED"
        job.status = JobStatus.PAUSED.value if paused else JobStatus.CANCELLED.value
        if paused:
            job.attempts = max(0, job.attempts - 1)
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = utc_now()
        append_event(session, event_type="research_task.paused" if paused else
                     "research_task.cancelled", actor_id=worker_id,
                     aggregate_id=task_id, payload={"phase": task.status})
        return True


def _keep_lease(job_id: UUID, worker_id: str, generation: int,
                stop: Event, lost: Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with SessionLocal.begin() as session:
                heartbeat(session, job_id=job_id, worker_id=worker_id,
                          generation=generation, lease_seconds=LEASE_SECONDS)
        except Exception:  # noqa: BLE001 - the business commit rechecks the lease.
            lost.set()
            return


def run_next_research_job(
    *, worker_id: str, model: StructuredGenerator | None = None,
    embedder: Embedder, reranker: Reranker | None = None, limit: int = 10,
    task_id: UUID | None = None,
) -> UUID | None:
    """Run one persisted task; retries resume from committed domain state."""
    with SessionLocal.begin() as session:
        recover_expired(session, actor_id=worker_id)
        job = acquire_job(session, worker_id=worker_id, lease_seconds=LEASE_SECONDS,
                          job_types=("research.run",),
                          idempotency_key=(f"research:{task_id}:run:v1" if task_id else None))
        if job is None:
            return None
        job_id, generation = job.id, job.execution_generation
        task_id = UUID(job.payload["task_id"])
        fingerprint = job.payload["run_fingerprint"]

    stop, lost = Event(), Event()
    keeper = Thread(target=_keep_lease, args=(job_id, worker_id, generation, stop, lost),
                    daemon=True)
    keeper.start()
    node_phase: str | None = None

    def guard(session) -> None:
        if lost.is_set():
            raise LeaseLostError("job heartbeat failed")
        assert_job_lease(session, job_id=job_id, worker_id=worker_id,
                         generation=generation)
        task = session.scalar(select(ResearchTask).where(
            ResearchTask.id == task_id
        ).with_for_update())
        if task is None or task.run_fingerprint != fingerprint:
            raise ValueError("research job differs from frozen task context")
        if task.control_state in {"PAUSE_REQUESTED", "CANCEL_REQUESTED"}:
            raise ResearchControlRequested(task.control_state)
        if task.control_state != "ACTIVE":
            raise ValueError("research job control state is not active")
        if node_phase is not None:
            session.add(TaskCheckpoint(
                job_id=job_id, execution_generation=generation,
                result={"kind": "research.node", "phase": node_phase,
                        "task_id": str(task_id), "run_fingerprint": fingerprint},
            ))

    def finish_debate(round_no: int) -> UUID | None:
        nonlocal node_phase
        node_phase = None
        with SessionLocal.begin() as session:
            guard(session)
            task = session.scalar(select(ResearchTask).where(
                ResearchTask.id == task_id
            ).with_for_update())
            if task.status not in {"FIRST_ROUND_COMPLETE", "DEBATING", "STOP_EVALUATION"}:
                raise ValueError("research task cannot finish its debate round")
            normalize_task_claims(task_id, actor_id=worker_id, session=session)
            evaluation = evaluate_stop(session, task_id, round_no)
            if evaluation.decision == "CONTINUE":
                task.status = "FIRST_ROUND_COMPLETE"
                return None
            if evaluation.decision == "WAITING_HUMAN":
                task.interrupted_stage = "STOP_EVALUATION"
                task.resume_stage = "STOP_EVALUATION"
                task.waiting_reason_code = evaluation.reason_code
                task.status = "WAITING_HUMAN"
                source_key = f"{round_no}:{evaluation.reason_code}"
                request = session.scalar(select(HumanReviewRequest).where(
                    HumanReviewRequest.task_id == task_id,
                    HumanReviewRequest.source_key == source_key))
                if request is None:
                    session.add(HumanReviewRequest(
                        task_id=task_id, stop_evaluation_id=evaluation.id,
                        source_key=source_key, status="PENDING",
                        interrupted_stage="STOP_EVALUATION", resume_stage="STOP_EVALUATION",
                        reason_code=evaluation.reason_code))
                append_event(session, event_type="research_task.waiting_human",
                             actor_id=worker_id, aggregate_id=task_id,
                             payload={"reason_code": evaluation.reason_code,
                                      "round_no": round_no})
            else:
                task.status = "DEBATE_ROUND_COMPLETE"
                append_event(session, event_type="research_task.debate_round_completed",
                             actor_id=worker_id, aggregate_id=task_id,
                             payload={"reason": evaluation.reason_code,
                                      "round_no": round_no})
            complete_job(session, job_id=job_id, worker_id=worker_id,
                         generation=generation,
                         result={"task_id": str(task_id), "status": task.status,
                                 "reason": evaluation.reason_code})
        return job_id

    try:
        if model is None:
            with SessionLocal() as session:
                task = session.get(ResearchTask, task_id)
                if task is None or task.execution_context is None:
                    raise ValueError("research task has no frozen model route")
                model = research_model_for_version(task.execution_context["generation_model"])
        with SessionLocal() as session:
            task = session.get(ResearchTask, task_id)
            if (task is None or task.execution_context is None
                    or model.model_version != task.execution_context["generation_model"]):
                raise ValueError("research Worker model differs from frozen task route")
        while True:
            with SessionLocal() as session:
                task = session.get(ResearchTask, task_id)
                if task is None or task.run_fingerprint != fingerprint:
                    raise ValueError("research job differs from frozen task context")
                status = task.status
                control_state = task.control_state
            if control_state in {"PAUSE_REQUESTED", "CANCEL_REQUESTED"}:
                if _settle_control(task_id, job_id, worker_id, generation):
                    return job_id
                continue
            if control_state != "ACTIVE":
                raise ValueError("research job control state is not active")
            if status == "PLANNING":
                execute_planner(task_id, model=model, lease_guard=guard)
            elif status == "RETRIEVING":
                retrieve_for_task(task_id, embedder=embedder, reranker=reranker,
                                  limit=limit, lease_guard=guard)
                prepare_first_round(task_id, lease_guard=guard)
            elif status == "RESEARCHING":
                execute_first_round(task_id, model=model, lease_guard=guard)
                with SessionLocal() as session:
                    if session.get(ResearchTask, task_id).status == "RESEARCHING":
                        raise RuntimeError("first round has no completed state")
            elif status == "FIRST_ROUND_COMPLETE":
                with SessionLocal() as session:
                    pending = session.scalar(select(Claim).where(
                        Claim.task_id == task_id, Claim.parent_claim_id.is_(None),
                        Claim.audit_status.in_(("PENDING", "PENDING_SEMANTIC")),
                    ).order_by(Claim.created_at, Claim.id).limit(1))
                    pending_id = pending.id if pending else None
                    pending_status = pending.audit_status if pending else None
                    any_claim = session.scalar(select(Claim.id).where(
                        Claim.task_id == task_id, Claim.parent_claim_id.is_(None),
                    ).limit(1)) is not None
                if pending_id is not None:
                    if pending_status == "PENDING":
                        node_phase = "FIRST_ROUND_MECHANICAL_AUDIT"
                        mechanical_audit_claim(pending_id, lease_guard=guard)
                    else:
                        node_phase = "FIRST_ROUND_SEMANTIC_AUDIT"
                        semantic_audit_claim(pending_id, model=model, lease_guard=guard)
                elif not any_claim:
                    return finish_debate(1)
                else:
                    node_phase = "FIRST_ROUND_CLAIMS_NORMALIZED"
                    with SessionLocal.begin() as session:
                        guard(session)
                        normalize_task_claims(task_id, actor_id=worker_id, session=session)
                    node_phase = "CRITIC_PREPARED"
                    prepare_critic_round(task_id, lease_guard=guard)
            elif status == "DEBATING":
                with SessionLocal() as session:
                    critic = session.scalar(select(AgentRun).where(
                        AgentRun.task_id == task_id, AgentRun.role == "Critic",
                    ).order_by(AgentRun.round_no.desc()).limit(1))
                    rebuttal = session.scalar(select(AgentRun).where(
                        AgentRun.task_id == task_id, AgentRun.role == "Rebuttal",
                        AgentRun.round_no == (critic.round_no if critic else 2),
                    ))
                    has_critique = session.scalar(select(Critique.id).where(
                        Critique.agent_run_id == (critic.id if critic else None),
                    ).limit(1)) is not None
                    has_pending_request = session.scalar(select(EvidenceRequest.id).where(
                        EvidenceRequest.task_id == task_id,
                        EvidenceRequest.status == "PENDING",
                    ).limit(1)) is not None
                    critic_state = (critic.id, critic.status) if critic else None
                    rebuttal_state = (rebuttal.id, rebuttal.status) if rebuttal else None
                if critic_state is None:
                    raise ValueError("debating task has no Critic AgentRun")
                if critic_state[1] == "PENDING":
                    node_phase = "CRITIC_SUBMITTED"
                    execute_critic(critic_state[0], model=model, lease_guard=guard)
                elif critic_state[1] != "COMPLETED":
                    raise ValueError("Critic AgentRun is not recoverable")
                elif not has_critique:
                    if finish_debate(critic.round_no) is not None:
                        return job_id
                elif has_pending_request:
                    node_phase = "EVIDENCE_REQUEST_RESOLVED"
                    retrieve_evidence_requests(task_id, embedder=embedder,
                                               reranker=reranker, limit=limit,
                                               lease_guard=guard)
                elif rebuttal_state is None:
                    node_phase = "REBUTTAL_PREPARED"
                    prepare_rebuttal_round(task_id, lease_guard=guard)
                elif rebuttal_state[1] == "PENDING":
                    node_phase = "REBUTTAL_SUBMITTED"
                    execute_rebuttal(rebuttal_state[0], model=model, lease_guard=guard)
                elif rebuttal_state[1] != "COMPLETED":
                    raise ValueError("Rebuttal AgentRun is not recoverable")
                else:
                    node_phase = "REVISED_CLAIM_AUDITED"
                    results = audit_revised_claims(task_id, model=model,
                                                   lease_guard=guard)
                    if not results and finish_debate(critic.round_no) is not None:
                        return job_id
            elif status == "STOP_EVALUATION":
                with SessionLocal() as session:
                    latest_round = session.scalar(select(AgentRun.round_no).where(
                        AgentRun.task_id == task_id, AgentRun.role == "Critic",
                    ).order_by(AgentRun.round_no.desc()).limit(1))
                if finish_debate(latest_round or 1) is not None:
                    return job_id
            else:
                raise ValueError(f"research task cannot run from {status}")
    except LeaseLostError:
        return job_id
    except ResearchControlRequested:
        try:
            if _settle_control(task_id, job_id, worker_id, generation):
                return job_id
            with SessionLocal.begin() as session:
                fail_job(session, job_id=job_id, worker_id=worker_id,
                         generation=generation, error="control request changed during commit")
        except LeaseLostError:
            pass
        return job_id
    except Exception as exc:  # noqa: BLE001 - record worker failure for retry.
        try:
            with SessionLocal.begin() as session:
                fail_job(session, job_id=job_id, worker_id=worker_id,
                         generation=generation, error=f"{type(exc).__name__}: {exc}")
        except LeaseLostError:
            pass
        return job_id
    finally:
        stop.set()
        keeper.join(timeout=2)
