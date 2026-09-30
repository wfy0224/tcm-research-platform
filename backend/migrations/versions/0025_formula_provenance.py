"""Freeze field-level provenance for newly authored formula revisions.

Revision ID: 0025_formula_provenance
Revises: 0024_knowledge_extraction
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_formula_provenance"
down_revision = "0024_knowledge_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adding with default zero preserves legacy reviewed rows without rebuilding them.
    op.add_column("formula_revision", sa.Column(
        "provenance_version", sa.Integer(), nullable=False, server_default="0"
    ), schema="knowledge")
    op.alter_column("formula_revision", "provenance_version", server_default="1",
                    schema="knowledge")
    op.create_table(
        "formula_field_source",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("formula_revision_id", sa.UUID(), nullable=False),
        sa.Column("field_key", sa.String(120), nullable=False),
        sa.Column("value_snapshot", sa.Text(), nullable=False),
        sa.Column("evidence_revision_id", sa.UUID(), nullable=False),
        sa.Column("segment_revision_id", sa.UUID(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("segment_checksum", sa.String(64), nullable=False),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["formula_revision_id"], ["knowledge.formula_revision.id"]),
        sa.ForeignKeyConstraint(["evidence_revision_id"], ["knowledge.evidence_revision.id"]),
        sa.ForeignKeyConstraint(["segment_revision_id"], ["source.text_segment_revision.id"]),
        sa.CheckConstraint("start_offset >= 0 AND end_offset > start_offset",
                           name="ck_formula_field_source_span"),
        sa.UniqueConstraint("formula_revision_id", "field_key", "evidence_revision_id",
                            "segment_revision_id", "start_offset", "end_offset",
                            name="uq_formula_field_source_span"),
        schema="knowledge",
    )
    op.create_index("ix_formula_field_source_revision", "formula_field_source",
                    ["formula_revision_id"], schema="knowledge")
    op.execute("""
        CREATE FUNCTION knowledge.guard_formula_field_source() RETURNS trigger AS $$
        DECLARE parent_status text; parent_version integer;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'formula field sources are immutable';
            END IF;
            SELECT status, provenance_version INTO parent_status, parent_version
              FROM knowledge.formula_revision WHERE id = NEW.formula_revision_id FOR UPDATE;
            IF NOT FOUND OR parent_status <> 'DRAFT' OR parent_version <> 1
               OR EXISTS (SELECT 1 FROM governance.knowledge_version_item
                          WHERE formula_revision_id = NEW.formula_revision_id)
               OR EXISTS (SELECT 1 FROM governance.human_review
                          WHERE target_kind = 'formula_revision'
                            AND target_id = NEW.formula_revision_id AND decision = 'APPROVE') THEN
                RAISE EXCEPTION 'formula field sources require an unfrozen provenance draft';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER immutable_formula_field_source
        BEFORE INSERT OR UPDATE OR DELETE ON knowledge.formula_field_source
        FOR EACH ROW EXECUTE FUNCTION knowledge.guard_formula_field_source();

        CREATE FUNCTION knowledge.guard_formula_revision() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.provenance_version <> 1 THEN
                    RAISE EXCEPTION 'new formula revisions require provenance version 1';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.provenance_version IS DISTINCT FROM OLD.provenance_version THEN
                RAISE EXCEPTION 'formula provenance version is immutable; create a new draft';
            END IF;
            IF OLD.status = 'REVIEWED'
               OR EXISTS (SELECT 1 FROM governance.knowledge_version_item
                          WHERE formula_revision_id = OLD.id)
               OR EXISTS (SELECT 1 FROM governance.human_review
                          WHERE target_kind = 'formula_revision'
                            AND target_id = OLD.id AND decision = 'APPROVE') THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'reviewed or snapshotted formula revisions are immutable';
                END IF;
                IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
                    RAISE EXCEPTION 'reviewed or snapshotted formula revisions are immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER frozen_formula_revision
        BEFORE INSERT OR UPDATE OR DELETE ON knowledge.formula_revision
        FOR EACH ROW EXECUTE FUNCTION knowledge.guard_formula_revision();

        CREATE FUNCTION knowledge.guard_formula_component() RETURNS trigger AS $$
        DECLARE parent_id uuid; parent_status text;
        BEGIN
            -- A reparenting UPDATE must check both the old and the new revision.
            FOR parent_id IN
                SELECT DISTINCT candidate FROM (VALUES
                    (CASE WHEN TG_OP <> 'INSERT' THEN OLD.formula_revision_id END),
                    (CASE WHEN TG_OP <> 'DELETE' THEN NEW.formula_revision_id END)
                ) AS parents(candidate) WHERE candidate IS NOT NULL ORDER BY candidate
            LOOP
                SELECT status INTO parent_status FROM knowledge.formula_revision
                  WHERE id = parent_id FOR UPDATE;
                IF parent_status = 'REVIEWED'
                   OR EXISTS (SELECT 1 FROM governance.knowledge_version_item
                              WHERE formula_revision_id = parent_id)
                   OR EXISTS (SELECT 1 FROM governance.human_review
                              WHERE target_kind = 'formula_revision'
                                AND target_id = parent_id AND decision = 'APPROVE') THEN
                    RAISE EXCEPTION 'reviewed or snapshotted formula components are immutable';
                END IF;
            END LOOP;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER frozen_formula_ingredient
        BEFORE INSERT OR UPDATE OR DELETE ON knowledge.formula_ingredient
        FOR EACH ROW EXECUTE FUNCTION knowledge.guard_formula_component();
        CREATE TRIGGER frozen_formula_evidence
        BEFORE INSERT OR UPDATE OR DELETE ON knowledge.formula_evidence
        FOR EACH ROW EXECUTE FUNCTION knowledge.guard_formula_component();
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM knowledge.formula_field_source) OR "
        "EXISTS (SELECT 1 FROM knowledge.formula_revision WHERE provenance_version <> 0)"
    )).scalar_one():
        raise RuntimeError("cannot downgrade while formula provenance drafts or field sources exist")
    op.execute("""
        DROP TRIGGER frozen_formula_evidence ON knowledge.formula_evidence;
        DROP TRIGGER frozen_formula_ingredient ON knowledge.formula_ingredient;
        DROP FUNCTION knowledge.guard_formula_component();
        DROP TRIGGER frozen_formula_revision ON knowledge.formula_revision;
        DROP FUNCTION knowledge.guard_formula_revision();
        DROP TRIGGER immutable_formula_field_source ON knowledge.formula_field_source;
        DROP FUNCTION knowledge.guard_formula_field_source();
    """)
    op.drop_table("formula_field_source", schema="knowledge")
    op.drop_column("formula_revision", "provenance_version", schema="knowledge")
