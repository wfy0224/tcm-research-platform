from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.audit import verify_chain
from tcm_platform.db import SessionLocal, engine
from tcm_platform.knowledge_service import (
    IngredientSpec,
    create_concept,
    create_entity_mention,
    create_evidence,
    create_formula,
    create_herb,
    create_relation,
    trace_evidence,
    trace_knowledge,
)
from tcm_platform.models import (
    ConceptEvidence,
    EntityMention,
    EvidenceRevision,
    FormulaEvidence,
    FormulaIngredient,
    FormulaRevision,
    HerbEvidence,
    RelationEvidence,
    TextSegmentRevision,
)
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import SourceMetadata, import_file, process_next_import
from tcm_platform.storage import ContentAddressedStore


@pytest.fixture(autouse=True)
def migrated_postgres():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM knowledge.evidence_revision LIMIT 1"))
    except SQLAlchemyError:
        pytest.skip("E4 migration is not available")


def _finish_segment(import_job_id, store):
    for _ in range(100):
        result = process_next_segment(store=store)
        if result is None:
            break
        if result.import_job_id == import_job_id:
            assert result.status == "SEGMENTED"
            return
    pytest.fail("target source revision was not segmented")


def test_draft_knowledge_traces_to_exact_source_revision(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    path = tmp_path / "formula.txt"
    original = "桂枝汤：桂枝三两，芍药三两。主治太阳中风。"
    path.write_text(f"卷一\n第一章\n{original}", encoding="utf-8")
    imported = import_file(
        path, SourceMetadata(source_type="CLASSIC", title="方剂试验古籍"),
        request_key=f"knowledge:{uuid4()}", store=store,
    )
    assert process_next_import(store=store).status == "PARSED"
    _finish_segment(imported.import_job_id, store)
    with SessionLocal() as session:
        paragraph = session.scalar(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == imported.source_revision_id,
            TextSegmentRevision.segment_type == "PARAGRAPH",
        ))
    evidence_revision_id = create_evidence([paragraph.id], strength="DIRECT")
    trace = trace_evidence(evidence_revision_id)
    assert trace["quote_text"] == original
    assert trace["source_revision_id"] == str(imported.source_revision_id)
    assert trace["segment_revision_ids"] == [str(paragraph.id)]
    assert trace["status"] == "DRAFT"

    herb_offset = original.index("桂枝三两")
    herb_mention_id = create_entity_mention(
        paragraph.id, start_offset=herb_offset,
        end_offset=herb_offset + 2, entity_type="HERB",
    )
    syndrome_offset = original.index("太阳中风")
    syndrome_mention_id = create_entity_mention(
        paragraph.id, start_offset=syndrome_offset,
        end_offset=syndrome_offset + 4, entity_type="SYNDROME",
    )
    herb_concept_id = create_concept(
        "桂枝", concept_type="HERB", evidence_revision_id=evidence_revision_id,
        mention_ids=(herb_mention_id,), terms=("桂枝尖",),
    )
    syndrome_id = create_concept(
        "太阳中风", concept_type="SYNDROME", evidence_revision_id=evidence_revision_id,
        mention_ids=(syndrome_mention_id,),
    )
    relation_id = create_relation(
        herb_concept_id, syndrome_id, relation_type="USED_FOR",
        assertion_text="桂枝汤用于太阳中风", evidence_revision_id=evidence_revision_id,
    )
    herb_id = create_herb("桂枝", evidence_revision_id=evidence_revision_id)
    formula_revision_id = create_formula(
        "桂枝汤", evidence_revision_id=evidence_revision_id,
        ingredients=(
            IngredientSpec(original_name="桂枝", herb_id=herb_id, amount_original="三两"),
            IngredientSpec(original_name="芍药", amount_original="三两"),
        ),
        indications="太阳中风",
    )
    for kind, object_id in (
        ("concept", herb_concept_id), ("relation", relation_id),
        ("herb", herb_id), ("formula_revision", formula_revision_id),
    ):
        assert trace_knowledge(kind, object_id)["evidence"][0]["quote_text"] == original
    with SessionLocal() as session:
        assert session.get(EntityMention, herb_mention_id).surface_text == "桂枝"
        assert session.scalar(select(ConceptEvidence).where(
            ConceptEvidence.concept_id == herb_concept_id
        )).evidence_revision_id == evidence_revision_id
        assert session.scalar(select(RelationEvidence).where(
            RelationEvidence.relation_id == relation_id
        )).evidence_revision_id == evidence_revision_id
        assert session.scalar(select(HerbEvidence).where(
            HerbEvidence.herb_id == herb_id
        )).evidence_revision_id == evidence_revision_id
        assert session.scalar(select(FormulaEvidence).where(
            FormulaEvidence.formula_revision_id == formula_revision_id
        )).evidence_revision_id == evidence_revision_id
        assert [row.original_name for row in session.scalars(select(FormulaIngredient).where(
            FormulaIngredient.formula_revision_id == formula_revision_id
        ).order_by(FormulaIngredient.sequence_no))] == ["桂枝", "芍药"]
        assert verify_chain(session)

    second_evidence_revision_id = create_evidence(
        [paragraph.id], strength="DIRECT", evidence_id=UUID(trace["evidence_id"])
    )
    with SessionLocal() as session:
        first = session.get(EvidenceRevision, evidence_revision_id)
        second = session.get(EvidenceRevision, second_evidence_revision_id)
        assert first.revision_no == 1
        assert second.revision_no == 2
        assert first.quote_text == second.quote_text == original

    formula_id = None
    with SessionLocal() as session:
        formula_id = session.get(FormulaRevision, formula_revision_id).formula_id
    second_formula_revision_id = create_formula(
        "桂枝汤", evidence_revision_id=evidence_revision_id,
        ingredients=(IngredientSpec(original_name="桂枝"),), formula_id=formula_id,
    )
    with SessionLocal() as session:
        assert session.get(FormulaRevision, second_formula_revision_id).revision_no == 2
        assert session.get(FormulaRevision, formula_revision_id).revision_no == 1


def test_evidence_rejects_missing_segment():
    with pytest.raises(ValueError, match="does not exist"):
        create_evidence([uuid4()], strength="DIRECT")
