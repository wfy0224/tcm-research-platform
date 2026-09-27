"""Lease-guarded, resumable first-round research worker."""

from threading import Event, Thread
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit import append_event
from tcm_platform.cloud_models import research_model_for_version
from tcm_platform.db import SessionLocal
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
from tcm_platform.models import ResearchTask, TaskCheckpoint, TaskJob, utc_now
from tcm_platform.research_runtime import (
    StructuredGenerator,
    execute_first_round,
    execute_planner,
)
from tcm_platform.research_service import prepare_first_round, retrieve_for_task
from tcm_platform.retrieval import Embedder, Reranker

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

    def guard(session) -> None:
        if lost.is_set():
            raise LeaseLostError("job heartbeat failed")
        assert_job_lease(session, job_id=job_id, worker_id=worker_id,
                         generation=generation)
        task = session.scalar(select(ResearchTask).where(
            ResearchTask.id == task_id
        ).with_for_update())
        if task.control_state in {"PAUSE_REQUESTED", "CANCEL_REQUESTED"}:
            raise ResearchControlRequested(task.control_state)

    try:
        if model is None:
            with SessionLocal() as session:
                task = session.get(ResearchTask, task_id)
                if task is None or task.execution_context is None:
                    raise ValueError("research task has no frozen model route")
                model = research_model_for_version(task.execution_context["generation_model"])
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
                with SessionLocal.begin() as session:
                    guard(session)
                    complete_job(session, job_id=job_id, worker_id=worker_id,
                                 generation=generation,
                                 result={"task_id": str(task_id), "status": status})
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
