"""Prevent duplicate evidence events for one debate request.

Revision ID: 0013_retrieval_request_unique
Revises: 0012_debate
"""

from alembic import op

revision = "0013_retrieval_request_unique"
down_revision = "0012_debate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_retrieval_request_revision", "evidence_retrieval_event",
        ["evidence_request_id", "evidence_revision_id"], schema="research",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_retrieval_request_revision", "evidence_retrieval_event",
        schema="research", type_="unique",
    )
