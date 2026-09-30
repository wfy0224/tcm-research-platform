"""Synthetic complete formulas through the real transaction/provenance/review chain."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from test_initial_corpus_integration import _segment_text

from tcm_platform import cli, knowledge_extraction
from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_extraction import extract_source_candidates, trace_extraction
from tcm_platform.knowledge_formula_provenance import validate_formula_field_sources
from tcm_platform.knowledge_publish import create_knowledge_version, review_object
from tcm_platform.knowledge_service import trace_knowledge
from tcm_platform.models import (
    Concept,
    EntityMention,
    EventLog,
    EvidenceRevision,
    Formula,
    FormulaFieldSource,
    FormulaIngredient,
    FormulaRevision,
    KnowledgeExtraction,
    KnowledgeVersionItem,
    SourceDocument,
    TextSegmentRevision,
)
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test"), name


@pytest.fixture
def sample(tmp_path, monkeypatch):
    paragraphs = ["合成測試湯方：", "桂枝三兩（去皮）；芍藥三兩。",
                  "右二味，以水七升，煮取三升。", "分溫再服。"]
    path = tmp_path / "synthetic-complete-formula.txt"
    path.write_text("\n\n".join(paragraphs), encoding="utf-8")
    imported, segments = _segment_text(
        path, ContentAddressedStore(tmp_path / "store"),
        SourceMetadata(source_type="OTHER", title="合成完整方剂规则，非真实语料",
                       era="合成时代", school="合成流派"), monkeypatch,
    )
    return imported, segments, paragraphs


def _approve(kind, identity):
    review_object(kind, identity, reviewer_id="synthetic-curator", decision="APPROVE",
                  note="Synthetic engineering validation only; no actual corpus expert review")


def _counts():
    with SessionLocal() as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
            Formula, FormulaRevision, FormulaIngredient, FormulaFieldSource, EvidenceRevision,
            Concept, EntityMention, KnowledgeExtraction, EventLog,
        ))


def test_complete_formula_exact_fields_unknowns_review_and_snapshot(sample):
    imported, segments, paragraphs = sample
    with SessionLocal.begin() as session:
        source = session.get(SourceDocument, imported.source_id)
        source.era, source.school = "修改后时代", "修改后流派"
    result = extract_source_candidates(imported.source_revision_id)
    assert result["formula_count"] == 1
    assert (result["era"], result["school"]) == ("合成时代", "合成流派")
    formula, = result["formulas"]
    revision_id, evidence_id = UUID(formula["formula_revision_id"]), UUID(formula["evidence_revision_id"])
    assert formula["segment_revision_ids"] == [str(s.id) for s in segments]
    trace = trace_knowledge("formula_revision", revision_id)
    assert trace["evidence"][0]["quote_text"] == "\n".join(paragraphs)
    batch = trace_extraction(UUID(result["extraction_id"]))
    assert evidence_id in {UUID(e["evidence_revision_id"]) for e in batch["evidence"]}
    with SessionLocal() as session:
        revision = session.get(FormulaRevision, revision_id)
        assert revision.status == "DRAFT" and revision.provenance_version == 1
        assert (revision.era, revision.school, revision.indications, revision.effects,
                revision.dosage_form, revision.preparation, revision.cautions) == (None,) * 7
        assert revision.method == "\n".join(paragraphs[2:])
        ingredients = list(session.scalars(select(FormulaIngredient).where(
            FormulaIngredient.formula_revision_id == revision_id
        ).order_by(FormulaIngredient.sequence_no)))
        assert [(i.original_name, i.amount_original, i.processing) for i in ingredients] == [
            ("桂枝", "三兩", "去皮"), ("芍藥", "三兩", None),
        ]
        assert all((i.herb_id, i.amount_normalized, i.dose_ratio, i.role) == (None,) * 4
                   for i in ingredients)
        sources = validate_formula_field_sources(session, revision_id, require_complete=True)
        assert len(sources) == 10
        for source in sources:
            segment = session.get(TextSegmentRevision, UUID(source["segment_revision_id"]))
            assert source["quote_text"] == segment.original_text[
                source["start_offset"]:source["end_offset"]
            ]
        assert verify_chain(session)
    with pytest.raises(ValueError, match="reviewed"):
        _approve("formula_revision", revision_id)
    _approve("evidence_revision", evidence_id)
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.formula_revision_id == revision_id,
        )) is None
    _approve("formula_revision", revision_id)
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.formula_revision_id == revision_id,
        )) is not None


@pytest.mark.parametrize("stage", ["field_sources", "batch_audit"])
def test_late_failure_rolls_back_formulas_other_candidates_and_audit(sample, monkeypatch, stage):
    imported, _, _ = sample
    before = _counts()
    with monkeypatch.context() as patch:
        if stage == "field_sources":
            from tcm_platform import knowledge_service

            def fail(*args, **kwargs):
                raise RuntimeError("injected field source failure")
            patch.setattr(knowledge_service, "add_formula_field_sources", fail)
        else:
            def fail(*args, **kwargs):
                raise RuntimeError("injected batch audit failure")
            patch.setattr(knowledge_extraction, "append_event", fail)
        with pytest.raises(RuntimeError, match="injected"):
            extract_source_candidates(imported.source_revision_id)
    assert _counts() == before
    assert extract_source_candidates(imported.source_revision_id)["formula_count"] == 1


def test_concurrent_replay_has_single_formula_and_old_v3_batch_is_preserved(sample):
    imported, _, _ = sample
    old_id = uuid4()
    old_manifest = {"extractor_version": "local-exact-terms/v3", "segments": [], "status": "DRAFT"}
    with SessionLocal.begin() as session:
        session.add(KnowledgeExtraction(id=old_id, source_revision_id=imported.source_revision_id,
                                        extractor_version="local-exact-terms/v3", manifest=old_manifest))
    before = _counts()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(extract_source_candidates, [imported.source_revision_id] * 2))
    assert results[0] == results[1] and results[0]["formula_count"] == 1
    assert _counts()[0] == before[0] + 1
    with SessionLocal() as session:
        assert session.get(KnowledgeExtraction, old_id).manifest == old_manifest
        assert session.scalar(select(func.count()).select_from(KnowledgeExtraction).where(
            KnowledgeExtraction.source_revision_id == imported.source_revision_id,
        )) == 2
    assert trace_extraction(old_id)["manifest"] == old_manifest


def test_cli_returns_formula_manifest_and_trace(sample, monkeypatch, capsys):
    imported, _, _ = sample
    monkeypatch.setattr("sys.argv", ["tcm-platform", "extract-knowledge", str(imported.source_revision_id)])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["formula_count"] == 1
    monkeypatch.setattr("sys.argv", ["tcm-platform", "trace-extraction", result["extraction_id"]])
    cli.main()
    trace = json.loads(capsys.readouterr().out)
    assert trace["manifest"]["formulas"] == result["formulas"]


def test_same_name_in_different_sources_keeps_separate_formula_identity(sample, tmp_path, monkeypatch):
    imported, _, paragraphs = sample
    path = tmp_path / "another-synthetic-source.txt"
    path.write_text("\n\n".join(paragraphs), encoding="utf-8")
    other, _ = _segment_text(path, ContentAddressedStore(tmp_path / "other-store"),
                             SourceMetadata(source_type="OTHER", title="另一合成来源"), monkeypatch)
    first = extract_source_candidates(imported.source_revision_id)["formulas"][0]
    second = extract_source_candidates(other.source_revision_id)["formulas"][0]
    with SessionLocal() as session:
        assert session.get(FormulaRevision, UUID(first["formula_revision_id"])).formula_id != (
            session.get(FormulaRevision, UUID(second["formula_revision_id"])).formula_id
        )


def test_no_formula_join_across_structural_parents(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-separated-chapters.txt"
    path.write_text("第一章\n\n合成測試湯方：\n\n桂枝三兩。\n\n第二章\n\n右一味，以水煎服。", encoding="utf-8")
    imported, _ = _segment_text(path, ContentAddressedStore(tmp_path / "chapter-store"),
                               SourceMetadata(source_type="OTHER", title="合成章节隔离"), monkeypatch)
    assert extract_source_candidates(imported.source_revision_id)["formula_count"] == 0
