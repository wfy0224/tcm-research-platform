"""Reproduce VIB-46 checks inside the existing Linux runtime against an isolated test DB."""

import argparse
import os
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--full-suite", action="store_true")
    args = parser.parse_args()
    if re.fullmatch(r"tcm_[a-z0-9_]+_test", args.database) is None:
        raise ValueError("verification requires a named tcm_*_test database")
    connection_url = make_url(os.environ["TCM_DATABASE_URL"])
    admin = create_engine(connection_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    created = False
    with admin.connect() as connection:
        if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"),
                                 {"name": args.database}):
            connection.exec_driver_sql(f'CREATE DATABASE "{args.database}"')
            created = True
    admin.dispose()
    os.environ["TCM_DATABASE_URL"] = connection_url.set(database=args.database).render_as_string(
        hide_password=False
    )
    os.environ["TCM_OUTBOUND_MODE"] = "LOCAL_ONLY"
    # Import application configuration only after selecting the isolated database.
    import pytest
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    database = create_engine(os.environ["TCM_DATABASE_URL"])
    legacy_revision_id = None
    legacy_concept_id = None
    if created:
        command.upgrade(config, "0024_knowledge_extraction")
        legacy_formula_id, legacy_revision_id = uuid4(), uuid4()
        legacy_concept_id = uuid4()
        with database.begin() as connection:
            connection.execute(text(
                "INSERT INTO knowledge.formula (id, public_id, canonical_name, status, created_at) "
                "VALUES (:id, :public_id, '合成迁移保留测试', 'DRAFT', now())"
            ), {"id": legacy_formula_id, "public_id": f"migration-probe-{legacy_formula_id}"})
            connection.execute(text(
                "INSERT INTO knowledge.formula_revision "
                "(id, formula_id, revision_no, original_name, cautions, status, created_at) "
                "VALUES (:id, :formula_id, 1, '合成迁移保留测试', '未知保持原值', 'DRAFT', now())"
            ), {"id": legacy_revision_id, "formula_id": legacy_formula_id})
            connection.execute(text(
                "INSERT INTO knowledge.concept "
                "(id, public_id, canonical_name, concept_type, status, row_version, created_at) "
                "VALUES (:id, :public_id, '合成旧术语', 'UNKNOWN', 'DRAFT', 1, now())"
            ), {"id": legacy_concept_id, "public_id": f"migration-probe-{legacy_concept_id}"})
    command.upgrade(config, "head")
    command.check(config)
    with database.connect() as connection:
        empty = (
            connection.scalar(text("SELECT count(*) FROM knowledge.knowledge_extraction")) == 0
            and connection.scalar(text(
                "SELECT count(*) FROM knowledge.formula_revision WHERE provenance_version > 0"
            )) == 0
            and connection.scalar(text("SELECT count(*) FROM knowledge.term_resolution")) == 0
            and connection.scalar(text(
                "SELECT count(*) FROM knowledge.concept WHERE requires_term_resolution"
            )) == 0
        )
    if empty:
        command.downgrade(config, "0023_release_snapshot")
        command.upgrade(config, "head")
        command.check(config)
    else:
        print("Migration round-trip skipped: candidate provenance must be preserved.")
    if legacy_revision_id is not None:
        with database.connect() as connection:
            preserved = connection.execute(text(
                "SELECT provenance_version, original_name, cautions, status "
                "FROM knowledge.formula_revision WHERE id=:id"
            ), {"id": legacy_revision_id}).one()
            if tuple(preserved) != (0, "合成迁移保留测试", "未知保持原值", "DRAFT"):
                raise AssertionError("migration changed legacy formula content or review status")
            if connection.scalar(text(
                "SELECT count(*) FROM knowledge.formula_field_source WHERE formula_revision_id=:id"
            ), {"id": legacy_revision_id}):
                raise AssertionError("migration fabricated legacy field sources")
        print("Legacy formula migration preservation passed; synthetic draft retained for inspection.")
    if legacy_concept_id is not None:
        with database.connect() as connection:
            preserved = connection.execute(text(
                "SELECT canonical_name, concept_type, era, school, status, requires_term_resolution "
                "FROM knowledge.concept WHERE id=:id"
            ), {"id": legacy_concept_id}).one()
            if tuple(preserved) != ("合成旧术语", "UNKNOWN", None, None, "DRAFT", False):
                raise AssertionError("migration changed legacy concept content or review status")
            if connection.scalar(text(
                "SELECT count(*) FROM knowledge.term_resolution WHERE source_concept_id=:id "
                "OR resolved_concept_id=:id"
            ), {"id": legacy_concept_id}):
                raise AssertionError("migration fabricated legacy term adjudication")
        print("Legacy concept migration preservation passed; unknowns and draft status retained.")
    database.dispose()
    tests = ["tests"] if args.full_suite else [
        "tests/test_knowledge_extraction.py", "tests/test_knowledge_extraction_integration.py",
        "tests/test_knowledge_integration.py", "tests/test_initial_corpus_integration.py",
        "tests/test_knowledge_publish_integration.py",
        "tests/test_formula_provenance_integration.py",
        "tests/test_term_resolution_integration.py",
        "tests/test_formula_extraction.py", "tests/test_formula_extraction_integration.py",
    ]
    raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", *tests]))


if __name__ == "__main__":
    main()
