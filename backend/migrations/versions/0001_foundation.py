"""E0/E1 storage, audit, and persistent job foundation.

Revision ID: 0001_foundation
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("storage", "source", "knowledge", "research", "runtime", "governance"):
        op.execute(sa.schema.CreateSchema(schema, if_not_exists=True))

    op.create_table(
        "blob_object",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes >= 0"),
        schema="storage",
    )
    op.create_table(
        "artifact",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("blob_sha256", sa.String(64), sa.ForeignKey("storage.blob_object.sha256"), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("retention_class", sa.String(64), nullable=False),
        sa.Column("original_name", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="storage",
    )
    op.create_index("ix_artifact_blob", "artifact", ["blob_sha256"], schema="storage")

    op.create_table(
        "event_log_head",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("last_hash", sa.String(64), nullable=False),
        sa.CheckConstraint("id = 1"),
        schema="governance",
    )
    op.execute(
        "INSERT INTO governance.event_log_head (id, sequence_no, last_hash) "
        "VALUES (1, 0, '" + "0" * 64 + "')"
    )
    op.create_table(
        "event_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("actor_id", sa.String(120), nullable=False),
        sa.Column("aggregate_id", sa.String(120), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sequence_no", name="uq_event_sequence"),
        schema="governance",
    )

    op.create_table(
        "task_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("resource_class", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("execution_generation", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_job_idempotency_key"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1"),
        schema="runtime",
    )
    op.create_index(
        "ix_task_job_claim",
        "task_job",
        ["status", "available_at", "priority", "created_at"],
        schema="runtime",
    )
    op.create_index("ix_task_job_lease", "task_job", ["status", "lease_expires_at"], schema="runtime")
    op.create_table(
        "task_checkpoint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime.task_job.id"), nullable=False),
        sa.Column("execution_generation", sa.Integer(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "execution_generation", name="uq_checkpoint_generation"),
        schema="runtime",
    )
    op.create_table(
        "backup_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        schema="governance",
    )


def downgrade() -> None:
    # Development-only rollback. Production recovery uses verified backup/snapshot.
    op.drop_table("backup_record", schema="governance")
    op.drop_table("task_checkpoint", schema="runtime")
    op.drop_index("ix_task_job_lease", table_name="task_job", schema="runtime")
    op.drop_index("ix_task_job_claim", table_name="task_job", schema="runtime")
    op.drop_table("task_job", schema="runtime")
    op.drop_table("event_log", schema="governance")
    op.drop_table("event_log_head", schema="governance")
    op.drop_index("ix_artifact_blob", table_name="artifact", schema="storage")
    op.drop_table("artifact", schema="storage")
    op.drop_table("blob_object", schema="storage")
    for schema in ("governance", "runtime", "research", "knowledge", "source", "storage"):
        op.execute(sa.schema.DropSchema(schema, if_exists=True))

