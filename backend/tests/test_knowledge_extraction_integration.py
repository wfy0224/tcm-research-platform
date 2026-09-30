"""Real corpus provenance plus transactional and review boundaries in an isolated DB."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from test_initial_corpus_integration import FIXTURES, _process_target, _segment_text

from tcm_platform import cli, knowledge_extraction
from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_extraction import extract_source_candidates, trace_extraction
from tcm_platform.knowledge_publish import create_knowledge_version, review_object
from tcm_platform.knowledge_service import create_evidence, trace_knowledge
from tcm_platform.models import (
    Concept,
    ConceptTerm,
    EntityMention,
    EvidenceRevision,
    FormulaIngredient,
    FormulaRevision,
    KnowledgeExtraction,
    KnowledgeRelation,
    KnowledgeRuntimeState,
    KnowledgeVersionItem,
    SourceDocument,
    TextSegmentRevision,
)
from tcm_platform.source_import import SourceMetadata, import_file
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test"), database
        session.execute(text("SELECT 1 FROM knowledge.knowledge_extraction LIMIT 1"))


def _synthetic(tmp_path, monkeypatch, *, era=None, school=None):
    path = tmp_path / f"{uuid4()}.txt"
    path.write_text("太陽病，發熱，汗出，惡風，脈緩者，名為中風。", encoding="utf-8")
    return _segment_text(
        path, ContentAddressedStore(tmp_path / "store"),
        SourceMetadata(source_type="OTHER", title="合成候选测试", era=era, school=school),
        monkeypatch,
    )[0]


def test_real_corpus_drafts_exact_spans_replay_and_snapshot_exclusion(tmp_path, monkeypatch):
    candidate = json.loads((FIXTURES / "initial_corpus.json").read_text(encoding="utf-8"))["sources"][0]
    path = tmp_path / candidate["file"]
    path.write_bytes((FIXTURES / candidate["file"]).read_bytes().replace(b"\r\n", b"\n"))
    imported, _ = _segment_text(
        path, ContentAddressedStore(tmp_path / "store"),
        SourceMetadata.model_validate(candidate["source_metadata"]), monkeypatch,
    )
    with SessionLocal() as session:
        active = session.get(KnowledgeRuntimeState, 1)
        before = (active.active_knowledge_version_id, active.active_index_build_id)
        formulas_before = session.scalar(select(func.count()).select_from(FormulaRevision))
        # Frozen metadata must win even after mutable source metadata is edited.
    with SessionLocal.begin() as session:
        source = session.get(SourceDocument, imported.source_id)
        source.era, source.school = "另一时代", "另一流派"
    result = extract_source_candidates(imported.source_revision_id)
    assert result == extract_source_candidates(imported.source_revision_id)
    assert result["segment_count"] == 29 and result["mention_count"] > 100
    assert result["relation_count"] >= 2
    assert result["formula_count"] == 0 and result["formulas"] == []
    assert result["era"] == "漢" and result["school"] is None
    traced = trace_extraction(UUID(result["extraction_id"]))
    assert len(traced["evidence"]) == sum(bool(row["mentions"]) for row in result["segments"])
    concept_ids, relation_ids, evidence_ids = set(), set(), set()
    with SessionLocal() as session:
        for row in result["segments"]:
            segment = session.get(TextSegmentRevision, UUID(row["segment_revision_id"]))
            if row["evidence_revision_id"]:
                evidence_ids.add(UUID(row["evidence_revision_id"]))
            for mention in row["mentions"]:
                entity = session.get(EntityMention, UUID(mention["mention_id"]))
                concept = session.get(Concept, UUID(mention["concept_id"]))
                concept_ids.add(concept.id)
                assert entity.surface_text == segment.original_text[
                    mention["start_offset"]:mention["end_offset"]
                ] == mention["surface_text"]
                assert entity.status == "RESOLVED_DRAFT" and concept.status == "DRAFT"
                assert concept.era == "漢" and concept.school is None
                terms = list(session.scalars(select(ConceptTerm).where(ConceptTerm.concept_id == concept.id)))
                assert [(t.term, t.term_kind) for t in terms] == [(concept.canonical_name, "PREFERRED")]
            for relation in row["relations"]:
                relation_id = UUID(relation["relation_id"])
                relation_ids.add(relation_id)
                obj = session.get(KnowledgeRelation, relation_id)
                assert obj.status == "DRAFT"
                assert obj.assertion_text == segment.original_text[
                    relation["start_offset"]:relation["end_offset"]
                ]
        assert len(concept_ids) == result["concept_count"]
        assert session.scalar(select(func.count()).select_from(FormulaRevision)) == formulas_before
        assert verify_chain(session)
    # A separately created synthetic sample supplies reviewed baseline Evidence.
    synthetic = _synthetic(tmp_path, monkeypatch)
    baseline = extract_source_candidates(synthetic.source_revision_id)
    baseline_evidence = UUID(baseline["segments"][0]["evidence_revision_id"])
    review_object("evidence_revision", baseline_evidence, reviewer_id="test-curator",
                  decision="APPROVE", note="Synthetic only; no real corpus expert review")
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.concept_id.in_(concept_ids),
        ).limit(1)) is None
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.relation_id.in_(relation_ids),
        ).limit(1)) is None
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.evidence_revision_id.in_(evidence_ids),
        ).limit(1)) is None
        active = session.get(KnowledgeRuntimeState, 1)
        assert (active.active_knowledge_version_id, active.active_index_build_id) == before


def test_failure_rolls_back_every_draft_and_audit_then_retry_succeeds(tmp_path, monkeypatch):
    imported = _synthetic(tmp_path, monkeypatch)
    with SessionLocal() as session:
        before = session.scalar(select(func.count()).select_from(Concept))
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise RuntimeError("injected relation failure")
        patch.setattr(knowledge_extraction, "create_relation", fail)
        with pytest.raises(RuntimeError, match="injected"):
            extract_source_candidates(imported.source_revision_id)
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Concept)) == before
        assert session.scalar(select(EvidenceRevision.id).where(
            EvidenceRevision.source_revision_id == imported.source_revision_id
        )) is None
        assert session.scalar(select(KnowledgeExtraction.id).where(
            KnowledgeExtraction.source_revision_id == imported.source_revision_id
        )) is None
        assert verify_chain(session)
    assert extract_source_candidates(imported.source_revision_id)["relation_count"] == 1


def test_concurrent_replay_and_separate_era_school_batches(tmp_path, monkeypatch):
    first = _synthetic(tmp_path, monkeypatch, era="时代甲", school="流派甲")
    second = _synthetic(tmp_path, monkeypatch, era="时代乙", school="流派乙")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(extract_source_candidates, [first.source_revision_id] * 2))
    assert results[0] == results[1]
    other = extract_source_candidates(second.source_revision_id)
    ids = {m["concept_id"] for row in results[0]["segments"] for m in row["mentions"]}
    assert ids.isdisjoint(m["concept_id"] for row in other["segments"] for m in row["mentions"])
    assert (other["era"], other["school"]) == ("时代乙", "流派乙")
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeExtraction).where(
            KnowledgeExtraction.source_revision_id == first.source_revision_id,
        )) == 1
    with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
        session.execute(text("UPDATE knowledge.knowledge_extraction SET manifest='{}'::jsonb WHERE id=:id"),
                        {"id": results[0]["extraction_id"]})


def test_unsegmented_or_missing_source_cannot_create_batch(tmp_path, monkeypatch):
    path = tmp_path / "pending.txt"
    path.write_text("太陽病。", encoding="utf-8")
    store = ContentAddressedStore(tmp_path / "store")
    imported = import_file(path, SourceMetadata(source_type="OTHER", title="未分段"),
                           request_key=f"extract-pending:{uuid4()}",
                           store=store)
    with pytest.raises(ValueError, match="segmentation"):
        extract_source_candidates(imported.source_revision_id)
    with pytest.raises(ValueError, match="does not exist"):
        extract_source_candidates(uuid4())
    assert _process_target(imported, store, monkeypatch).status == "PARSED"
    assert _process_target(imported, store, monkeypatch, segment=True).status == "SEGMENTED"


def test_formula_cli_fields_append_revision_and_require_evidence_review(tmp_path, monkeypatch, capsys):
    original = "桂枝湯：桂枝三兩，去皮；芍藥三兩。煎服測試。待专项校订。禁忌待考。"
    path = tmp_path / "synthetic-formula.txt"
    path.write_text(original, encoding="utf-8")
    _, segments = _segment_text(
        path, ContentAddressedStore(tmp_path / "store"),
        SourceMetadata(source_type="OTHER", title="合成方剂字段测试"), monkeypatch,
    )
    evidence_id = create_evidence([segments[0].id], strength="DIRECT")
    ingredients = tmp_path / "ingredients.json"
    ingredients.write_text(json.dumps([
        {"original_name": "桂枝", "amount_original": "三兩", "amount_normalized": None,
         "unit": "兩", "processing": "去皮", "dose_ratio": "1"},
        {"original_name": "芍藥", "amount_original": "三兩", "dose_ratio": "1"},
    ], ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "field-sources.json"
    def field_source(key, quote, *, start=0, basis=None):
        offset = original.index(quote, start)
        return {"field_key": key, "evidence_revision_id": str(evidence_id),
                "segment_revision_id": str(segments[0].id),
                "start_offset": offset, "end_offset": offset + len(quote), "basis": basis}
    field_sources = [
        field_source("original_name", "桂枝湯"),
        field_source("method", "煎服測試"),
        field_source("dosage_form", "湯"),
        field_source("preparation", "待专项校订"),
        field_source("cautions", "禁忌待考"),
        field_source("ingredients.0.original_name", "桂枝", start=original.index("：")),
        field_source("ingredients.0.amount_original", "三兩"),
        field_source("ingredients.0.unit", "兩"),
        field_source("ingredients.0.processing", "去皮"),
        field_source("ingredients.0.dose_ratio", "三兩", basis="合成两味均为三兩，剂量比例为1"),
        field_source("ingredients.1.original_name", "芍藥"),
        field_source("ingredients.1.amount_original", "三兩", start=original.index("芍藥")),
        field_source("ingredients.1.dose_ratio", "三兩", start=original.index("芍藥"),
                     basis="合成两味均为三兩，剂量比例为1"),
    ]
    sources.write_text(json.dumps(field_sources, ensure_ascii=False), encoding="utf-8")
    args = ["tcm", "create-formula", "桂枝湯", "--evidence", str(evidence_id),
            "--ingredient-spec", str(ingredients), "--field-sources", str(sources),
            "--method", "煎服測試",
            "--dosage-form", "湯", "--preparation", "待专项校订", "--cautions", "禁忌待考"]
    monkeypatch.setattr("sys.argv", args)
    cli.main()
    first_id = UUID(json.loads(capsys.readouterr().out)["formula_revision_id"])
    trace = trace_knowledge("formula_revision", first_id)
    assert trace["evidence"][0]["quote_text"] == original
    with SessionLocal() as session:
        first = session.get(FormulaRevision, first_id)
        assert (first.method, first.dosage_form, first.preparation, first.cautions) == (
            "煎服測試", "湯", "待专项校订", "禁忌待考",
        )
        assert first.era is None and first.school is None
        formula_id = first.formula_id
        rows = list(session.scalars(select(FormulaIngredient).where(
            FormulaIngredient.formula_revision_id == first_id,
        ).order_by(FormulaIngredient.sequence_no)))
        assert rows[0].amount_original == "三兩" and rows[0].amount_normalized is None
        assert rows[0].processing == "去皮" and rows[0].role is None
        assert rows[0].dose_ratio == rows[1].dose_ratio == "1"
    with pytest.raises(ValueError, match="reviewed"):
        review_object("formula_revision", first_id, reviewer_id="test-curator", decision="APPROVE",
                      note="Synthetic only")
    review_object("evidence_revision", evidence_id, reviewer_id="test-curator", decision="APPROVE",
                  note="Synthetic only; no expert corpus review")
    review_object("formula_revision", first_id, reviewer_id="test-curator", decision="APPROVE",
                  note="Synthetic only; no expert corpus review")
    version_id = create_knowledge_version()
    ingredients.write_text('[{"original_name":"桂枝","amount_original":"三兩"}]', encoding="utf-8")
    sources.write_text(json.dumps([
        item for item in field_sources if not item["field_key"].startswith("ingredients.")
        or item["field_key"] in {"ingredients.0.original_name", "ingredients.0.amount_original"}
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [*args, "--formula-id", str(formula_id)])
    cli.main()
    second_id = UUID(json.loads(capsys.readouterr().out)["formula_revision_id"])
    with SessionLocal() as session:
        assert session.get(FormulaRevision, first_id).revision_no == 1
        assert session.get(FormulaRevision, first_id).status == "REVIEWED"
        assert session.get(FormulaRevision, second_id).revision_no == 2
        assert session.get(FormulaRevision, second_id).status == "DRAFT"
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.formula_revision_id == first_id,
        )) is not None
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.formula_revision_id == second_id,
        )) is None
