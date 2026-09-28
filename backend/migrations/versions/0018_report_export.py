"""Track versioned derived report files independently of research completion.

Revision ID: 0018_report_export
Revises: 0017_judge_report
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_report_export"
down_revision = "0017_judge_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_export",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("report_id", sa.UUID(),
                  sa.ForeignKey("research.structured_report.id"), nullable=False),
        sa.Column("task_id", sa.UUID(),
                  sa.ForeignKey("research.research_task.id"), nullable=False),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("renderer_version", sa.String(40), nullable=False),
        sa.Column("process_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("job_id", sa.UUID(), sa.ForeignKey("runtime.task_job.id"), nullable=False),
        sa.Column("artifact_id", sa.UUID(), sa.ForeignKey("storage.artifact.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("report_id", "file_format", "renderer_version",
                            name="uq_report_export_version"),
        sa.UniqueConstraint("job_id", name="uq_report_export_job"),
        schema="research",
    )


def downgrade() -> None:
    op.drop_table("report_export", schema="research")
