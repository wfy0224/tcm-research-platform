from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.enums import JobStatus, ResourceClass
from tcm_platform.models import TaskCheckpoint, TaskJob


class LeaseLostError(RuntimeError):
    pass


def enqueue_job(
    session: Session,
    *,
    idempotency_key: str,
    job_type: str,
    payload: dict,
    resource_class: ResourceClass,
    actor_id: str,
    priority: int = 0,
) -> TaskJob:
    """The unique key makes repeated command delivery return the original job."""
    statement = (
        insert(TaskJob)
        .values(
            idempotency_key=idempotency_key,
            job_type=job_type,
            payload=payload,
            resource_class=resource_class.value,
            priority=priority,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(TaskJob.id)
    )
    inserted_id = session.scalar(statement)
    job = (
        session.get(TaskJob, inserted_id)
        if inserted_id is not None
        else session.scalar(select(TaskJob).where(TaskJob.idempotency_key == idempotency_key))
    )
    if job is None:
        raise RuntimeError("job idempotency lookup failed")
    if (
        job.job_type != job_type
        or job.payload != payload
        or job.resource_class != resource_class.value
        or job.priority != priority
    ):
        raise ValueError("idempotency key was already used for a different job")
    if inserted_id is not None:
        append_event(
            session,
            event_type="job.enqueued",
            actor_id=actor_id,
            aggregate_id=job.id,
            payload={"job_type": job_type, "resource_class": resource_class.value},
        )
    return job


def acquire_job(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 60,
    job_types: tuple[str, ...] | None = None,
    idempotency_key: str | None = None,
) -> TaskJob | None:
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    now = datetime.now(UTC)
    query = (
        select(TaskJob)
        .where(TaskJob.status.in_([JobStatus.PENDING.value, JobStatus.RETRY_WAIT.value]))
        .where(TaskJob.available_at <= now)
    )
    if job_types is not None:
        if not job_types:
            return None
        query = query.where(TaskJob.job_type.in_(job_types))
    if idempotency_key is not None:
        query = query.where(TaskJob.idempotency_key == idempotency_key)
    job = session.scalar(
        query.order_by(TaskJob.priority.desc(), TaskJob.available_at, TaskJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = JobStatus.RUNNING.value
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.execution_generation += 1
    job.attempts += 1
    job.updated_at = now
    session.flush()
    return job


def _locked_lease(session: Session, job_id: UUID, worker_id: str, generation: int) -> TaskJob:
    job = session.scalar(select(TaskJob).where(TaskJob.id == job_id).with_for_update())
    now = datetime.now(UTC)
    if (
        job is None
        or job.status != JobStatus.RUNNING.value
        or job.lease_owner != worker_id
        or job.execution_generation != generation
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise LeaseLostError("job lease is no longer valid")
    return job


def assert_job_lease(session: Session, *, job_id: UUID, worker_id: str,
                     generation: int) -> None:
    _locked_lease(session, job_id, worker_id, generation)


def heartbeat(
    session: Session, *, job_id: UUID, worker_id: str, generation: int, lease_seconds: int = 60
) -> None:
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    job = _locked_lease(session, job_id, worker_id, generation)
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)


def complete_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    result: dict,
) -> TaskCheckpoint:
    """Persist result, checkpoint, event, and job completion in one transaction."""
    job = _locked_lease(session, job_id, worker_id, generation)
    checkpoint = TaskCheckpoint(job_id=job.id, execution_generation=generation, result=result)
    session.add(checkpoint)
    job.status = JobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.updated_at = datetime.now(UTC)
    append_event(
        session,
        event_type="job.completed",
        actor_id=worker_id,
        aggregate_id=job.id,
        payload={"generation": generation},
    )
    return checkpoint


def fail_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    error: str,
) -> None:
    job = _locked_lease(session, job_id, worker_id, generation)
    now = datetime.now(UTC)
    retryable = job.attempts < job.max_attempts
    job.status = JobStatus.RETRY_WAIT.value if retryable else JobStatus.FAILED.value
    job.available_at = now + timedelta(seconds=min(300, 2**job.attempts)) if retryable else now
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = error[:4000]
    job.updated_at = now
    append_event(
        session,
        event_type="job.retry_scheduled" if retryable else "job.failed",
        actor_id=worker_id,
        aggregate_id=job.id,
        payload={"generation": generation, "attempts": job.attempts},
    )


def recover_expired(session: Session, *, actor_id: str = "recovery") -> int:
    """Reconcile the checkpoint before requeueing an expired job."""
    now = datetime.now(UTC)
    expired = list(
        session.scalars(
            select(TaskJob)
            .where(TaskJob.status == JobStatus.RUNNING.value)
            .where(TaskJob.lease_expires_at < now)
            .with_for_update(skip_locked=True)
            .limit(100)
        )
    )
    for job in expired:
        checkpoints = session.scalars(
            select(TaskCheckpoint.result).where(
                TaskCheckpoint.job_id == job.id,
                TaskCheckpoint.execution_generation == job.execution_generation,
            )
        )
        if any(result.get("kind") != "research.node" for result in checkpoints):
            job.status = JobStatus.COMPLETED.value
        elif job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED.value
        else:
            job.status = JobStatus.RETRY_WAIT.value
            job.available_at = now
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = now
        append_event(
            session,
            event_type="job.reconciled",
            actor_id=actor_id,
            aggregate_id=job.id,
            payload={"generation": job.execution_generation, "status": job.status},
        )
    return len(expired)

