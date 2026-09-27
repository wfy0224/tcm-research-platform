"""E2 source identity, immutable revisions, import tracking.

Revision ID: 0002_source_import
Revises: 0001_foundation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_source_import"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(300)),
        sa.Column("era", sa.String(120)),
        sa.Column("school", sa.String(120)),
        sa.Column("edition", sa.String(300)),
        sa.Column("publisher", sa.String(300)),
        sa.Column("publication_year", sa.Integer()),
        sa.Column("language", sa.String(30), nullable=False),
        sa.Column("copyright_status", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_source_public_id"),
        schema="source",
    )
    op.create_table(
        "source_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_document.id"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_format", sa.String(20), nullable=False),
        sa.Column("metadata_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "revision_no", name="uq_source_revision_no"),
        schema="source",
    )
    op.create_index("ix_source_revision_hash", "source_revision", ["file_sha256"], schema="source")
    op.create_table(
        "file_asset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_revision.id"), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("storage.artifact.id"), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_revision_id", "role", "sequence_no", name="uq_file_asset_role"),
        schema="source",
    )
    op.create_table(
        "import_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_key", sa.String(200), nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_revision.id"), nullable=False),
        sa.Column("task_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime.task_job.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("parsed_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("storage.artifact.id")),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_key", name="uq_import_request_key"),
        sa.UniqueConstraint("task_job_id", name="uq_import_task_job"),
        schema="source",
    )
    op.create_index("ix_import_job_status", "import_job", ["status", "created_at"], schema="source")
    op.create_table(
        "pipeline_step_execution",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.import_job.id"), nullable=False),
        sa.Column("step", sa.String(60), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("tool_version", sa.String(80), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("output_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("storage.artifact.id")),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("import_job_id", "step", "attempt", name="uq_import_step_attempt"),
        schema="source",
    )


def downgrade() -> None:
    op.drop_table("pipeline_step_execution", schema="source")
    op.drop_index("ix_import_job_status", table_name="import_job", schema="source")
    op.drop_table("import_job", schema="source")
    op.drop_table("file_asset", schema="source")
    op.drop_index("ix_source_revision_hash", table_name="source_revision", schema="source")
    op.drop_table("source_revision", schema="source")
    op.drop_table("source_document", schema="source")

