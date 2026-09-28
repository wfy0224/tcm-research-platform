"""Persist frozen stopping decisions and resumable human review.

Revision ID: 0016_stop_review
Revises: 0015_canonical_claim_dispute_gap
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_stop_review"
down_revision = "0015_canonical_claim_dispute_gap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("interrupted_stage", "resume_stage", "waiting_reason_code"):
        op.add_column("research_task", sa.Column(column, sa.String(40)), schema="research")
    op.create_table(
        "stop_evaluation",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "round_no", "input_hash", name="uq_stop_evaluation_input"),
        schema="research",
    )
    op.create_table(
        "human_review_request",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("stop_evaluation_id", sa.UUID(),
                  sa.ForeignKey("research.stop_evaluation.id"), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("interrupted_stage", sa.String(40), nullable=False),
        sa.Column("resume_stage", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_by", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_id", "source_key", name="uq_human_review_request_source"),
        schema="research",
    )


def downgrade() -> None:
    op.drop_table("human_review_request", schema="research")
    op.drop_table("stop_evaluation", schema="research")
    for column in ("waiting_reason_code", "resume_stage", "interrupted_stage"):
        op.drop_column("research_task", column, schema="research")
