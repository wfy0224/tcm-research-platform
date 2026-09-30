"""Field-level formula citations, review gates and immutable revision boundaries."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_initial_corpus_integration import _segment_text

from tcm_platform import cli, knowledge_publish, knowledge_service
from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal, engine
from tcm_platform.knowledge_formula_provenance import (
    FormulaFieldSourceSpec,
    validate_formula_field_sources,
)
from tcm_platform.knowledge_publish import create_knowledge_version, review_object
from tcm_platform.knowledge_service import (
    IngredientSpec,
    create_evidence,
    create_formula,
    create_herb,
    trace_knowledge,
)
from tcm_platform.models import (
    EventLog,
    Formula,
    FormulaEvidence,
    FormulaFieldSource,
    FormulaIngredient,
    FormulaRevision,
    HumanReview,
    KnowledgeVersionItem,
)
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test"), database
        session.execute(text("SELECT 1 FROM knowledge.formula_field_source LIMIT 1"))


@pytest.fixture
def sample(tmp_path, monkeypatch):
    paragraphs = [
        "合成測試方：桂枝三兩，去皮；芍藥三兩。主治測試證。解肌。",
        "漢代合成測試，流派甲。調和。煎服。湯劑。水煎。禁忌待考。比例1，桂枝為君。",
    ]
    path = tmp_path / "field-citations.txt"
    path.write_text("\n\n".join(paragraphs), encoding="utf-8")
    _, segments = _segment_text(
        path, ContentAddressedStore(tmp_path / "store"),
        SourceMetadata(source_type="OTHER", title="合成方剂逐字段引用"), monkeypatch,
    )
    assert [segment.original_text for segment in segments] == paragraphs
    evidence = create_evidence([segment.id for segment in segments], strength="DIRECT")

    def source(key, quote, *, paragraph=0, start=0, basis=None):
        offset = paragraphs[paragraph].index(quote, start)
        return FormulaFieldSourceSpec(
            field_key=key, evidence_revision_id=evidence,
            segment_revision_id=segments[paragraph].id,
            start_offset=offset, end_offset=offset + len(quote), basis=basis,
        )

    basic_sources = (
        source("original_name", "合成測試方"),
        source("ingredients.0.original_name", "桂枝"),
    )
    return {"text": paragraphs, "segments": segments, "evidence": evidence,
            "source": source, "basic_sources": basic_sources}


def _approve(kind, object_id):
    return review_object(kind, object_id, reviewer_id="synthetic-curator", decision="APPROVE",
                         note="Synthetic test only; no actual corpus expert review")


def _basic_formula(sample, **kwargs):
    return create_formula(
        "合成測試方", evidence_revision_id=sample["evidence"],
        ingredients=(IngredientSpec(original_name="桂枝"),), **kwargs,
    )


def _counts(session_factory=SessionLocal):
    with session_factory() as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
            Formula, FormulaRevision, FormulaIngredient, FormulaFieldSource, HumanReview, EventLog,
        ))


def test_missing_sources_draft_is_traceable_but_approval_has_no_review_or_audit(sample):
    revision_id = _basic_formula(sample)
    assert trace_knowledge("formula_revision", revision_id)["evidence"]
    _approve("evidence_revision", sample["evidence"])
    before = _counts()
    with pytest.raises(ValueError, match="missing"):
        _approve("formula_revision", revision_id)
    assert _counts() == before
    with SessionLocal() as session:
        assert session.get(FormulaRevision, revision_id).status == "DRAFT"
        assert session.scalar(select(HumanReview.id).where(HumanReview.target_id == revision_id)) is None
        assert verify_chain(session)


@pytest.mark.parametrize("case", [
    "negative", "past_end", "empty_span", "fractional", "wrong_evidence", "missing_segment",
    "unknown_key", "bad_sequence", "unknown_ingredient_field", "duplicate_span", "empty_basis",
    "missing_basis", "null_field",
])
def test_invalid_field_sources_roll_back_formula_and_audit(sample, case):
    spec = sample["basic_sources"][0]
    changes = {
        "negative": {"start_offset": -1},
        "past_end": {"end_offset": len(sample["text"][0]) + 1},
        "empty_span": {"end_offset": spec.start_offset},
        "fractional": {"start_offset": 0.5},
        "wrong_evidence": {"evidence_revision_id": uuid4()},
        "missing_segment": {"segment_revision_id": uuid4()},
        "unknown_key": {"field_key": "unsupported"},
        "bad_sequence": {"field_key": "ingredients.1.original_name"},
        "unknown_ingredient_field": {"field_key": "ingredients.0.unsupported"},
        "empty_basis": {"basis": "  "},
        "missing_basis": {"end_offset": spec.end_offset + 1},
        "null_field": {"field_key": "era"},
    }
    sources = (spec, spec) if case == "duplicate_span" else (replace(spec, **changes[case]),)
    before = _counts()
    with pytest.raises((ValueError, TypeError)):
        _basic_formula(sample, field_sources=sources)
    assert _counts() == before


def test_segment_must_be_in_cited_evidence(sample):
    first_only = create_evidence([sample["segments"][0].id], strength="DIRECT")
    outside = replace(sample["source"]("method", "煎服", paragraph=1),
                      evidence_revision_id=first_only)
    before = _counts()
    with pytest.raises(ValueError, match="evidence|segment"):
        _basic_formula(sample, method="煎服", field_sources=(outside,))
    assert _counts() == before


@pytest.mark.parametrize("key,root_fields,ingredient,quote,paragraph", [
    ("era", {"era": "漢"}, IngredientSpec(original_name="桂枝"), "漢", 1),
    ("school", {"school": "流派甲"}, IngredientSpec(original_name="桂枝"), "流派甲", 1),
    ("ingredients.0.amount_normalized", {},
     IngredientSpec(original_name="桂枝", amount_normalized="三兩"), "三兩", 0),
    ("ingredients.0.dose_ratio", {}, IngredientSpec(original_name="桂枝", dose_ratio="1"), "1", 1),
    ("ingredients.0.role", {}, IngredientSpec(original_name="桂枝", role="君"), "君", 1),
])
def test_normalized_and_context_fields_require_explicit_basis(
    sample, key, root_fields, ingredient, quote, paragraph,
):
    before = _counts()
    source = sample["source"](key, quote, paragraph=paragraph)
    with pytest.raises(ValueError, match="basis"):
        create_formula("合成測試方", evidence_revision_id=sample["evidence"],
                       ingredients=(ingredient,), field_sources=(source,), **root_fields)
    assert _counts() == before


def test_herb_link_requires_basis_even_with_a_real_herb(sample):
    herb_id = create_herb("桂枝", evidence_revision_id=sample["evidence"])
    before = _counts()
    with pytest.raises(ValueError, match="basis"):
        create_formula(
            "合成測試方", evidence_revision_id=sample["evidence"],
            ingredients=(IngredientSpec(original_name="桂枝", herb_id=herb_id),),
            field_sources=(sample["source"]("ingredients.0.herb_id", "桂枝"),),
        )
    assert _counts() == before


def test_complete_multisegment_multispan_fields_are_frozen_and_unknowns_stay_null(sample):
    source = sample["source"]
    fields = {"era": "漢", "school": "流派甲", "indications": "測試證", "effects": "解肌調和",
              "method": "煎服", "dosage_form": "湯劑", "preparation": "水煎", "cautions": "禁忌待考"}
    sources = (*sample["basic_sources"],
        source("era", "漢代", paragraph=1, basis="合成文本明确汉代，时代简称漢"),
        source("school", "流派甲", paragraph=1, basis="合成文本明确流派甲"),
        source("indications", "測試證"),
        source("effects", "解肌", basis="两段功效合并为解肌調和"),
        source("effects", "調和", paragraph=1, basis="两段功效合并为解肌調和"),
        source("method", "煎服", paragraph=1),
        source("dosage_form", "湯劑", paragraph=1),
        source("preparation", "水煎", paragraph=1),
        source("cautions", "禁忌待考", paragraph=1),
        source("ingredients.0.amount_original", "三兩"),
        source("ingredients.0.amount_normalized", "三兩", basis="合成古剂量数值三记录为3，未转换现代重量"),
        source("ingredients.0.unit", "兩"),
        source("ingredients.0.dose_ratio", "三兩", basis="两味原剂量均三兩，比例记为1"),
        source("ingredients.0.processing", "去皮"),
    )
    revision_id = create_formula(
        "合成測試方", evidence_revision_id=sample["evidence"], field_sources=sources,
        ingredients=(IngredientSpec(original_name="桂枝", amount_original="三兩",
                                    amount_normalized="3", unit="兩", dose_ratio="1", processing="去皮"),),
        **fields,
    )
    with SessionLocal() as session:
        revision = session.get(FormulaRevision, revision_id)
        assert revision.provenance_version == 1
        ingredient = session.scalar(select(FormulaIngredient).where(
            FormulaIngredient.formula_revision_id == revision_id))
        assert ingredient.herb_id is None and ingredient.role is None
        rows = list(session.scalars(select(FormulaFieldSource).where(
            FormulaFieldSource.formula_revision_id == revision_id)))
        assert len(rows) == len(sources)
        for row in rows:
            segment = next(segment for segment in sample["segments"] if segment.id == row.segment_revision_id)
            assert row.quote_text == segment.original_text[row.start_offset:row.end_offset]
            assert row.segment_checksum == segment.checksum
            if row.field_key.startswith("ingredients."):
                expected = getattr(ingredient, row.field_key.split(".")[2])
            else:
                expected = getattr(revision, row.field_key)
            assert row.value_snapshot == str(expected)
        assert sum(row.field_key == "effects" for row in rows) == 2
        source_id = rows[0].id
    _approve("evidence_revision", sample["evidence"])
    _approve("formula_revision", revision_id)
    for statement in (
        "UPDATE knowledge.formula_field_source SET quote_text='篡改' WHERE id=:id",
        "DELETE FROM knowledge.formula_field_source WHERE id=:id",
    ):
        with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
            session.execute(text(statement), {"id": source_id})
    with pytest.raises(SQLAlchemyError, match="provenance draft"), SessionLocal.begin() as session:
        session.add(FormulaFieldSource(
            formula_revision_id=revision_id, field_key="original_name", value_snapshot="合成測試方",
            evidence_revision_id=sample["evidence"], segment_revision_id=sample["segments"][0].id,
            start_offset=0, end_offset=2, quote_text="合成", basis="追加已审核引用应失败",
            segment_checksum=sample["segments"][0].checksum,
        ))
        session.flush()


def test_append_revision_keeps_published_formula_and_citations(sample):
    first_id = _basic_formula(sample, field_sources=sample["basic_sources"])
    _approve("evidence_revision", sample["evidence"])
    _approve("formula_revision", first_id)
    version_id = create_knowledge_version()
    before = trace_knowledge("formula_revision", first_id)
    with SessionLocal() as session:
        formula_id = session.get(FormulaRevision, first_id).formula_id
    second_id = _basic_formula(sample, formula_id=formula_id, field_sources=sample["basic_sources"],
                               method="煎服")
    with pytest.raises(ValueError, match="missing"):
        _approve("formula_revision", second_id)
    assert trace_knowledge("formula_revision", first_id) == before
    with SessionLocal() as session:
        assert session.get(FormulaRevision, second_id).revision_no == 2
        assert session.get(FormulaRevision, second_id).status == "DRAFT"
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.formula_revision_id == first_id)) is not None
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.formula_revision_id == second_id)) is None


def test_reviewed_formula_parent_components_and_version_are_frozen_but_rejection_remains_available(sample):
    revision_id = _basic_formula(sample, field_sources=sample["basic_sources"])
    _approve("evidence_revision", sample["evidence"])
    _approve("formula_revision", revision_id)
    with SessionLocal() as session:
        formula_id = session.get(FormulaRevision, revision_id).formula_id
        ingredient_id = session.scalar(select(FormulaIngredient.id).where(
            FormulaIngredient.formula_revision_id == revision_id))
        evidence_link_id = session.scalar(select(FormulaEvidence.id).where(
            FormulaEvidence.formula_revision_id == revision_id))
    replacement_id = _basic_formula(sample, formula_id=formula_id,
                                    field_sources=sample["basic_sources"])
    alternate_evidence_id = create_evidence([sample["segments"][0].id], strength="DIRECT")
    before = trace_knowledge("formula_revision", revision_id)
    counts = _counts()
    mutations = (
        ("UPDATE knowledge.formula_revision SET original_name='改名' WHERE id=:id", revision_id),
        ("DELETE FROM knowledge.formula_revision WHERE id=:id", revision_id),
        ("UPDATE knowledge.formula_revision SET provenance_version=0 WHERE id=:id", revision_id),
        ("UPDATE knowledge.formula_ingredient SET original_name='改药' WHERE id=:id", ingredient_id),
        ("DELETE FROM knowledge.formula_ingredient WHERE id=:id", ingredient_id),
        ("UPDATE knowledge.formula_ingredient SET formula_revision_id=:replacement WHERE id=:id",
         ingredient_id),
        ("UPDATE knowledge.formula_evidence SET evidence_revision_id=:evidence WHERE id=:id",
         evidence_link_id),
        ("DELETE FROM knowledge.formula_evidence WHERE id=:id", evidence_link_id),
        ("UPDATE knowledge.formula_evidence SET formula_revision_id=:replacement WHERE id=:id",
         evidence_link_id),
    )
    for statement, object_id in mutations:
        with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
            session.execute(text(statement), {
                "id": object_id, "replacement": replacement_id, "evidence": alternate_evidence_id,
            })
    with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
        session.add(FormulaIngredient(formula_revision_id=revision_id, original_name="芍藥", sequence_no=1))
        session.flush()
    assert _counts() == counts
    assert trace_knowledge("formula_revision", revision_id) == before
    with SessionLocal() as session:
        assert session.get(FormulaRevision, replacement_id).status == "DRAFT"
    rejection_id = review_object(
        "formula_revision", revision_id, reviewer_id="synthetic-curator", decision="REJECT",
        note="Synthetic status-only rejection remains available before snapshot",
    )
    with SessionLocal() as session:
        assert session.get(FormulaRevision, revision_id).status == "REJECTED"
        assert session.get(HumanReview, rejection_id).decision == "REJECT"
        assert session.get(FormulaIngredient, ingredient_id).formula_revision_id == revision_id
        assert session.get(FormulaEvidence, evidence_link_id).evidence_revision_id == sample["evidence"]
        assert verify_chain(session)
    # A prior approval freezes content even after the supported status-only rejection.
    with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
        session.execute(text("UPDATE knowledge.formula_revision SET original_name='改名' WHERE id=:id"),
                        {"id": revision_id})


def test_snapshot_revalidates_new_formulas_even_if_review_service_was_bypassed(sample, monkeypatch):
    revision_id = _basic_formula(sample)
    _approve("evidence_revision", sample["evidence"])
    before = _counts()
    # Roll back the fake review through an outer transaction: REVIEWED rows are immutable.
    with engine.connect() as connection:
        transaction = connection.begin()
        scoped_session = sessionmaker(bind=connection, expire_on_commit=False,
                                      join_transaction_mode="create_savepoint")
        try:
            with scoped_session.begin() as session:
                session.get(FormulaRevision, revision_id).status = "REVIEWED"
            with monkeypatch.context() as patch:
                patch.setattr(knowledge_publish, "SessionLocal", scoped_session)
                with pytest.raises(ValueError, match="missing"):
                    create_knowledge_version()
        finally:
            transaction.rollback()
    assert _counts() == before
    with SessionLocal() as session:
        assert session.get(FormulaRevision, revision_id).status == "DRAFT"


@pytest.mark.parametrize("attribute,value", [
    ("value_snapshot", "改写值"), ("quote_text", "改写引文"), ("segment_checksum", "0" * 64),
])
def test_trace_validation_detects_changed_frozen_snapshots_without_writing(sample, attribute, value):
    revision_id = _basic_formula(sample, field_sources=sample["basic_sources"])
    with SessionLocal() as session:
        row = session.scalar(select(FormulaFieldSource).where(
            FormulaFieldSource.formula_revision_id == revision_id))
        setattr(row, attribute, value)
        with session.no_autoflush, pytest.raises(ValueError, match="snapshot"):
            validate_formula_field_sources(session, revision_id)
    assert trace_knowledge("formula_revision", revision_id)["evidence"]


def test_unknown_fields_stay_null_and_adjacent_spans_can_support_one_exact_value(sample):
    name = sample["basic_sources"][0]
    split_sources = (
        replace(name, end_offset=2), replace(name, start_offset=2), sample["basic_sources"][1],
    )
    revision_id = _basic_formula(sample, field_sources=split_sources)
    _approve("evidence_revision", sample["evidence"])
    _approve("formula_revision", revision_id)
    with SessionLocal() as session:
        revision = session.get(FormulaRevision, revision_id)
        assert all(getattr(revision, key) is None for key in (
            "era", "school", "indications", "effects", "method", "dosage_form", "preparation", "cautions",
        ))
        ingredient = session.scalar(select(FormulaIngredient).where(
            FormulaIngredient.formula_revision_id == revision_id))
        assert all(getattr(ingredient, key) is None for key in (
            "herb_id", "amount_original", "amount_normalized", "unit", "dose_ratio", "role", "processing",
        ))


def test_legacy_reviewed_formula_snapshots_without_fabricated_sources_but_draft_cannot_approve(
    sample, monkeypatch,
):
    _approve("evidence_revision", sample["evidence"])
    formula_id, draft_id, reviewed_id = uuid4(), uuid4(), uuid4()
    # The independent test DB simulates pre-migration rows. DDL and rows are rolled back together.
    with engine.connect() as connection:
        transaction = connection.begin()
        scoped_session = sessionmaker(bind=connection, expire_on_commit=False,
                                      join_transaction_mode="create_savepoint")
        try:
            with scoped_session.begin() as session:
                session.execute(text(
                    "ALTER TABLE knowledge.formula_revision DISABLE TRIGGER frozen_formula_revision"))
                session.add(Formula(id=formula_id, public_id=f"legacy-{formula_id}", canonical_name="旧方"))
                session.flush()
                for number, revision_id in enumerate((draft_id, reviewed_id), 1):
                    session.add(FormulaRevision(id=revision_id, formula_id=formula_id, revision_no=number,
                                                original_name="旧方", provenance_version=0, status="DRAFT"))
                session.flush()
                session.execute(text(
                    "ALTER TABLE knowledge.formula_revision ENABLE TRIGGER frozen_formula_revision"))
                for revision_id in (draft_id, reviewed_id):
                    session.add(FormulaIngredient(formula_revision_id=revision_id,
                                                  original_name="桂枝", sequence_no=0))
                    session.add(FormulaEvidence(formula_revision_id=revision_id,
                                                evidence_revision_id=sample["evidence"]))
                session.flush()
                session.get(FormulaRevision, reviewed_id).status = "REVIEWED"
            with monkeypatch.context() as patch:
                patch.setattr(knowledge_publish, "SessionLocal", scoped_session)
                patch.setattr(knowledge_service, "SessionLocal", scoped_session)
                before = _counts(scoped_session)
                with pytest.raises(ValueError, match="legacy"):
                    _approve("formula_revision", draft_id)
                assert _counts(scoped_session) == before
                version_id = create_knowledge_version()
                with scoped_session() as session:
                    assert session.scalar(select(KnowledgeVersionItem.id).where(
                        KnowledgeVersionItem.knowledge_version_id == version_id,
                        KnowledgeVersionItem.formula_revision_id == reviewed_id)) is not None
                    assert session.scalar(select(KnowledgeVersionItem.id).where(
                        KnowledgeVersionItem.knowledge_version_id == version_id,
                        KnowledgeVersionItem.formula_revision_id == draft_id)) is None
                    assert session.scalar(select(FormulaFieldSource.id).where(
                        FormulaFieldSource.formula_revision_id == reviewed_id)) is None
        finally:
            transaction.rollback()


@pytest.mark.parametrize("payload", ["{}", "[null]", '["source"]'])
def test_cli_rejects_non_object_source_arrays(tmp_path, monkeypatch, payload):
    source_file = tmp_path / "invalid-sources.json"
    source_file.write_text(payload, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["tcm", "create-formula", "合成測試方",
                        "--evidence", str(uuid4()), "--ingredient", "桂枝",
                        "--field-sources", str(source_file)])
    with pytest.raises(ValueError, match="JSON array"):
        cli.main()
