"""Synthetic term decisions prove engineering gates, not expert terminology truth."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from test_initial_corpus_integration import _segment_text
from test_knowledge_publish_integration import FakeEmbedder

from tcm_platform import cli, knowledge_extraction, knowledge_publish, knowledge_terms
from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_extraction import extract_source_candidates
from tcm_platform.knowledge_publish import (
    activate_knowledge_version,
    compare_knowledge_versions,
    create_index_build,
    create_knowledge_version,
    review_object,
    supersede_reviewed_object,
)
from tcm_platform.knowledge_service import create_concept, trace_knowledge
from tcm_platform.knowledge_terms import TermSourceSpec, adjudicate_term
from tcm_platform.models import (
    Concept,
    EntityMention,
    EventLog,
    HumanReview,
    KnowledgeVersionItem,
    TermResolution,
)
from tcm_platform.retrieval import build_retrieval_index
from tcm_platform.source_import import SourceMetadata
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def isolated_database():
    with SessionLocal() as session:
        name = session.scalar(text("SELECT current_database()"))
        assert name.startswith("tcm_") and name.endswith("_test"), name
        session.execute(text("SELECT 1 FROM knowledge.term_resolution LIMIT 1"))


def _batch(tmp_path, monkeypatch, *, era=None, school=None, ambiguous=False):
    with monkeypatch.context() as patch:
        patch.setattr(knowledge_extraction, "TERMS", {
            "CONDITION": ("合成原詞",), **({"PATTERN": ("合成原詞",)} if ambiguous else {}),
        })
        path = tmp_path / f"{uuid4()}.txt"
        path.write_text("🙂合成原詞，另一說法。合成原詞，待考。", encoding="utf-8")
        imported, _ = _segment_text(
            path, ContentAddressedStore(tmp_path / "store"),
            SourceMetadata(source_type="OTHER", title="合成术语裁定", era=era, school=school), patch,
        )
        batch = extract_source_candidates(imported.source_revision_id)
    row = batch["segments"][0]
    concept_id = UUID(row["mentions"][0]["concept_id"])
    source = TermSourceSpec(UUID(row["evidence_revision_id"]), UUID(row["segment_revision_id"]),
                          1, 11)
    return batch, concept_id, source


def _decide(concept_id, source, **kwargs):
    return adjudicate_term(concept_id, decision=kwargs.pop("decision", "NORMALIZE"),
                           basis="合成测试人工解释；不代表正式术语标准", actor_id="test-curator",
                           sources=kwargs.pop("sources", (source,)), **kwargs)


def _approve_evidence(source):
    review_object("evidence_revision", source.evidence_revision_id, reviewer_id="test-curator",
                  decision="APPROVE", note="Synthetic engineering fixture only")


def _approve(concept_id):
    return review_object("concept", concept_id, reviewer_id="test-curator", decision="APPROVE",
                         note="Synthetic engineering fixture only")


def _publish(version_id):
    build_id = create_index_build(version_id, configuration={
        "strategy": "hybrid-v1", "embedding_model": FakeEmbedder.model_version,
    })
    build_retrieval_index(build_id, embedder=FakeEmbedder())
    activate_knowledge_version(version_id, build_id)
    return build_id


def test_ambiguous_type_candidates_independent_and_approval_requires_adjudication(
    tmp_path, monkeypatch,
):
    batch, concept_id, source = _batch(tmp_path, monkeypatch, ambiguous=True)
    mentions = batch["segments"][0]["mentions"]
    assert batch["concept_count"] == 2 and batch["mention_count"] == 4
    assert all(item["ambiguous"] for item in mentions)
    _approve_evidence(source)
    with pytest.raises(ValueError, match="explicit human adjudication"):
        _approve(concept_id)
    with SessionLocal() as session:
        assert session.get(Concept, concept_id).status == "DRAFT"
        assert session.scalar(select(HumanReview.id).where(HumanReview.target_id == concept_id)) is None
    new_id = _decide(concept_id, source, decision="DISTINCT")
    assert new_id not in {UUID(item["concept_id"]) for item in mentions}
    _approve(new_id)
    version_id = create_knowledge_version()
    with SessionLocal() as session:
        selected = set(session.scalars(select(KnowledgeVersionItem.concept_id).where(
            KnowledgeVersionItem.knowledge_version_id == version_id,
        )))
        assert new_id in selected
        assert all(UUID(item["concept_id"]) not in selected for item in mentions)
        assert all(session.get(EntityMention, UUID(item["mention_id"])).status == "AMBIGUOUS_DRAFT"
                   for item in mentions)


def test_selected_mentions_clone_exact_unicode_and_keep_unknown_metadata(tmp_path, monkeypatch):
    batch, old_id, source = _batch(tmp_path, monkeypatch)
    mentions = batch["segments"][0]["mentions"]
    selected = UUID(mentions[1]["mention_id"])
    new_id = _decide(old_id, source, canonical_name="合成規範詞", concept_type="PATTERN",
                     mention_ids=(selected,))
    traced = trace_knowledge("concept", new_id)
    assert (traced["era"], traced["school"]) == (None, None)
    assert traced["concept_type"] == "PATTERN"
    resolution = traced["term_resolution"]
    assert resolution["source_concept_id"] == str(old_id)
    assert len(resolution["mentions"]) == 1
    mention = resolution["mentions"][0]
    assert mention["source_mention_id"] == str(selected)
    assert mention["quote_text"] == "合成原詞" and mention["start_offset"] == 11
    assert mention["resolved_mention_id"] != str(selected)
    assert {(item["term"], item["term_kind"]) for item in traced["terms"]} == {
        ("合成規範詞", "PREFERRED"), ("合成原詞", "ORIGINAL"),
    }
    with SessionLocal() as session:
        assert session.get(EntityMention, selected).concept_id == old_id
        assert session.get(Concept, old_id).canonical_name == "合成原詞"
    with pytest.raises(ValueError, match="reviewed first"):
        _approve(new_id)
    _approve_evidence(source)
    _approve(new_id)


def test_historical_synonym_is_explicit_scoped_and_does_not_merge(tmp_path, monkeypatch):
    _, old_id, source = _batch(tmp_path, monkeypatch, era="合成时代甲", school="合成流派甲")
    _, other_id, other_source = _batch(tmp_path, monkeypatch, era="合成时代乙", school="合成流派乙")
    comparison = create_concept("合成現代詞", concept_type="CONDITION",
                                evidence_revision_id=other_source.evidence_revision_id,
                                era="合成时代乙", school="合成流派乙")
    with pytest.raises(ValueError, match="explicit reviewed comparison"):
        _decide(old_id, source, decision="HISTORICAL_SYNONYM", related_concept_id=comparison)
    _approve_evidence(other_source)
    _approve(comparison)
    with pytest.raises(ValueError, match="exact comparison evidence"):
        _decide(old_id, source, decision="HISTORICAL_SYNONYM", related_concept_id=comparison)
    new_id = _decide(old_id, source, decision="HISTORICAL_SYNONYM", related_concept_id=comparison,
                     sources=(source, other_source))
    traced = trace_knowledge("concept", new_id)
    assert new_id not in {old_id, other_id, comparison}
    assert traced["name"] == "合成現代詞"
    assert (traced["era"], traced["school"]) == ("合成时代甲", "合成流派甲")
    historical = next(term for term in traced["terms"] if term["term_kind"] == "HISTORICAL")
    assert (historical["term"], historical["era"], historical["school"]) == (
        "合成原詞", "合成时代甲", "合成流派甲",
    )
    assert traced["term_resolution"]["related_concept_id"] == str(comparison)
    assert {item["evidence_revision_id"] for item in traced["evidence"]} == {
        str(source.evidence_revision_id), str(other_source.evidence_revision_id),
    }
    _approve_evidence(source)
    _approve(new_id)
    with SessionLocal() as session:
        assert session.get(Concept, old_id).status == session.get(Concept, other_id).status == "DRAFT"


def test_unresolved_draft_retains_nulls_and_cannot_approve_or_snapshot(tmp_path, monkeypatch):
    _, old_id, source = _batch(tmp_path, monkeypatch)
    unresolved = _decide(old_id, source, decision="UNRESOLVED")
    _approve_evidence(source)
    with pytest.raises(ValueError, match="unresolved term"):
        _approve(unresolved)
    with SessionLocal.begin() as session:
        session.get(Concept, unresolved).status = "REVIEWED"  # Simulate an out-of-service bypass.
    try:
        with pytest.raises(ValueError, match="unresolved term"):
            create_knowledge_version()
    finally:
        with SessionLocal.begin() as session:
            session.get(Concept, unresolved).status = "DRAFT"
    with pytest.raises(ValueError, match="retain original"):
        _decide(old_id, source, decision="UNRESOLVED", canonical_name="不可推定")


def test_activation_rechecks_unresolved_adjudication(tmp_path, monkeypatch):
    _, old_id, source = _batch(tmp_path, monkeypatch)
    unresolved = _decide(old_id, source, decision="UNRESOLVED")
    _approve_evidence(source)
    with SessionLocal.begin() as session:
        session.get(Concept, unresolved).status = "REVIEWED"
    try:
        with monkeypatch.context() as patch:
            patch.setattr(knowledge_publish, "_validate_terms", lambda *args: None)
            version_id = create_knowledge_version()  # Simulate a snapshot gate bypass.
        with pytest.raises(ValueError, match="unresolved term"):
            _publish(version_id)
    finally:
        with SessionLocal.begin() as session:
            session.get(Concept, unresolved).status = "DRAFT"


def test_migration_refuses_to_discard_adjudication(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    _, old_id, source = _batch(tmp_path, monkeypatch)
    _decide(old_id, source)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="term adjudication lineage"):
        command.downgrade(config, "0025_formula_provenance")
    with SessionLocal() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0026_term_resolution"
        )


@pytest.mark.parametrize("mutation", [
    "UPDATE knowledge.term_resolution SET basis='改写' WHERE resolved_concept_id=:id",
    "DELETE FROM knowledge.term_resolution WHERE resolved_concept_id=:id",
    "UPDATE knowledge.concept SET canonical_name='改写' WHERE id=:id",
    "UPDATE knowledge.concept_term SET term='改写' WHERE concept_id=:id",
    "DELETE FROM knowledge.concept_evidence WHERE concept_id=:id",
    "UPDATE knowledge.entity_mention SET start_offset=0 WHERE concept_id=:id",
    "DELETE FROM knowledge.entity_mention WHERE concept_id=:id",
    "UPDATE knowledge.concept SET requires_term_resolution=false WHERE id=:id",
])
def test_adjudication_and_exact_components_are_immutable(tmp_path, monkeypatch, mutation):
    _, old_id, source = _batch(tmp_path, monkeypatch)
    new_id = _decide(old_id, source)
    with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
        session.execute(text(mutation), {"id": new_id})
    with pytest.raises(SQLAlchemyError, match="immutable"), SessionLocal.begin() as session:
        session.execute(text("UPDATE knowledge.concept SET school='改写' WHERE id=:id"), {"id": old_id})


@pytest.mark.parametrize("invalid", ["missing_evidence", "other_segment", "offset", "foreign_mention"])
def test_invalid_provenance_rolls_back_all_rows_and_audit(tmp_path, monkeypatch, invalid):
    _, old_id, source = _batch(tmp_path, monkeypatch)
    kwargs = {}
    if invalid == "missing_evidence":
        source = TermSourceSpec(uuid4(), source.segment_revision_id, 1, 5)
    elif invalid == "other_segment":
        _, _, other = _batch(tmp_path, monkeypatch)
        source = TermSourceSpec(source.evidence_revision_id, other.segment_revision_id, 1, 5)
    elif invalid == "offset":
        source = TermSourceSpec(source.evidence_revision_id, source.segment_revision_id, -1, 5)
    else:
        kwargs["mention_ids"] = (uuid4(),)
    def counts():
        with SessionLocal() as session:
            return tuple(session.scalar(select(func.count()).select_from(model))
                         for model in (Concept, TermResolution, EntityMention, EventLog))
    before = counts()
    with pytest.raises(ValueError):
        _decide(old_id, source, **kwargs)
    assert counts() == before
    with SessionLocal() as session:
        assert verify_chain(session)


def test_audit_failure_rolls_back_new_revision_and_freeze_then_retry(tmp_path, monkeypatch):
    _, old_id, source = _batch(tmp_path, monkeypatch)
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise RuntimeError("injected term audit failure")
        patch.setattr(knowledge_terms, "append_event", fail)
        with pytest.raises(RuntimeError, match="injected"):
            _decide(old_id, source)
    with SessionLocal() as session:
        assert session.scalar(select(TermResolution.id).where(
            TermResolution.source_concept_id == old_id,
        )) is None
    assert _decide(old_id, source)


def test_concurrent_proposals_preserve_original_candidate(tmp_path, monkeypatch):
    batch, old_id, source = _batch(tmp_path, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _decide(old_id, source), range(2)))
    assert results[0] != results[1]
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(TermResolution).where(
            TermResolution.source_concept_id == old_id,
        )) == 2
        assert all(session.get(EntityMention, UUID(item["mention_id"])).concept_id == old_id
                   for item in batch["segments"][0]["mentions"])
        assert verify_chain(session)


def test_published_term_correction_uses_existing_lineage_and_historical_activation(
    tmp_path, monkeypatch,
):
    _, old_id, source = _batch(tmp_path, monkeypatch, era="合成时代")
    _approve_evidence(source)
    _approve(old_id)
    old_version = create_knowledge_version()
    old_build = _publish(old_version)
    new_id = _decide(old_id, source, canonical_name="合成校訂詞")
    before_review = create_knowledge_version()
    with SessionLocal() as session:
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == before_review,
            KnowledgeVersionItem.concept_id == new_id,
        )) is None
    _approve(new_id)
    assert supersede_reviewed_object("concept", old_id, new_id) == 2
    new_version = create_knowledge_version()
    diff = compare_knowledge_versions(old_version, new_version)
    assert str(old_id) in diff["concept"]["removed"]
    assert str(new_id) in diff["concept"]["added"]
    _publish(new_version)
    activate_knowledge_version(old_version, old_build)
    with SessionLocal() as session:
        assert session.get(Concept, old_id).canonical_name == "合成原詞"
        assert session.scalar(select(KnowledgeVersionItem.id).where(
            KnowledgeVersionItem.knowledge_version_id == old_version,
            KnowledgeVersionItem.concept_id == old_id,
        )) is not None


def test_cli_requires_actor_basis_exact_sources_and_returns_trace(tmp_path, monkeypatch, capsys):
    _, old_id, source = _batch(tmp_path, monkeypatch)
    path = tmp_path / "term-sources.json"
    path.write_text(json.dumps([{
        "evidence_revision_id": str(source.evidence_revision_id),
        "segment_revision_id": str(source.segment_revision_id),
        "start_offset": source.start_offset, "end_offset": source.end_offset,
    }]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["tcm", "adjudicate-term", str(old_id), "--decision", "NORMALIZE",
                                    "--basis", "合成测试说明", "--actor", "test-curator",
                                    "--sources", str(path), "--name", "合成CLI校訂"])
    cli.main()
    concept_id = UUID(json.loads(capsys.readouterr().out)["concept_id"])
    assert trace_knowledge("concept", concept_id)["term_resolution"]["basis"] == "合成测试说明"
