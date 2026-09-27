from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from tcm_platform.db import Base
from tcm_platform.ids import new_id


def utc_now() -> datetime:
    return datetime.now(UTC)


class BlobObject(Base):
    __tablename__ = "blob_object"
    __table_args__ = (CheckConstraint("size_bytes >= 0"), {"schema": "storage"})

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Artifact(Base):
    __tablename__ = "artifact"
    __table_args__ = (Index("ix_artifact_blob", "blob_sha256"), {"schema": "storage"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    blob_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("storage.blob_object.sha256"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_class: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EventLogHead(Base):
    __tablename__ = "event_log_head"
    __table_args__ = (CheckConstraint("id = 1"), {"schema": "governance"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)


class EventLog(Base):
    __tablename__ = "event_log"
    __table_args__ = (
        UniqueConstraint("sequence_no", name="uq_event_sequence"),
        {"schema": "governance"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskJob(Base):
    __tablename__ = "task_job"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_job_idempotency_key"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1"),
        Index("ix_task_job_claim", "status", "available_at", "priority", "created_at"),
        Index("ix_task_job_lease", "status", "lease_expires_at"),
        {"schema": "runtime"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resource_class: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    execution_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskCheckpoint(Base):
    __tablename__ = "task_checkpoint"
    __table_args__ = (
        UniqueConstraint("job_id", "execution_generation", name="uq_checkpoint_generation"),
        {"schema": "runtime"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("runtime.task_job.id"), nullable=False
    )
    execution_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BackupRecord(Base):
    __tablename__ = "backup_record"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "governance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (UniqueConstraint("public_id", name="uq_source_public_id"), {"schema": "source"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(300))
    era: Mapped[str | None] = mapped_column(String(120))
    school: Mapped[str | None] = mapped_column(String(120))
    edition: Mapped[str | None] = mapped_column(String(300))
    publisher: Mapped[str | None] = mapped_column(String(300))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(30), nullable=False)
    copyright_status: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceRevision(Base):
    __tablename__ = "source_revision"
    __table_args__ = (
        UniqueConstraint("source_id", "revision_no", name="uq_source_revision_no"),
        Index("ix_source_revision_hash", "file_sha256"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_document.id"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FileAsset(Base):
    __tablename__ = "file_asset"
    __table_args__ = (
        UniqueConstraint("source_revision_id", "role", "sequence_no", name="uq_file_asset_role"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("storage.artifact.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ImportJob(Base):
    __tablename__ = "import_job"
    __table_args__ = (
        UniqueConstraint("request_key", name="uq_import_request_key"),
        UniqueConstraint("task_job_id", name="uq_import_task_job"),
        Index("ix_import_job_status", "status", "created_at"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    request_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    task_job_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("runtime.task_job.id")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    parsed_artifact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("storage.artifact.id")
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PipelineStepExecution(Base):
    __tablename__ = "pipeline_step_execution"
    __table_args__ = (
        UniqueConstraint("import_job_id", "step", "attempt", name="uq_import_step_attempt"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    import_job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.import_job.id"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(60), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_artifact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("storage.artifact.id")
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TextSegment(Base):
    __tablename__ = "text_segment"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_text_segment_public_id"),
        Index("ix_text_segment_source", "source_id"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_document.id"), nullable=False
    )
    segment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TextSegmentRevision(Base):
    __tablename__ = "text_segment_revision"
    __table_args__ = (
        UniqueConstraint("segment_id", "source_revision_id", name="uq_segment_source_revision"),
        UniqueConstraint("source_revision_id", "sequence_no", name="uq_segment_sequence"),
        Index("ix_segment_revision_locator", "source_revision_id", "page_no", "paragraph_no"),
        Index("ix_segment_revision_checksum", "checksum"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    segment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment.id"), nullable=False
    )
    source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    parent_segment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment.id")
    )
    segment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_before: Mapped[str] = mapped_column(Text, nullable=False)
    context_after: Mapped[str] = mapped_column(Text, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    chapter_no: Mapped[int | None] = mapped_column(Integer)
    paragraph_no: Mapped[int | None] = mapped_column(Integer)
    structural_locator: Mapped[dict] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SegmentAlignment(Base):
    __tablename__ = "segment_alignment"
    __table_args__ = (
        CheckConstraint("old_revision_id IS NOT NULL OR new_revision_id IS NOT NULL"),
        Index("ix_alignment_from_to", "from_source_revision_id", "to_source_revision_id"),
        {"schema": "source"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    from_source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    to_source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    old_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment_revision.id")
    )
    new_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment_revision.id")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

