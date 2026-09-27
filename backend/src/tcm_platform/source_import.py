"""Source registration and parse execution with short database transactions."""

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from tcm_platform.audit import append_event
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import JobStatus, ResourceClass
from tcm_platform.ids import new_id
from tcm_platform.jobs import acquire_job, complete_job, enqueue_job, fail_job
from tcm_platform.models import (
    Artifact,
    FileAsset,
    ImportJob,
    PipelineStepExecution,
    SourceDocument,
    SourceRevision,
    TaskJob,
    utc_now,
)
from tcm_platform.parsing import (
    PARSER_VERSION,
    OCRRequired,
    SourceParseError,
    parse_source_file,
    validate_source_file,
)
from tcm_platform.storage import ContentAddressedStore

IMPORT_VERSION = "source-import/v1"


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_type: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=300)
    era: str | None = Field(default=None, max_length=120)
    school: str | None = Field(default=None, max_length=120)
    edition: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=300)
    publication_year: int | None = None
    language: str = Field(default="zh", min_length=1, max_length=30)
    copyright_status: str = Field(default="UNKNOWN", min_length=1, max_length=80)


SOURCE_TYPES = frozenset(
    {
        "CLASSIC", "PHYSICIAN_WORK", "COMMENTARY", "FORMULA_BOOK", "MATERIA_MEDICA",
        "MEDICAL_CASE_COLLECTION", "TEXTBOOK", "GUIDELINE", "MODERN_RESEARCH",
        "PATIENT_CASE", "OTHER",
    }
)


@dataclass(frozen=True)
class ImportResult:
    import_job_id: UUID
    source_id: UUID
    source_revision_id: UUID
    task_job_id: UUID | None
    status: str


def _result(session, import_job: ImportJob) -> ImportResult:
    revision = session.get(SourceRevision, import_job.source_revision_id)
    if revision is None:
        raise RuntimeError("import references a missing source revision")
    return ImportResult(
        import_job.id, revision.source_id, revision.id, import_job.task_job_id, import_job.status
    )


def import_file(
    file_path: Path,
    metadata: SourceMetadata,
    *,
    request_key: str,
    source_id: UUID | None = None,
    actor_id: str = "local-user",
    store: ContentAddressedStore | None = None,
) -> ImportResult:
    if metadata.source_type not in SOURCE_TYPES:
        raise ValueError("unknown source type")
    if not request_key or len(request_key) > 200:
        raise ValueError("request_key must be 1-200 characters")
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    store = store or ContentAddressedStore(settings.data_root)
    with file_path.open("rb") as stream:
        blob = store.put(stream, max_bytes=settings.max_import_bytes)
    file_format = file_path.suffix.lower().lstrip(".")
    validation_error: SourceParseError | None = None
    try:
        validate_source_file(blob.path, file_format)
    except SourceParseError as exc:
        validation_error = exc
    snapshot = metadata.model_dump(mode="json")

    with SessionLocal.begin() as session:
        # Serialize retries of one command before checking the unique request key.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:request_key, 0))"),
            {"request_key": request_key},
        )
        existing = session.scalar(select(ImportJob).where(ImportJob.request_key == request_key))
        if existing is not None:
            revision = session.get(SourceRevision, existing.source_revision_id)
            if (
                revision is None
                or revision.file_sha256 != blob.sha256
                or revision.metadata_snapshot != snapshot
                or (source_id is not None and revision.source_id != source_id)
            ):
                raise ValueError("request key was already used for different source content")
            return _result(session, existing)

        original = store.register(
            session,
            blob,
            artifact_type="SOURCE_ORIGINAL",
            retention_class="PERMANENT",
            original_name=file_path.name,
        )
        if source_id is None:
            source = SourceDocument(
                id=new_id(),
                public_id=f"SRC-{new_id()}",
                source_type=metadata.source_type,
                title=metadata.title,
                author=metadata.author,
                era=metadata.era,
                school=metadata.school,
                edition=metadata.edition,
                publisher=metadata.publisher,
                publication_year=metadata.publication_year,
                language=metadata.language,
                copyright_status=metadata.copyright_status,
                status="DRAFT",
            )
            session.add(source)
            session.flush()
            revision_no = 1
        else:
            source = session.scalar(
                select(SourceDocument).where(SourceDocument.id == source_id).with_for_update()
            )
            if source is None:
                raise ValueError("source_id does not exist")
            if source.title != metadata.title or source.source_type != metadata.source_type:
                raise ValueError("new revision must keep source title and type")
            last_revision = session.scalar(
                select(func.max(SourceRevision.revision_no)).where(
                    SourceRevision.source_id == source_id
                )
            )
            revision_no = (last_revision or 0) + 1
        revision = SourceRevision(
            id=new_id(),
            source_id=source.id,
            revision_no=revision_no,
            file_sha256=blob.sha256,
            file_size_bytes=blob.size_bytes,
            file_format=file_format,
            metadata_snapshot=snapshot,
        )
        import_job = ImportJob(
            id=new_id(),
            request_key=request_key,
            source_revision_id=revision.id,
            status="REGISTERED" if validation_error is None else "FAILED",
            error_code=validation_error.code if validation_error else None,
            error_message=str(validation_error) if validation_error else None,
        )
        session.add(revision)
        session.flush()
        session.add_all(
            [
                FileAsset(
                    source_revision_id=revision.id,
                    artifact_id=original.id,
                    role="ORIGINAL",
                    sequence_no=0,
                ),
                import_job,
            ]
        )
        session.flush()
        session.add_all(
            [
                PipelineStepExecution(
                    import_job_id=import_job.id,
                    step="REGISTER",
                    attempt=1,
                    status="COMPLETED",
                    input_hash=blob.sha256,
                    tool_version=IMPORT_VERSION,
                    parameters={"file_format": file_format, "size_bytes": blob.size_bytes},
                    output_artifact_id=original.id,
                    finished_at=utc_now(),
                ),
                PipelineStepExecution(
                    import_job_id=import_job.id,
                    step="VALIDATE_FILE",
                    attempt=1,
                    status="COMPLETED" if validation_error is None else "FAILED",
                    input_hash=blob.sha256,
                    tool_version=IMPORT_VERSION,
                    parameters={"file_format": file_format},
                    error_code=validation_error.code if validation_error else None,
                    error_message=str(validation_error) if validation_error else None,
                    finished_at=utc_now(),
                ),
            ]
        )
        session.flush()
        if validation_error is None:
            job = enqueue_job(
                session,
                idempotency_key=f"source.parse:{import_job.id}",
                job_type="source.parse",
                payload={"import_job_id": str(import_job.id)},
                resource_class=ResourceClass.CPU_PARSE,
                actor_id=actor_id,
            )
            import_job.task_job_id = job.id
        append_event(
            session,
            event_type="source.registered" if validation_error is None else "source.rejected",
            actor_id=actor_id,
            aggregate_id=source.id,
            payload={
                "revision_id": str(revision.id),
                "file_sha256": blob.sha256,
                "status": import_job.status,
                "error_code": import_job.error_code,
            },
        )
        return _result(session, import_job)


def _parse_step(session, import_job_id: UUID, attempt: int) -> PipelineStepExecution:
    step = session.scalar(
        select(PipelineStepExecution).where(
            PipelineStepExecution.import_job_id == import_job_id,
            PipelineStepExecution.step == "PARSE",
            PipelineStepExecution.attempt == attempt,
        )
    )
    if step is None:
        raise RuntimeError("parse step is missing")
    return step


def process_next_import(
    *, worker_id: str = "local-parser", store: ContentAddressedStore | None = None
) -> ImportResult | None:
    store = store or ContentAddressedStore(settings.data_root)
    with SessionLocal.begin() as session:
        job = acquire_job(
            session, worker_id=worker_id, lease_seconds=900, job_types=("source.parse",)
        )
        if job is None:
            return None
        import_job_id = UUID(job.payload["import_job_id"])
        import_job = session.get(ImportJob, import_job_id)
        if import_job is None:
            raise RuntimeError("parse job references a missing import")
        revision = session.get(SourceRevision, import_job.source_revision_id)
        if revision is None:
            raise RuntimeError("import references a missing source revision")
        job_id, generation, attempt = job.id, job.execution_generation, job.attempts
        import_job.status = "PARSING"
        import_job.updated_at = utc_now()
        session.add(
            PipelineStepExecution(
                import_job_id=import_job.id,
                step="PARSE",
                attempt=attempt,
                status="RUNNING",
                input_hash=revision.file_sha256,
                tool_version=PARSER_VERSION,
                parameters={"file_format": revision.file_format},
            )
        )
        source_revision_id = revision.id
        blob_path = store.path_for(revision.file_sha256)
        file_format = revision.file_format

    parsed_blob = None
    parse_error: SourceParseError | None = None
    try:
        parsed = parse_source_file(blob_path, file_format)
        parsed_blob = store.put(io.BytesIO(parsed.to_bytes()))
    except SourceParseError as exc:
        parse_error = exc
    except Exception as exc:  # noqa: BLE001 - preserve unexpected parser failures for retry.
        parse_error = SourceParseError("PARSE_FAILED", str(exc))

    with SessionLocal.begin() as session:
        import_job = session.scalar(select(ImportJob).where(ImportJob.id == import_job_id).with_for_update())
        if import_job is None:
            raise RuntimeError("import disappeared during parsing")
        step = _parse_step(session, import_job_id, attempt)
        now = datetime.now(UTC)
        if parse_error is None and parsed_blob is not None:
            complete_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                generation=generation,
                result={"status": "PARSED", "source_revision_id": str(source_revision_id)},
            )
            artifact: Artifact = store.register(
                session,
                parsed_blob,
                artifact_type="PARSED_DOCUMENT",
                retention_class="PERMANENT",
            )
            import_job.parsed_artifact_id = artifact.id
            import_job.status = "PARSED"
            import_job.error_code = None
            import_job.error_message = None
            step.status = "COMPLETED"
            step.output_artifact_id = artifact.id
            append_event(
                session,
                event_type="source.parsed",
                actor_id=worker_id,
                aggregate_id=source_revision_id,
                payload={"parsed_artifact_id": str(artifact.id)},
            )
        elif isinstance(parse_error, OCRRequired):
            complete_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                generation=generation,
                result={"status": "OCR_REQUIRED", "source_revision_id": str(source_revision_id)},
            )
            import_job.status = "OCR_REQUIRED"
            import_job.error_code = parse_error.code
            import_job.error_message = str(parse_error)
            step.status = "BLOCKED"
            step.error_code = parse_error.code
            step.error_message = str(parse_error)
            append_event(
                session,
                event_type="source.ocr_required",
                actor_id=worker_id,
                aggregate_id=source_revision_id,
                payload={"import_job_id": str(import_job_id)},
            )
        else:
            error = parse_error or SourceParseError("PARSE_FAILED", "unknown parser failure")
            fail_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                generation=generation,
                error=str(error),
            )
            current_job = session.get(TaskJob, job_id)
            import_job.status = (
                "RETRY_WAIT" if current_job.status == JobStatus.RETRY_WAIT.value else "FAILED"
            )
            import_job.error_code = error.code
            import_job.error_message = str(error)
            step.status = "FAILED"
            step.error_code = error.code
            step.error_message = str(error)
            append_event(
                session,
                event_type="source.parse_failed",
                actor_id=worker_id,
                aggregate_id=source_revision_id,
                payload={"error_code": error.code, "attempt": attempt},
            )
        step.finished_at = now
        import_job.updated_at = now
        return _result(session, import_job)

