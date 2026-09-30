"""Freeze local candidate extraction outputs for atomic, idempotent replay.

Revision ID: 0024_knowledge_extraction
Revises: 0023_release_snapshot
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_knowledge_extraction"
down_revision = "0023_release_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_extraction",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_revision_id", sa.UUID(), nullable=False),
        sa.Column("extractor_version", sa.String(80), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source.source_revision.id"]),
        sa.UniqueConstraint("source_revision_id", "extractor_version",
                            name="uq_extraction_source_rule"),
        schema="knowledge",
    )
    op.execute("""
        CREATE FUNCTION knowledge.reject_extraction_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'knowledge extraction manifests are immutable';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER immutable_knowledge_extraction
        BEFORE UPDATE OR DELETE ON knowledge.knowledge_extraction
        FOR EACH ROW EXECUTE FUNCTION knowledge.reject_extraction_mutation();
    """)


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM knowledge.knowledge_extraction"
    )).scalar_one():
        raise RuntimeError("cannot downgrade while extraction manifests exist")
    op.drop_table("knowledge_extraction", schema="knowledge")
    op.execute("DROP FUNCTION knowledge.reject_extraction_mutation()")
