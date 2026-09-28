"""Persist one-use loopback bootstrap grants, sessions, and public job IDs.

Revision ID: 0019_local_session_api
Revises: 0018_report_export
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_local_session_api"
down_revision = "0018_report_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_job", sa.Column("public_id", sa.String(80)), schema="runtime")
    op.execute("UPDATE runtime.task_job SET public_id = 'JOB-' || gen_random_uuid()::text")
    op.alter_column("task_job", "public_id", nullable=False, schema="runtime")
    op.create_unique_constraint("uq_task_job_public_id", "task_job", ["public_id"],
                                schema="runtime")
    op.create_table(
        "local_bootstrap_grant",
        sa.Column("secret_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="governance",
    )
    op.create_table(
        "local_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(120), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_local_session_public_id"),
        sa.UniqueConstraint("token_hash", name="uq_local_session_token_hash"),
        schema="governance",
    )


def downgrade() -> None:
    op.drop_table("local_session", schema="governance")
    op.drop_table("local_bootstrap_grant", schema="governance")
    op.drop_constraint("uq_task_job_public_id", "task_job", schema="runtime")
    op.drop_column("task_job", "public_id", schema="runtime")
