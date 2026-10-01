"""Proposed real C02 excerpts validate draft engineering, never expert acceptance."""

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from test_initial_corpus_integration import _segment_text

from tcm_platform.corpus_preflight import check_candidate_bundle
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_extraction import extract_source_candidates, trace_extraction
from tcm_platform.knowledge_formula_provenance import validate_formula_field_sources
from tcm_platform.knowledge_publish import create_knowledge_version, review_object
from tcm_platform.knowledge_service import create_evidence, trace_knowledge
from tcm_platform.models import (
    EvidenceRevision,
    FormulaIngredient,
    FormulaRevision,
    HumanReview,
    KnowledgeExtraction,
    KnowledgeRuntimeState,
    KnowledgeVersionItem,
    SourceRevision,
    TextSegmentRevision,
)
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore

BUNDLE = Path(__file__).resolve().parents[1] / "fixtures" / "c02_candidate"


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test"), name


@pytest.mark.parametrize("file,title,ingredients", [
    ("guizhi_tang.txt", "桂枝湯", ["桂枝", "芍藥", "甘草", "生薑", "大棗"]),
    ("guizhi_jia_ge_gen_tang.txt", "桂枝加葛根湯",
     ["葛根", "麻黄", "芍藥", "生薑", "甘草", "大棗", "桂枝"]),
    ("guizhi_jia_fu_zi_tang.txt", "桂枝加附子湯",
     ["桂枝", "芍藥", "甘草", "生薑", "大棗", "附子"]),
])
def test_proposed_real_formula_preserves_all_fields_and_stays_unreviewed(
    tmp_path, monkeypatch, file, title, ingredients,
):
    assert check_candidate_bundle(BUNDLE)["structural_valid"] is True
    original = (BUNDLE / file).read_bytes().replace(b"\r\n", b"\n")
    sample = tmp_path / file
    sample.write_bytes(original)
    store = ContentAddressedStore(tmp_path / "store")
    imported, segments = _segment_text(
        sample, store, SourceMetadata(
            source_type="CLASSIC", title=f"PROPOSED C02 工程验证·{title}",
            author="張仲景", era="漢", school=None,
            edition="維基文庫固定修訂2607901；待负责人选择/专家校订",
            copyright_status="PUBLIC_DOMAIN", data_level="PUBLIC",
            outbound_authorized=False,
        ), monkeypatch,
    )
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        active_before = (runtime.active_knowledge_version_id, runtime.active_index_build_id)
    result = extract_source_candidates(imported.source_revision_id)
    assert result["extractor_version"] == "local-exact-terms/v5"
    assert result["formula_count"] == 1
    formula, = result["formulas"]
    revision_id = UUID(formula["formula_revision_id"])
    evidence_id = UUID(formula["evidence_revision_id"])
    assert formula["original_name"] == title
    assert formula["segment_revision_ids"] == [str(segment.id) for segment in segments]
    trace = trace_knowledge("formula_revision", revision_id)
    assert trace["evidence"][0]["quote_text"] == "\n".join(s.original_text for s in segments)
    with SessionLocal() as session:
        revision = session.get(FormulaRevision, revision_id)
        assert revision.status == "DRAFT"
        assert (revision.era, revision.school, revision.indications, revision.effects,
                revision.dosage_form, revision.preparation, revision.cautions) == (None,) * 7
        assert revision.method == segments[-1].original_text
        rows = list(session.scalars(select(FormulaIngredient).where(
            FormulaIngredient.formula_revision_id == revision_id,
        ).order_by(FormulaIngredient.sequence_no)))
        assert [row.original_name for row in rows] == ingredients
        assert all((row.herb_id, row.amount_normalized, row.dose_ratio, row.role) == (None,) * 4
                   for row in rows)
        sources = validate_formula_field_sources(session, revision_id, require_complete=True)
        for source in sources:
            segment = session.get(TextSegmentRevision, UUID(source["segment_revision_id"]))
            assert source["quote_text"] == segment.original_text[
                source["start_offset"]:source["end_offset"]
            ]
        assert session.get(EvidenceRevision, evidence_id).status == "DRAFT"
        assert session.scalar(select(HumanReview.id).where(
            HumanReview.target_id.in_([revision_id, evidence_id]),
        ).limit(1)) is None
        source = session.get(SourceRevision, imported.source_revision_id)
        assert source.file_sha256 == hashlib.sha256(original).hexdigest()
        assert source.metadata_snapshot["outbound_authorized"] is False
    # Review attempts must fail before any review row is written for real excerpts.
    with pytest.raises(ValueError, match="reviewed"):
        review_object("formula_revision", revision_id, reviewer_id="engineering-gate-probe",
                      decision="APPROVE", note="Must fail: real evidence still unreviewed")
    with SessionLocal() as session:
        assert session.scalar(select(HumanReview.id).where(
            HumanReview.target_id.in_([revision_id, evidence_id]),
        ).limit(1)) is None

    # A separately named synthetic baseline lets us test snapshot exclusion without
    # ever approving C02 evidence, formulas, or other real knowledge candidates.
    baseline = tmp_path / "synthetic-baseline.txt"
    baseline.write_text("合成快照基线。", encoding="utf-8")
    _, baseline_segments = _segment_text(
        baseline, store, SourceMetadata(source_type="OTHER", title="合成快照基线"), monkeypatch,
    )
    baseline_evidence = create_evidence([baseline_segments[0].id], strength="DIRECT")
    review_object("evidence_revision", baseline_evidence, reviewer_id="synthetic-curator",
                  decision="APPROVE", note="Synthetic baseline only, never real C02 approval")
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.formula_revision_id == revision_id,
        )) is None
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
            KnowledgeVersionItem.evidence_revision_id == evidence_id,
        )) is None
        runtime = session.get(KnowledgeRuntimeState, 1)
        assert (runtime.active_knowledge_version_id, runtime.active_index_build_id) == active_before
    assert extract_source_candidates(imported.source_revision_id) == result


def test_v5_draft_extraction_keeps_existing_v4_batch(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-rule-lineage.txt"
    path.write_text("合成測試湯方：桂枝三兩。上一味，以水煎服。", encoding="utf-8")
    imported, _ = _segment_text(
        path, ContentAddressedStore(tmp_path / "store"),
        SourceMetadata(source_type="OTHER", title="合成v4谱系保留"), monkeypatch,
    )
    old_id = uuid4()
    old = {"extractor_version": "local-exact-terms/v4", "status": "DRAFT",
           "formula_count": 0, "segments": [], "formulas": []}
    with SessionLocal.begin() as session:
        session.add(KnowledgeExtraction(id=old_id, source_revision_id=imported.source_revision_id,
                                        extractor_version="local-exact-terms/v4", manifest=old))
    new = extract_source_candidates(imported.source_revision_id)
    assert new["extractor_version"] == "local-exact-terms/v5" and new["formula_count"] == 1
    assert new["extraction_id"] != str(old_id)
    assert trace_extraction(old_id)["manifest"] == old
    assert extract_source_candidates(imported.source_revision_id) == new
