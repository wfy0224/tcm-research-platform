"""Allow multiple atomic research node checkpoints per job generation.

Revision ID: 0014_research_node_checkpoints
Revises: 0013_retrieval_request_unique
"""

from alembic import op
from sqlalchemy import text

revision = "0014_research_node_checkpoints"
down_revision = "0013_retrieval_request_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_checkpoint_generation", "task_checkpoint",
                       schema="runtime", type_="unique")
    op.create_index("ix_checkpoint_job_generation", "task_checkpoint",
                    ["job_id", "execution_generation", "created_at"], schema="runtime")


def downgrade() -> None:
    duplicate = op.get_bind().execute(text("""
        SELECT 1 FROM runtime.task_checkpoint
        GROUP BY job_id, execution_generation HAVING count(*) > 1 LIMIT 1
    """)).scalar()
    if duplicate is not None:
        raise RuntimeError("cannot restore the old checkpoint constraint while node history exists")
    op.drop_index("ix_checkpoint_job_generation", table_name="task_checkpoint",
                  schema="runtime")
    op.create_unique_constraint("uq_checkpoint_generation", "task_checkpoint",
                                ["job_id", "execution_generation"], schema="runtime")
