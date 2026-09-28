"""Freeze historical evidence citations alongside active version members.

Revision ID: 0022_reference_manifest
Revises: 0021_knowledge_supersession
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_reference_manifest"
down_revision = "0021_knowledge_supersession"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_version", sa.Column(
        "reference_manifest_hash", sa.String(64), nullable=True
    ), schema="governance")
    op.create_table(
        "knowledge_version_reference",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("knowledge_version_id", sa.UUID(), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("evidence_revision_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_version_id"], ["governance.knowledge_version.id"]),
        sa.ForeignKeyConstraint(["evidence_revision_id"], ["knowledge.evidence_revision.id"]),
        sa.UniqueConstraint("knowledge_version_id", "target_kind", "target_id",
                            "evidence_revision_id", name="uq_kv_reference"),
        schema="governance",
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM governance.knowledge_version "
        "WHERE reference_manifest_hash IS NOT NULL"
    )).scalar_one():
        raise RuntimeError("cannot downgrade while reference manifests exist")
    op.drop_table("knowledge_version_reference", schema="governance")
    op.drop_column("knowledge_version", "reference_manifest_hash", schema="governance")
