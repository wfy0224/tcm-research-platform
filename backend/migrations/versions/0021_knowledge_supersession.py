"""Record append-only reviewed knowledge replacements.

Revision ID: 0021_knowledge_supersession
Revises: 0020_outbound_source_policy
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_knowledge_supersession"
down_revision = "0020_outbound_source_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_supersession",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("target_kind", sa.String(40), nullable=False),
        sa.Column("old_object_id", sa.UUID(), nullable=False),
        sa.Column("new_object_id", sa.UUID(), nullable=False),
        sa.Column("root_object_id", sa.UUID(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("target_kind", "old_object_id", name="uq_supersession_old"),
        sa.UniqueConstraint("target_kind", "new_object_id", name="uq_supersession_new"),
        sa.UniqueConstraint("target_kind", "root_object_id", "revision_no",
                            name="uq_supersession_revision"),
        schema="governance",
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM governance.knowledge_supersession"
    )).scalar_one():
        raise RuntimeError("cannot downgrade while knowledge revision lineage exists")
    op.drop_table("knowledge_supersession", schema="governance")
