from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from tcm_platform.db import Base
from tcm_platform.ids import new_id
from tcm_platform.vector_type import Vector


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
        Index("ix_checkpoint_job_generation", "job_id", "execution_generation", "created_at"),
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


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("public_id", name="uq_evidence_public_id"), {"schema": "knowledge"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_document.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceRevision(Base):
    __tablename__ = "evidence_revision"
    __table_args__ = (
        UniqueConstraint("evidence_id", "revision_no", name="uq_evidence_revision_no"),
        Index("ix_evidence_revision_source", "source_revision_id", "status"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    evidence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence.id"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    anchor_segment_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment_revision.id"), nullable=False
    )
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_before: Mapped[str] = mapped_column(Text, nullable=False)
    context_after: Mapped[str] = mapped_column(Text, nullable=False)
    citation_locator: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_class: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    quote_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceSegmentRef(Base):
    __tablename__ = "evidence_segment_ref"
    __table_args__ = (
        UniqueConstraint("evidence_revision_id", "sequence_no", name="uq_evidence_ref_sequence"),
        UniqueConstraint("evidence_revision_id", "segment_revision_id", name="uq_evidence_ref_segment"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )
    segment_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment_revision.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)


class EntityMention(Base):
    __tablename__ = "entity_mention"
    __table_args__ = (Index("ix_mention_segment", "segment_revision_id"), {"schema": "knowledge"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    segment_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.text_segment_revision.id"), nullable=False
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.concept.id")
    )
    surface_text: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="CANDIDATE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Concept(Base):
    __tablename__ = "concept"
    __table_args__ = (UniqueConstraint("public_id", name="uq_concept_public_id"), {"schema": "knowledge"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    concept_type: Mapped[str] = mapped_column(String(60), nullable=False)
    era: Mapped[str | None] = mapped_column(String(120))
    school: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConceptTerm(Base):
    __tablename__ = "concept_term"
    __table_args__ = (
        UniqueConstraint("concept_id", "term", "term_kind", name="uq_concept_term"),
        Index("ix_concept_term_text", "term"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    concept_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.concept.id"), nullable=False
    )
    term: Mapped[str] = mapped_column(String(300), nullable=False)
    term_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    era: Mapped[str | None] = mapped_column(String(120))
    school: Mapped[str | None] = mapped_column(String(120))


class ConceptEvidence(Base):
    __tablename__ = "concept_evidence"
    __table_args__ = (
        UniqueConstraint("concept_id", "evidence_revision_id", name="uq_concept_evidence"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    concept_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.concept.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )


class KnowledgeRelation(Base):
    __tablename__ = "relation"
    __table_args__ = (UniqueConstraint("public_id", name="uq_relation_public_id"), {"schema": "knowledge"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_concept_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.concept.id"), nullable=False
    )
    object_concept_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.concept.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    assertion_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RelationEvidence(Base):
    __tablename__ = "relation_evidence"
    __table_args__ = (
        UniqueConstraint("relation_id", "evidence_revision_id", name="uq_relation_evidence"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    relation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.relation.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )


class Herb(Base):
    __tablename__ = "herb"
    __table_args__ = (UniqueConstraint("public_id", name="uq_herb_public_id"), {"schema": "knowledge"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    era: Mapped[str | None] = mapped_column(String(120))
    school: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class HerbTerm(Base):
    __tablename__ = "herb_term"
    __table_args__ = (
        UniqueConstraint("herb_id", "term", "term_kind", name="uq_herb_term"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    herb_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.herb.id"), nullable=False
    )
    term: Mapped[str] = mapped_column(String(300), nullable=False)
    term_kind: Mapped[str] = mapped_column(String(30), nullable=False)


class HerbEvidence(Base):
    __tablename__ = "herb_evidence"
    __table_args__ = (
        UniqueConstraint("herb_id", "evidence_revision_id", name="uq_herb_evidence"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    herb_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.herb.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )


class Formula(Base):
    __tablename__ = "formula"
    __table_args__ = (UniqueConstraint("public_id", name="uq_formula_public_id"), {"schema": "knowledge"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FormulaRevision(Base):
    __tablename__ = "formula_revision"
    __table_args__ = (
        UniqueConstraint("formula_id", "revision_no", name="uq_formula_revision_no"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    formula_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.formula.id"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    original_name: Mapped[str] = mapped_column(String(300), nullable=False)
    era: Mapped[str | None] = mapped_column(String(120))
    school: Mapped[str | None] = mapped_column(String(120))
    indications: Mapped[str | None] = mapped_column(Text)
    effects: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    dosage_form: Mapped[str | None] = mapped_column(String(100))
    preparation: Mapped[str | None] = mapped_column(Text)
    cautions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FormulaIngredient(Base):
    __tablename__ = "formula_ingredient"
    __table_args__ = (
        UniqueConstraint("formula_revision_id", "sequence_no", name="uq_formula_ingredient_sequence"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    formula_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.formula_revision.id"), nullable=False
    )
    herb_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("knowledge.herb.id"))
    original_name: Mapped[str] = mapped_column(String(300), nullable=False)
    amount_original: Mapped[str | None] = mapped_column(String(120))
    amount_normalized: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(60))
    dose_ratio: Mapped[str | None] = mapped_column(String(60))
    role: Mapped[str | None] = mapped_column(String(60))
    processing: Mapped[str | None] = mapped_column(String(300))
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)


class FormulaEvidence(Base):
    __tablename__ = "formula_evidence"
    __table_args__ = (
        UniqueConstraint("formula_revision_id", "evidence_revision_id", name="uq_formula_evidence"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    formula_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.formula_revision.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )


class QualityIssue(Base):
    __tablename__ = "quality_issue"
    __table_args__ = (
        Index("ix_quality_issue_open", "status", "severity", "target_kind", "target_id"),
        {"schema": "governance"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HumanReview(Base):
    __tablename__ = "human_review"
    __table_args__ = (Index("ix_human_review_target", "target_kind", "target_id"),
                      {"schema": "governance"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_version"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_knowledge_version_public_id"),
        UniqueConstraint("version_no", name="uq_knowledge_version_no"),
        {"schema": "governance"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeVersionItem(Base):
    __tablename__ = "knowledge_version_item"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(evidence_revision_id, formula_revision_id, concept_id, "
            "relation_id, herb_id) = 1", name="ck_knowledge_item_one_object"
        ),
        UniqueConstraint("knowledge_version_id", "evidence_revision_id", name="uq_kv_evidence"),
        UniqueConstraint("knowledge_version_id", "formula_revision_id", name="uq_kv_formula"),
        UniqueConstraint("knowledge_version_id", "concept_id", name="uq_kv_concept"),
        UniqueConstraint("knowledge_version_id", "relation_id", name="uq_kv_relation"),
        UniqueConstraint("knowledge_version_id", "herb_id", name="uq_kv_herb"),
        {"schema": "governance"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    knowledge_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.knowledge_version.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id")
    )
    formula_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.formula_revision.id")
    )
    concept_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.concept.id")
    )
    relation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.relation.id")
    )
    herb_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.herb.id")
    )


class IndexBuild(Base):
    __tablename__ = "index_build"
    __table_args__ = (Index("ix_index_build_version", "knowledge_version_id", "status"),
                      {"schema": "governance"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    knowledge_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.knowledge_version.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    fts_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    vector_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeRuntimeState(Base):
    __tablename__ = "knowledge_runtime_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_knowledge_runtime_singleton"),
        CheckConstraint(
            "(active_knowledge_version_id IS NULL) = (active_index_build_id IS NULL)",
            name="ck_knowledge_runtime_pointer_pair",
        ),
        {"schema": "governance"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_knowledge_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.knowledge_version.id")
    )
    active_index_build_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.index_build.id")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalChunk(Base):
    __tablename__ = "retrieval_chunk"
    __table_args__ = (
        UniqueConstraint("index_build_id", "evidence_revision_id", name="uq_chunk_build_evidence"),
        Index("ix_chunk_fts", "search_vector", postgresql_using="gin"),
        Index("ix_chunk_trgm", "chunk_text", postgresql_using="gin",
              postgresql_ops={"chunk_text": "gin_trgm_ops"}),
        Index("ix_chunk_build", "index_build_id"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    index_build_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.index_build.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )
    source_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("source.source_revision.id"), nullable=False
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', token_text)", persisted=True), nullable=False
    )
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EmbeddingRecord(Base):
    __tablename__ = "embedding_record"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_embedding_chunk"),
        Index("ix_embedding_build", "index_build_id"),
        {"schema": "knowledge"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    index_build_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.index_build.id"), nullable=False
    )
    chunk_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.retrieval_chunk.id"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[str] = mapped_column(Vector(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalGoldenQuery(Base):
    __tablename__ = "retrieval_golden_query"
    __table_args__ = (UniqueConstraint("public_id", name="uq_golden_query_public_id"),
                      {"schema": "governance"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_scope: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalGoldenJudgment(Base):
    __tablename__ = "retrieval_golden_judgment"
    __table_args__ = (
        UniqueConstraint("query_id", "evidence_revision_id", name="uq_golden_judgment"),
        {"schema": "governance"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    query_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.retrieval_golden_query.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)


class RetrievalBenchmarkRun(Base):
    __tablename__ = "retrieval_benchmark_run"
    __table_args__ = ({"schema": "governance"},)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    knowledge_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.knowledge_version.id"), nullable=False
    )
    index_build_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("governance.index_build.id"), nullable=False
    )
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ResearchTask(Base):
    __tablename__ = "research_task"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_research_task_public_id"),
        Index("ix_research_task_status", "status", "created_at"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(80), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="CREATED")
    control_state: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    draft_scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    execution_context: Mapped[dict | None] = mapped_column(JSONB)
    run_fingerprint: Mapped[str | None] = mapped_column(String(64))
    interrupted_stage: Mapped[str | None] = mapped_column(String(40))
    resume_stage: Mapped[str | None] = mapped_column(String(40))
    waiting_reason_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchSubquestion(Base):
    __tablename__ = "sub_question"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence_no", name="uq_sub_question_order"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)


class TaskEvidenceRef(Base):
    __tablename__ = "task_evidence_ref"
    __table_args__ = (
        UniqueConstraint("task_id", "evidence_revision_id", name="uq_task_evidence_member"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceRetrievalEvent(Base):
    __tablename__ = "evidence_retrieval_event"
    __table_args__ = (
        Index("ix_retrieval_event_task", "task_id", "created_at"),
        UniqueConstraint("evidence_request_id", "evidence_revision_id",
                         name="uq_retrieval_request_revision"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("knowledge.evidence_revision.id"), nullable=False
    )
    evidence_request_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.evidence_request.id",
                                         name="fk_retrieval_event_request")
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_run"
    __table_args__ = (
        UniqueConstraint("task_id", "role", "round_no", name="uq_agent_run_round"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    visible_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelInvocation(Base):
    __tablename__ = "model_invocation"
    __table_args__ = (
        Index("ix_model_invocation_task", "task_id", "created_at"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.agent_run.id")
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(500))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64))
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Claim(Base):
    __tablename__ = "claim"
    __table_args__ = (Index("ix_claim_task_role", "task_id", "agent_role"),
                      {"schema": "research"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.agent_run.id"), nullable=False
    )
    parent_claim_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id")
    )
    agent_role: Mapped[str] = mapped_column(String(50), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), nullable=False)
    assertion_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    audit_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (UniqueConstraint("claim_id", "task_evidence_ref_id", name="uq_claim_evidence"),
                      {"schema": "research"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id"), nullable=False
    )
    task_evidence_ref_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.task_evidence_ref.id"), nullable=False
    )


class AuditResult(Base):
    __tablename__ = "audit_result"
    __table_args__ = (
        UniqueConstraint("claim_id", "sequence_no", name="uq_audit_claim_sequence"),
        Index("ix_audit_result_task", "task_id", "created_at"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    verdict: Mapped[str] = mapped_column(String(40), nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_revision_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Critique(Base):
    __tablename__ = "critique"
    __table_args__ = (Index("ix_critique_task_claim", "task_id", "target_claim_id"),
                      {"schema": "research"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.agent_run.id"), nullable=False
    )
    target_claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id"), nullable=False
    )
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceRequest(Base):
    __tablename__ = "evidence_request"
    __table_args__ = (Index("ix_evidence_request_task_status", "task_id", "status"),
                      {"schema": "research"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    critique_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.critique.id"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    result_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Rebuttal(Base):
    __tablename__ = "rebuttal"
    __table_args__ = (
        UniqueConstraint("critique_id", "round_no", name="uq_rebuttal_critique_round"),
        CheckConstraint("(action = 'REVISE' AND revised_claim_id IS NOT NULL) OR "
                        "(action <> 'REVISE' AND revised_claim_id IS NULL)"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    critique_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.critique.id"), nullable=False
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.agent_run.id"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    revised_claim_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalClaim(Base):
    __tablename__ = "canonical_claim"
    __table_args__ = (
        UniqueConstraint("task_id", "fingerprint", name="uq_canonical_claim_fingerprint"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), nullable=False)
    assertion_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_context: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CanonicalClaimMember(Base):
    __tablename__ = "canonical_claim_member"
    __table_args__ = (
        UniqueConstraint("claim_id", name="uq_canonical_claim_member_claim"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    canonical_claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.canonical_claim.id"), nullable=False
    )
    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id"), nullable=False
    )
    audit_result_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.audit_result.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Dispute(Base):
    __tablename__ = "dispute"
    __table_args__ = (
        UniqueConstraint("task_id", "source_key", name="uq_dispute_source"),
        Index("ix_dispute_task", "task_id", "created_at"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.canonical_claim.id"), nullable=False
    )
    target_claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id"), nullable=False
    )
    competing_claim_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id")
    )
    critique_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.critique.id")
    )
    audit_result_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.audit_result.id")
    )
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    opposing_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceGap(Base):
    __tablename__ = "evidence_gap"
    __table_args__ = (
        UniqueConstraint("task_id", "source_key", name="uq_evidence_gap_source"),
        Index("ix_evidence_gap_task", "task_id", "created_at"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.claim.id"), nullable=False
    )
    critique_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.critique.id")
    )
    audit_result_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.audit_result.id")
    )
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    rationale_summary: Mapped[str] = mapped_column(Text, nullable=False)
    cited_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StopEvaluation(Base):
    __tablename__ = "stop_evaluation"
    __table_args__ = (
        UniqueConstraint("task_id", "round_no", "input_hash", name="uq_stop_evaluation_input"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class HumanReviewRequest(Base):
    __tablename__ = "human_review_request"
    __table_args__ = (
        UniqueConstraint("task_id", "source_key", name="uq_human_review_request_source"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    stop_evaluation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.stop_evaluation.id"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    interrupted_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    resume_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchSynthesis(Base):
    __tablename__ = "research_synthesis"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_research_synthesis_task"),
        UniqueConstraint("judge_run_id", name="uq_research_synthesis_run"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    judge_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.agent_run.id"), nullable=False
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    findings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StructuredReport(Base):
    __tablename__ = "structured_report"
    __table_args__ = (UniqueConstraint("task_id", name="uq_structured_report_task"),
                      {"schema": "research"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    synthesis_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_synthesis.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReportExport(Base):
    __tablename__ = "report_export"
    __table_args__ = (
        UniqueConstraint("report_id", "file_format", "renderer_version",
                         name="uq_report_export_version"),
        UniqueConstraint("job_id", name="uq_report_export_job"),
        {"schema": "research"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    report_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.structured_report.id"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research.research_task.id"), nullable=False
    )
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(40), nullable=False)
    process_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("runtime.task_job.id"), nullable=False
    )
    artifact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("storage.artifact.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

