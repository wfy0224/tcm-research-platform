"""Append-only term adjudication and frozen source-scoped concept revisions.

Revision ID: 0026_term_resolution
Revises: 0025_formula_provenance
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_term_resolution"
down_revision = "0025_formula_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("concept", sa.Column(
        "requires_term_resolution", sa.Boolean(), nullable=False, server_default=sa.false()
    ), schema="knowledge")
    op.create_table(
        "term_resolution",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_concept_id", sa.UUID(), nullable=False),
        sa.Column("resolved_concept_id", sa.UUID(), nullable=False),
        sa.Column("related_concept_id", sa.UUID(), nullable=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(120), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_concept_id"], ["knowledge.concept.id"]),
        sa.ForeignKeyConstraint(["resolved_concept_id"], ["knowledge.concept.id"]),
        sa.ForeignKeyConstraint(["related_concept_id"], ["knowledge.concept.id"]),
        sa.UniqueConstraint("resolved_concept_id", name="uq_term_resolution_concept"),
        sa.CheckConstraint("source_concept_id <> resolved_concept_id", name="ck_term_resolution_new"),
        sa.CheckConstraint("decision IN ('NORMALIZE', 'HISTORICAL_SYNONYM', 'DISTINCT', 'UNRESOLVED')",
                           name="ck_term_resolution_decision"),
        schema="knowledge",
    )
    op.execute("""
        CREATE FUNCTION knowledge.concept_is_frozen(parent_id uuid) RETURNS boolean AS $$
            SELECT EXISTS (SELECT 1 FROM knowledge.concept
                           WHERE id = parent_id AND status = 'REVIEWED')
                OR EXISTS (SELECT 1 FROM governance.knowledge_version_item
                           WHERE concept_id = parent_id)
                OR EXISTS (SELECT 1 FROM governance.human_review
                           WHERE target_kind = 'concept' AND target_id = parent_id
                             AND decision = 'APPROVE')
                OR EXISTS (SELECT 1 FROM knowledge.term_resolution
                           WHERE source_concept_id = parent_id OR resolved_concept_id = parent_id);
        $$ LANGUAGE sql;
        CREATE FUNCTION knowledge.guard_term_resolution() RETURNS trigger AS $$
        DECLARE parent_id uuid; parent_status text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'term resolutions are immutable';
            END IF;
            FOR parent_id IN SELECT DISTINCT candidate FROM (VALUES
                (NEW.source_concept_id), (NEW.resolved_concept_id), (NEW.related_concept_id)
            ) AS parents(candidate) WHERE candidate IS NOT NULL ORDER BY candidate
            LOOP
                PERFORM 1 FROM knowledge.concept WHERE id = parent_id FOR UPDATE;
            END LOOP;
            SELECT status INTO parent_status FROM knowledge.concept
              WHERE id = NEW.resolved_concept_id;
            IF parent_status IS DISTINCT FROM 'DRAFT'
               OR knowledge.concept_is_frozen(NEW.resolved_concept_id) THEN
                RAISE EXCEPTION 'term resolution requires an unfrozen new draft';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER immutable_term_resolution
        BEFORE INSERT OR UPDATE OR DELETE ON knowledge.term_resolution
        FOR EACH ROW EXECUTE FUNCTION knowledge.guard_term_resolution();

        CREATE FUNCTION knowledge.guard_concept_revision() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.requires_term_resolution IS DISTINCT FROM
               OLD.requires_term_resolution THEN
                RAISE EXCEPTION 'term resolution requirement is immutable';
            END IF;
            IF knowledge.concept_is_frozen(OLD.id) THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'reviewed or adjudicated concepts are immutable';
                END IF;
                IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
                    RAISE EXCEPTION 'reviewed or adjudicated concepts are immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER frozen_concept_revision
        BEFORE UPDATE OR DELETE ON knowledge.concept
        FOR EACH ROW EXECUTE FUNCTION knowledge.guard_concept_revision();

        CREATE FUNCTION knowledge.guard_concept_component() RETURNS trigger AS $$
        DECLARE parent_id uuid;
        BEGIN
            IF TG_TABLE_NAME = 'entity_mention' AND TG_OP = 'UPDATE' THEN
                IF (to_jsonb(NEW) - 'concept_id' - 'status') IS DISTINCT FROM
                   (to_jsonb(OLD) - 'concept_id' - 'status')
                   OR (OLD.concept_id IS NOT NULL AND NEW.concept_id IS DISTINCT FROM OLD.concept_id)
                   OR (OLD.status = 'AMBIGUOUS_DRAFT' AND NEW.status <> OLD.status) THEN
                    RAISE EXCEPTION 'exact mention identity and ambiguity are immutable';
                END IF;
            END IF;
            FOR parent_id IN SELECT DISTINCT candidate FROM (VALUES
                (CASE WHEN TG_OP <> 'INSERT' THEN OLD.concept_id END),
                (CASE WHEN TG_OP <> 'DELETE' THEN NEW.concept_id END)
            ) AS parents(candidate) WHERE candidate IS NOT NULL ORDER BY candidate
            LOOP
                PERFORM 1 FROM knowledge.concept WHERE id = parent_id FOR UPDATE;
                IF knowledge.concept_is_frozen(parent_id) THEN
                    RAISE EXCEPTION 'reviewed or adjudicated concept components are immutable';
                END IF;
            END LOOP;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("concept_term", "concept_evidence", "entity_mention"):
        op.execute(f"""
            CREATE TRIGGER frozen_{table}
            BEFORE INSERT OR UPDATE OR DELETE ON knowledge.{table}
            FOR EACH ROW EXECUTE FUNCTION knowledge.guard_concept_component()
        """)


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM knowledge.term_resolution) OR "
        "EXISTS (SELECT 1 FROM knowledge.concept WHERE requires_term_resolution)"
    )).scalar_one():
        raise RuntimeError("cannot downgrade while term adjudication lineage exists")
    for table in ("concept_term", "concept_evidence", "entity_mention"):
        op.execute(f"DROP TRIGGER frozen_{table} ON knowledge.{table}")
    op.execute("""
        DROP FUNCTION knowledge.guard_concept_component();
        DROP TRIGGER frozen_concept_revision ON knowledge.concept;
        DROP FUNCTION knowledge.guard_concept_revision();
        DROP TRIGGER immutable_term_resolution ON knowledge.term_resolution;
        DROP FUNCTION knowledge.guard_term_resolution();
        DROP FUNCTION knowledge.concept_is_frozen(uuid);
    """)
    op.drop_table("term_resolution", schema="knowledge")
    op.drop_column("concept", "requires_term_resolution", schema="knowledge")
