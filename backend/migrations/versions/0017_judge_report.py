"""Persist immutable Judge synthesis and structured reports.

Revision ID: 0017_judge_report
Revises: 0016_stop_review
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_judge_report"
down_revision = "0016_stop_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_synthesis",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("judge_run_id", sa.UUID(), sa.ForeignKey("research.agent_run.id"), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("findings", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_research_synthesis_task"),
        sa.UniqueConstraint("judge_run_id", name="uq_research_synthesis_run"),
        schema="research",
    )
    op.create_table(
        "structured_report",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("synthesis_id", sa.UUID(),
                  sa.ForeignKey("research.research_synthesis.id"), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_structured_report_task"),
        schema="research",
    )
    op.execute("""
        CREATE FUNCTION research.reject_immutable_report_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'research report records are immutable';
        END;
        $$
    """)
    for table in ("research_synthesis", "structured_report"):
        op.execute(f"""
            CREATE TRIGGER immutable_{table}
            BEFORE UPDATE OR DELETE ON research.{table}
            FOR EACH ROW EXECUTE FUNCTION research.reject_immutable_report_mutation()
        """)


def downgrade() -> None:
    op.drop_table("structured_report", schema="research")
    op.drop_table("research_synthesis", schema="research")
    op.execute("DROP FUNCTION research.reject_immutable_report_mutation()")
