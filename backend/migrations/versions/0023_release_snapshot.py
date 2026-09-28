"""Bind a release switch to a content-addressed rollback manifest.

Revision ID: 0023_release_snapshot
Revises: 0022_reference_manifest
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_release_snapshot"
down_revision = "0022_reference_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_snapshot",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_knowledge_version_id", sa.UUID(), nullable=False),
        sa.Column("source_index_build_id", sa.UUID(), nullable=False),
        sa.Column("target_knowledge_version_id", sa.UUID(), nullable=False),
        sa.Column("target_index_build_id", sa.UUID(), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_knowledge_version_id"],
                                ["governance.knowledge_version.id"]),
        sa.ForeignKeyConstraint(["source_index_build_id"], ["governance.index_build.id"]),
        sa.ForeignKeyConstraint(["target_knowledge_version_id"],
                                ["governance.knowledge_version.id"]),
        sa.ForeignKeyConstraint(["target_index_build_id"], ["governance.index_build.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["storage.artifact.id"]),
        schema="governance",
    )
    op.execute("""
        CREATE FUNCTION governance.reject_release_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'release snapshot records are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER immutable_release_snapshot
        BEFORE UPDATE OR DELETE ON governance.release_snapshot
        FOR EACH ROW EXECUTE FUNCTION governance.reject_release_snapshot_mutation()
    """)


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM governance.release_snapshot"
    )).scalar_one():
        raise RuntimeError("cannot downgrade while release snapshots exist")
    op.execute("DROP TRIGGER IF EXISTS immutable_release_snapshot "
               "ON governance.release_snapshot")
    op.execute("DROP FUNCTION IF EXISTS governance.reject_release_snapshot_mutation()")
    op.drop_table("release_snapshot", schema="governance")
