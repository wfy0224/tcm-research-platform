"""Draft knowledge authoring with exact source and evidence provenance."""

import hashlib
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_formula_provenance import (
    FormulaFieldSourceSpec,
    add_formula_field_sources,
    validate_formula_field_sources,
)
from tcm_platform.models import (
    Concept,
    ConceptEvidence,
    ConceptTerm,
    EntityMention,
    Evidence,
    EvidenceRevision,
    EvidenceSegmentRef,
    Formula,
    FormulaEvidence,
    FormulaIngredient,
    FormulaRevision,
    Herb,
    HerbEvidence,
    HerbTerm,
    ImportJob,
    KnowledgeRelation,
    RelationEvidence,
    SourceDocument,
    SourceRevision,
    TextSegmentRevision,
)
from tcm_platform.segmentation import PARAGRAPH_TYPES

EVIDENCE_STRENGTHS = frozenset(
    {"DIRECT", "INDIRECT", "INTERPRETIVE", "EMPIRICAL", "BACKGROUND", "UNVERIFIED"}
)
CITABLE_SEGMENT_TYPES = frozenset(
    {"CLAUSE", "PARAGRAPH", "SENTENCE", "COMMENTARY", "NOTE", "CASE_NOTE", "FORMULA_TEXT"}
)
SOURCE_CLASS = {
    "CLASSIC": "CLASSIC",
    "PHYSICIAN_WORK": "PHYSICIAN_WORK",
    "COMMENTARY": "COMMENTARY",
    "TEXTBOOK": "TEXTBOOK",
    "GUIDELINE": "GUIDELINE",
    "MODERN_RESEARCH": "MODERN_RESEARCH",
    "MEDICAL_CASE_COLLECTION": "CASE",
    "PATIENT_CASE": "CASE",
}


@dataclass(frozen=True)
class IngredientSpec:
    original_name: str
    herb_id: UUID | None = None
    amount_original: str | None = None
    amount_normalized: str | None = None
    unit: str | None = None
    dose_ratio: str | None = None
    role: str | None = None
    processing: str | None = None


def _required(value: str, field: str, max_length: int) -> str:
    value = value.strip()
    if not value or len(value) > max_length:
        raise ValueError(f"{field} must be 1-{max_length} characters")
    return value


def _evidence(session: Session, revision_id: UUID) -> EvidenceRevision:
    revision = session.get(EvidenceRevision, revision_id)
    if revision is None:
        raise ValueError("evidence revision does not exist")
    return revision


def create_evidence(
    segment_revision_ids: list[UUID],
    *,
    strength: str,
    actor_id: str = "local-curator",
    evidence_id: UUID | None = None,
    _session: Session | None = None,
) -> UUID:
    """Build a draft quote from one contiguous sibling range, never from free text."""
    if not segment_revision_ids or len(segment_revision_ids) > 100:
        raise ValueError("evidence requires 1-100 segment revisions")
    if len(set(segment_revision_ids)) != len(segment_revision_ids):
        raise ValueError("evidence segment revisions must be unique")
    if strength not in EVIDENCE_STRENGTHS:
        raise ValueError("unknown evidence strength")
    with nullcontext(_session) if _session is not None else SessionLocal.begin() as session:
        segments = list(session.scalars(
            select(TextSegmentRevision)
            .where(TextSegmentRevision.id.in_(segment_revision_ids))
            .order_by(TextSegmentRevision.sequence_no)
        ))
        if len(segments) != len(segment_revision_ids):
            raise ValueError("segment revision does not exist")
        first, last = segments[0], segments[-1]
        if first.segment_type not in CITABLE_SEGMENT_TYPES:
            raise ValueError("structural headings cannot be cited as evidence")
        compatible_types = PARAGRAPH_TYPES if first.segment_type in PARAGRAPH_TYPES else {first.segment_type}
        if any(
            row.source_revision_id != first.source_revision_id
            or row.segment_type not in compatible_types
            or row.parent_segment_id != first.parent_segment_id
            for row in segments
        ):
            raise ValueError("evidence range must share a source revision, parent, and level")
        siblings = list(session.scalars(
            select(TextSegmentRevision)
            .where(
                TextSegmentRevision.source_revision_id == first.source_revision_id,
                TextSegmentRevision.parent_segment_id == first.parent_segment_id,
                TextSegmentRevision.sequence_no.between(first.sequence_no, last.sequence_no),
            )
            .order_by(TextSegmentRevision.sequence_no)
        ))
        if [row.id for row in siblings] != [row.id for row in segments]:
            raise ValueError("evidence range must be contiguous")
        source_revision = session.get(SourceRevision, first.source_revision_id)
        source = session.get(SourceDocument, source_revision.source_id)
        import_job = session.scalar(
            select(ImportJob).where(ImportJob.source_revision_id == source_revision.id)
        )
        if import_job is None or import_job.status != "SEGMENTED":
            raise ValueError("source revision has not completed segmentation")
        if evidence_id is None:
            evidence_id = new_id()
            session.add(Evidence(
                id=evidence_id, public_id=f"EV-{evidence_id}", source_id=source.id
            ))
            session.flush()
            revision_no = 1
        else:
            evidence = session.scalar(
                select(Evidence).where(Evidence.id == evidence_id).with_for_update()
            )
            if evidence is None or evidence.source_id != source.id:
                raise ValueError("evidence identity belongs to another source or does not exist")
            revision_no = (session.scalar(select(func.max(EvidenceRevision.revision_no)).where(
                EvidenceRevision.evidence_id == evidence_id
            )) or 0) + 1
        quote = "\n".join(row.original_text for row in segments)
        revision_id = new_id()
        session.add(EvidenceRevision(
            id=revision_id,
            evidence_id=evidence_id,
            revision_no=revision_no,
            source_revision_id=source_revision.id,
            anchor_segment_revision_id=first.id,
            quote_text=quote,
            context_before=first.context_before,
            context_after=last.context_after,
            citation_locator={
                "source_revision_id": str(source_revision.id),
                "start": first.structural_locator,
                "end": last.structural_locator,
            },
            source_class=SOURCE_CLASS.get(source.source_type, "OTHER"),
            evidence_strength=strength,
            status="DRAFT",
            quote_checksum=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        ))
        session.flush()
        session.add_all([
            EvidenceSegmentRef(
                evidence_revision_id=revision_id,
                segment_revision_id=row.id,
                sequence_no=index,
            )
            for index, row in enumerate(segments)
        ])
        append_event(
            session, event_type="evidence.draft_created", actor_id=actor_id,
            aggregate_id=evidence_id,
            payload={"revision_id": str(revision_id), "source_revision_id": str(source_revision.id)},
        )
        return revision_id


def create_entity_mention(
    segment_revision_id: UUID,
    *,
    start_offset: int,
    end_offset: int,
    entity_type: str,
    actor_id: str = "local-curator",
    _session: Session | None = None,
) -> UUID:
    entity_type = _required(entity_type, "entity_type", 60)
    with nullcontext(_session) if _session is not None else SessionLocal.begin() as session:
        segment = session.get(TextSegmentRevision, segment_revision_id)
        if segment is None or segment.segment_type not in CITABLE_SEGMENT_TYPES:
            raise ValueError("mention requires a citable segment revision")
        if not 0 <= start_offset < end_offset <= len(segment.original_text):
            raise ValueError("mention offsets exceed the original text")
        mention_id = new_id()
        session.add(EntityMention(
            id=mention_id,
            segment_revision_id=segment.id,
            surface_text=segment.original_text[start_offset:end_offset],
            entity_type=entity_type,
            start_offset=start_offset,
            end_offset=end_offset,
            status="CANDIDATE",
        ))
        append_event(
            session, event_type="entity_mention.created", actor_id=actor_id,
            aggregate_id=mention_id, payload={"segment_revision_id": str(segment.id)},
        )
        return mention_id


def create_concept(
    canonical_name: str,
    *,
    concept_type: str,
    evidence_revision_id: UUID,
    terms: tuple[str, ...] = (),
    mention_ids: tuple[UUID, ...] = (),
    era: str | None = None,
    school: str | None = None,
    requires_term_resolution: bool = False,
    actor_id: str = "local-curator",
    _session: Session | None = None,
) -> UUID:
    canonical_name = _required(canonical_name, "canonical_name", 300)
    concept_type = _required(concept_type, "concept_type", 60)
    if len(set(terms)) != len(terms):
        raise ValueError("concept terms must be unique")
    with nullcontext(_session) if _session is not None else SessionLocal.begin() as session:
        _evidence(session, evidence_revision_id)
        cited = set(session.scalars(select(EvidenceSegmentRef.segment_revision_id).where(
            EvidenceSegmentRef.evidence_revision_id == evidence_revision_id
        )))
        mentions = [session.get(EntityMention, mention_id) for mention_id in mention_ids]
        if any(mention is None or mention.segment_revision_id not in cited for mention in mentions):
            raise ValueError("concept mentions must belong to the cited evidence")
        concept_id = new_id()
        session.add(Concept(
            id=concept_id, public_id=f"CON-{concept_id}",
            canonical_name=canonical_name, concept_type=concept_type,
            era=era, school=school, status="DRAFT", row_version=1,
            requires_term_resolution=requires_term_resolution,
        ))
        session.flush()
        session.add(ConceptTerm(
            concept_id=concept_id, term=canonical_name, term_kind="PREFERRED",
            era=era, school=school,
        ))
        session.add_all([
            ConceptTerm(concept_id=concept_id, term=_required(term, "term", 300),
                        term_kind="ALIAS", era=era, school=school)
            for term in terms if term != canonical_name
        ])
        session.add(ConceptEvidence(
            concept_id=concept_id, evidence_revision_id=evidence_revision_id
        ))
        for mention in mentions:
            if mention.concept_id is not None:
                raise ValueError("mention is already resolved to a concept")
            mention.concept_id = concept_id
            mention.status = "RESOLVED_DRAFT"
        append_event(
            session, event_type="concept.draft_created", actor_id=actor_id,
            aggregate_id=concept_id, payload={"evidence_revision_id": str(evidence_revision_id)},
        )
        return concept_id


def create_relation(
    subject_concept_id: UUID,
    object_concept_id: UUID,
    *,
    relation_type: str,
    assertion_text: str,
    evidence_revision_id: UUID,
    actor_id: str = "local-curator",
    _session: Session | None = None,
) -> UUID:
    relation_type = _required(relation_type, "relation_type", 80)
    assertion_text = _required(assertion_text, "assertion_text", 4000)
    with nullcontext(_session) if _session is not None else SessionLocal.begin() as session:
        _evidence(session, evidence_revision_id)
        if session.get(Concept, subject_concept_id) is None:
            raise ValueError("subject concept does not exist")
        if session.get(Concept, object_concept_id) is None:
            raise ValueError("object concept does not exist")
        relation_id = new_id()
        session.add(KnowledgeRelation(
            id=relation_id, public_id=f"REL-{relation_id}",
            subject_concept_id=subject_concept_id, object_concept_id=object_concept_id,
            relation_type=relation_type, assertion_text=assertion_text, status="DRAFT",
        ))
        session.flush()
        session.add(RelationEvidence(
            relation_id=relation_id, evidence_revision_id=evidence_revision_id
        ))
        append_event(
            session, event_type="relation.draft_created", actor_id=actor_id,
            aggregate_id=relation_id, payload={"evidence_revision_id": str(evidence_revision_id)},
        )
        return relation_id


def create_herb(
    canonical_name: str,
    *,
    evidence_revision_id: UUID,
    terms: tuple[str, ...] = (),
    era: str | None = None,
    school: str | None = None,
    actor_id: str = "local-curator",
) -> UUID:
    canonical_name = _required(canonical_name, "canonical_name", 300)
    if len(set(terms)) != len(terms):
        raise ValueError("herb terms must be unique")
    with SessionLocal.begin() as session:
        _evidence(session, evidence_revision_id)
        herb_id = new_id()
        session.add(Herb(
            id=herb_id, public_id=f"HERB-{herb_id}", canonical_name=canonical_name,
            era=era, school=school, status="DRAFT",
        ))
        session.flush()
        session.add(HerbTerm(herb_id=herb_id, term=canonical_name, term_kind="PREFERRED"))
        session.add_all([
            HerbTerm(herb_id=herb_id, term=_required(term, "term", 300), term_kind="ALIAS")
            for term in terms if term != canonical_name
        ])
        session.add(HerbEvidence(herb_id=herb_id, evidence_revision_id=evidence_revision_id))
        append_event(
            session, event_type="herb.draft_created", actor_id=actor_id,
            aggregate_id=herb_id, payload={"evidence_revision_id": str(evidence_revision_id)},
        )
        return herb_id


def create_formula(
    original_name: str,
    *,
    evidence_revision_id: UUID,
    ingredients: tuple[IngredientSpec, ...],
    formula_id: UUID | None = None,
    era: str | None = None,
    school: str | None = None,
    indications: str | None = None,
    effects: str | None = None,
    method: str | None = None,
    dosage_form: str | None = None,
    preparation: str | None = None,
    cautions: str | None = None,
    field_sources: tuple[FormulaFieldSourceSpec, ...] = (),
    actor_id: str = "local-curator",
    _session: Session | None = None,
) -> UUID:
    original_name = _required(original_name, "original_name", 300)
    if not ingredients or len(ingredients) > 100:
        raise ValueError("formula requires 1-100 ingredients")
    with nullcontext(_session) if _session is not None else SessionLocal.begin() as session:
        _evidence(session, evidence_revision_id)
        if formula_id is None:
            formula_id = new_id()
            session.add(Formula(
                id=formula_id, public_id=f"FORM-{formula_id}",
                canonical_name=original_name, status="DRAFT",
            ))
            session.flush()
            revision_no = 1
        else:
            formula = session.scalar(select(Formula).where(Formula.id == formula_id).with_for_update())
            if formula is None:
                raise ValueError("formula identity does not exist")
            revision_no = (session.scalar(select(func.max(FormulaRevision.revision_no)).where(
                FormulaRevision.formula_id == formula_id
            )) or 0) + 1
        revision_id = new_id()
        session.add(FormulaRevision(
            id=revision_id, formula_id=formula_id, revision_no=revision_no,
            original_name=original_name, era=era, school=school, indications=indications,
            effects=effects, method=method, dosage_form=dosage_form,
            preparation=preparation, cautions=cautions, status="DRAFT", provenance_version=1,
        ))
        session.flush()
        for index, ingredient in enumerate(ingredients):
            name = _required(ingredient.original_name, "ingredient original_name", 300)
            if ingredient.herb_id is not None and session.get(Herb, ingredient.herb_id) is None:
                raise ValueError("ingredient herb does not exist")
            session.add(FormulaIngredient(
                formula_revision_id=revision_id, herb_id=ingredient.herb_id,
                original_name=name, amount_original=ingredient.amount_original,
                amount_normalized=ingredient.amount_normalized, unit=ingredient.unit,
                dose_ratio=ingredient.dose_ratio, role=ingredient.role,
                processing=ingredient.processing, sequence_no=index,
            ))
        session.add(FormulaEvidence(
            formula_revision_id=revision_id, evidence_revision_id=evidence_revision_id
        ))
        add_formula_field_sources(session, revision_id, field_sources)
        append_event(
            session, event_type="formula.draft_created", actor_id=actor_id,
            aggregate_id=formula_id,
            payload={"revision_id": str(revision_id), "evidence_revision_id": str(evidence_revision_id)},
        )
        return revision_id


def trace_evidence(evidence_revision_id: UUID) -> dict:
    """Return exact source text and locator; reject a broken provenance chain."""
    with SessionLocal() as session:
        revision = _evidence(session, evidence_revision_id)
        evidence = session.get(Evidence, revision.evidence_id)
        source_revision = session.get(SourceRevision, revision.source_revision_id)
        source = session.get(SourceDocument, source_revision.source_id)
        refs = list(session.scalars(
            select(EvidenceSegmentRef).where(
                EvidenceSegmentRef.evidence_revision_id == evidence_revision_id
            ).order_by(EvidenceSegmentRef.sequence_no)
        ))
        segments = [session.get(TextSegmentRevision, ref.segment_revision_id) for ref in refs]
        quote = "\n".join(segment.original_text for segment in segments)
        if (
            not segments or quote != revision.quote_text
            or hashlib.sha256(quote.encode("utf-8")).hexdigest() != revision.quote_checksum
            or any(segment.source_revision_id != source_revision.id for segment in segments)
            or segments[0].id != revision.anchor_segment_revision_id
            or revision.citation_locator.get("start") != segments[0].structural_locator
            or revision.citation_locator.get("end") != segments[-1].structural_locator
        ):
            raise ValueError("evidence provenance chain is inconsistent")
        return {
            "evidence_id": str(evidence.id),
            "evidence_revision_id": str(revision.id),
            "status": revision.status,
            "source_id": str(source.id),
            "source_title": source.title,
            "source_author": source.author,
            "source_era": source.era,
            "source_school": source.school,
            "source_edition": source.edition,
            "source_publication_year": source.publication_year,
            "source_revision_id": str(source_revision.id),
            "source_revision_no": source_revision.revision_no,
            "quote_text": quote,
            "context_before": revision.context_before,
            "context_after": revision.context_after,
            "citation_locator": revision.citation_locator,
            "segment_revision_ids": [str(segment.id) for segment in segments],
        }


def trace_knowledge(kind: str, object_id: UUID) -> dict:
    """Follow a draft knowledge object through EvidenceRevision to source text."""
    from tcm_platform.knowledge_terms import validate_term_resolution

    mapping = {
        "concept": (Concept, ConceptEvidence, ConceptEvidence.concept_id),
        "relation": (KnowledgeRelation, RelationEvidence, RelationEvidence.relation_id),
        "herb": (Herb, HerbEvidence, HerbEvidence.herb_id),
        "formula_revision": (
            FormulaRevision, FormulaEvidence, FormulaEvidence.formula_revision_id
        ),
    }
    if kind not in mapping:
        raise ValueError("unknown knowledge object kind")
    model, link_model, foreign_key = mapping[kind]
    with SessionLocal() as session:
        obj = session.get(model, object_id)
        if obj is None:
            raise ValueError("knowledge object does not exist")
        evidence_ids = list(session.scalars(
            select(link_model.evidence_revision_id).where(foreign_key == object_id)
        ))
        if not evidence_ids:
            raise ValueError("knowledge object has no cited evidence")
        name = (
            obj.canonical_name if kind in {"concept", "herb"}
            else obj.original_name if kind == "formula_revision" else obj.assertion_text
        )
        formula_provenance = (
            {"provenance_version": obj.provenance_version,
             "field_sources": validate_formula_field_sources(session, object_id)}
            if kind == "formula_revision" else {}
        )
        term_provenance = ({
            "concept_type": obj.concept_type, "era": obj.era, "school": obj.school,
            "requires_term_resolution": obj.requires_term_resolution,
            "term_resolution": validate_term_resolution(session, object_id),
            "terms": [{"term": term.term, "term_kind": term.term_kind,
                       "era": term.era, "school": term.school}
                      for term in session.scalars(select(ConceptTerm).where(
                          ConceptTerm.concept_id == object_id
                      ).order_by(ConceptTerm.term_kind, ConceptTerm.term))],
        } if kind == "concept" else {})
    return {
        "kind": kind,
        "object_id": str(object_id),
        "name": name,
        "evidence": [trace_evidence(revision_id) for revision_id in evidence_ids],
        **formula_provenance,
        **term_provenance,
    }
