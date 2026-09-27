import io
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal, engine
from tcm_platform.enums import JobStatus, ResourceClass
from tcm_platform.jobs import LeaseLostError, acquire_job, complete_job, enqueue_job
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM runtime.task_job LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("migrated PostgreSQL is not available")


def test_idempotent_enqueue_and_fenced_completion(tmp_path):
    key = f"integration:{uuid4()}"
    store = ContentAddressedStore(tmp_path)
    blob = store.put(io.BytesIO(b"Original source material"))
    with SessionLocal.begin() as session:
        artifact = store.register(
            session,
            blob,
            artifact_type="SOURCE_ORIGINAL",
            retention_class="PERMANENT",
        )
        assert artifact.blob_sha256 == blob.sha256
        first = enqueue_job(
            session,
            idempotency_key=key,
            job_type="test.noop",
            payload={"source": "test"},
            resource_class=ResourceClass.IO,
            actor_id="test",
            priority=1_000_000,
        )
        second = enqueue_job(
            session,
            idempotency_key=key,
            job_type="test.noop",
            payload={"source": "test"},
            resource_class=ResourceClass.IO,
            actor_id="test",
            priority=1_000_000,
        )
        assert first.id == second.id
        with pytest.raises(ValueError, match="different job"):
            enqueue_job(
                session,
                idempotency_key=key,
                job_type="test.other",
                payload={},
                resource_class=ResourceClass.IO,
                actor_id="test",
                priority=1_000_000,
            )
        job_id = first.id

    with SessionLocal.begin() as session:
        claimed = acquire_job(session, worker_id="worker-a")
        assert claimed is not None and claimed.id == job_id
        assert claimed.execution_generation == 1

    with SessionLocal.begin() as session:
        with pytest.raises(LeaseLostError):
            complete_job(session, job_id=job_id, worker_id="worker-b", generation=1, result={})
        checkpoint = complete_job(
            session, job_id=job_id, worker_id="worker-a", generation=1, result={"ok": True}
        )
        assert checkpoint.result == {"ok": True}

    with SessionLocal() as session:
        assert session.get(type(claimed), job_id).status == JobStatus.COMPLETED.value
        assert verify_chain(session)

