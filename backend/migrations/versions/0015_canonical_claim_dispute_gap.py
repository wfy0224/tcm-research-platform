"""Persist claim normalization, disputes, and evidence gaps.

Revision ID: 0015_canonical_claim_dispute_gap
Revises: 0014_research_node_checkpoints
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_canonical_claim_dispute_gap"
down_revision = "0014_research_node_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_claim",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("claim_type", sa.String(40), nullable=False),
        sa.Column("assertion_text", sa.Text(), nullable=False),
        sa.Column("source_context", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "fingerprint", name="uq_canonical_claim_fingerprint"),
        schema="research",
    )
    op.create_table(
        "canonical_claim_member",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("canonical_claim_id", sa.UUID(),
                  sa.ForeignKey("research.canonical_claim.id"), nullable=False),
        sa.Column("claim_id", sa.UUID(), sa.ForeignKey("research.claim.id"), nullable=False),
        sa.Column("audit_result_id", sa.UUID(),
                  sa.ForeignKey("research.audit_result.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("claim_id", name="uq_canonical_claim_member_claim"),
        schema="research",
    )
    op.create_table(
        "dispute",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("canonical_claim_id", sa.UUID(),
                  sa.ForeignKey("research.canonical_claim.id"), nullable=False),
        sa.Column("target_claim_id", sa.UUID(), sa.ForeignKey("research.claim.id"), nullable=False),
        sa.Column("competing_claim_id", sa.UUID(), sa.ForeignKey("research.claim.id")),
        sa.Column("critique_id", sa.UUID(), sa.ForeignKey("research.critique.id")),
        sa.Column("audit_result_id", sa.UUID(), sa.ForeignKey("research.audit_result.id")),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("rationale_summary", sa.Text(), nullable=False),
        sa.Column("supporting_evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("opposing_evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "source_key", name="uq_dispute_source"),
        schema="research",
    )
    op.create_index("ix_dispute_task", "dispute", ["task_id", "created_at"], schema="research")
    op.create_table(
        "evidence_gap",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("claim_id", sa.UUID(), sa.ForeignKey("research.claim.id"), nullable=False),
        sa.Column("critique_id", sa.UUID(), sa.ForeignKey("research.critique.id")),
        sa.Column("audit_result_id", sa.UUID(), sa.ForeignKey("research.audit_result.id")),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("rationale_summary", sa.Text(), nullable=False),
        sa.Column("cited_evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "source_key", name="uq_evidence_gap_source"),
        schema="research",
    )
    op.create_index("ix_evidence_gap_task", "evidence_gap", ["task_id", "created_at"],
                    schema="research")


def downgrade() -> None:
    op.drop_index("ix_evidence_gap_task", table_name="evidence_gap", schema="research")
    op.drop_table("evidence_gap", schema="research")
    op.drop_index("ix_dispute_task", table_name="dispute", schema="research")
    op.drop_table("dispute", schema="research")
    op.drop_table("canonical_claim_member", schema="research")
    op.drop_table("canonical_claim", schema="research")
