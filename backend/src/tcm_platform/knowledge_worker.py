"""Complete a queued knowledge publication using the established publish services."""

from uuid import UUID

from sqlalchemy import select

from tcm_platform.cloud_models import cloud_clients_from_environment
from tcm_platform.db import SessionLocal
from tcm_platform.jobs import acquire_job, complete_job, fail_job
from tcm_platform.knowledge_publish import activate_knowledge_version, create_index_build
from tcm_platform.models import IndexBuild, KnowledgeRuntimeState, KnowledgeVersion
from tcm_platform.retrieval import build_retrieval_index


def process_next_knowledge_publish(*, worker_id: str = "local-publisher") -> UUID | None:
    """Retry against the same build; the old active pointers survive every failed gate."""
    with SessionLocal.begin() as session:
        job = acquire_job(session, worker_id=worker_id, lease_seconds=3600,
                          job_types=("knowledge.publish",))
        if job is None:
            return None
        job_id, generation = job.id, job.execution_generation
        version_id = UUID(job.payload["version_id"])
        configuration = job.payload["configuration"]

    try:
        embedder, reranker = cloud_clients_from_environment()
        if (configuration["embedding_model"] != embedder.model_version
                or configuration["rerank_model"] != reranker.model_version
                or configuration["embedding_endpoint"] != embedder.endpoint
                or configuration["rerank_endpoint"] != reranker.endpoint):
            raise ValueError("index configuration differs from the configured model route")
        with SessionLocal() as session:
            version = session.get(KnowledgeVersion, version_id)
            if version is None:
                raise ValueError("knowledge version does not exist")
            build = session.scalar(select(IndexBuild).where(
                IndexBuild.knowledge_version_id == version_id).order_by(
                    IndexBuild.created_at.desc(), IndexBuild.id.desc()).limit(1))
            if build is not None and any(
                build.configuration.get(key) != value for key, value in configuration.items()
            ):
                raise ValueError("existing index build uses a different configuration")
            build_id = build.id if build else None
        if build_id is None:
            build_id = create_index_build(version_id, configuration=configuration,
                                          actor_id=worker_id)
        with SessionLocal() as session:
            build = session.get(IndexBuild, build_id)
            build_status = build.status
        if build_status == "PENDING":
            build_retrieval_index(build_id, embedder=embedder, actor_id=worker_id)
        elif build_status != "READY":
            raise ValueError("index build cannot be resumed from its current status")
        with SessionLocal() as session:
            runtime = session.get(KnowledgeRuntimeState, 1)
            already_active = (runtime is not None
                              and runtime.active_knowledge_version_id == version_id
                              and runtime.active_index_build_id == build_id)
        if not already_active:
            activate_knowledge_version(version_id, build_id, actor_id=worker_id)
        with SessionLocal.begin() as session:
            complete_job(session, job_id=job_id, worker_id=worker_id,
                         generation=generation, result={"knowledge_version_id": str(version_id),
                                                        "index_build_id": str(build_id)})
    except Exception as exc:  # noqa: BLE001 - record unexpected worker failures for retry.
        with SessionLocal.begin() as session:
            fail_job(session, job_id=job_id, worker_id=worker_id,
                     generation=generation, error=str(exc))
    return job_id
