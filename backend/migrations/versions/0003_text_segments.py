"""E3 stable text segment identities, immutable revisions, and alignment.

Revision ID: 0003_text_segments
Revises: 0002_source_import
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_text_segments"
down_revision = "0002_source_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "text_segment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("public_id", sa.String(80), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_document.id"), nullable=False),
        sa.Column("segment_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_text_segment_public_id"),
        schema="source",
    )
    op.create_index("ix_text_segment_source", "text_segment", ["source_id"], schema="source")
    op.create_table(
        "text_segment_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.text_segment.id"), nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_revision.id"), nullable=False),
        sa.Column("parent_segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.text_segment.id")),
        sa.Column("segment_type", sa.String(30), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("context_before", sa.Text(), nullable=False),
        sa.Column("context_after", sa.Text(), nullable=False),
        sa.Column("page_no", sa.Integer()),
        sa.Column("chapter_no", sa.Integer()),
        sa.Column("paragraph_no", sa.Integer()),
        sa.Column("structural_locator", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("segment_id", "source_revision_id", name="uq_segment_source_revision"),
        sa.UniqueConstraint("source_revision_id", "sequence_no", name="uq_segment_sequence"),
        schema="source",
    )
    op.create_index("ix_segment_revision_locator", "text_segment_revision", ["source_revision_id", "page_no", "paragraph_no"], schema="source")
    op.create_index("ix_segment_revision_checksum", "text_segment_revision", ["checksum"], schema="source")
    op.create_table(
        "segment_alignment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_revision.id"), nullable=False),
        sa.Column("to_source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.source_revision.id"), nullable=False),
        sa.Column("old_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.text_segment_revision.id")),
        sa.Column("new_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source.text_segment_revision.id")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("old_revision_id IS NOT NULL OR new_revision_id IS NOT NULL"),
        schema="source",
    )
    op.create_index("ix_alignment_from_to", "segment_alignment", ["from_source_revision_id", "to_source_revision_id"], schema="source")


def downgrade() -> None:
    op.drop_index("ix_alignment_from_to", table_name="segment_alignment", schema="source")
    op.drop_table("segment_alignment", schema="source")
    op.drop_index("ix_segment_revision_checksum", table_name="text_segment_revision", schema="source")
    op.drop_index("ix_segment_revision_locator", table_name="text_segment_revision", schema="source")
    op.drop_table("text_segment_revision", schema="source")
    op.drop_index("ix_text_segment_source", table_name="text_segment", schema="source")
    op.drop_table("text_segment", schema="source")
