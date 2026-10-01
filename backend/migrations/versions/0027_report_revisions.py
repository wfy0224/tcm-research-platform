"""Keep reviewed and revision-required report snapshots without overwriting them."""

import sqlalchemy as sa
from alembic import op

revision = "0027_report_revisions"
down_revision = "0026_term_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("structured_report", sa.Column(
        "revision_no", sa.Integer(), nullable=False, server_default="1"), schema="research")
    op.drop_constraint("uq_structured_report_task", "structured_report",
                       schema="research", type_="unique")
    op.create_unique_constraint("uq_structured_report_revision", "structured_report",
                                ["task_id", "revision_no"], schema="research")


def downgrade() -> None:
    duplicates = op.get_bind().scalar(sa.text(
        "SELECT EXISTS(SELECT 1 FROM research.structured_report GROUP BY task_id HAVING count(*) > 1)"))
    if duplicates:
        raise RuntimeError("report revisions exist; downgrade would discard saved research")
    op.drop_constraint("uq_structured_report_revision", "structured_report",
                       schema="research", type_="unique")
    op.create_unique_constraint("uq_structured_report_task", "structured_report",
                                ["task_id"], schema="research")
    op.drop_column("structured_report", "revision_no", schema="research")
