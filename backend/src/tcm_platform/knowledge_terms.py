"""Human term adjudication with scoped evidence and append-only concept drafts."""

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.models import (
    Concept,
    ConceptEvidence,
    ConceptTerm,
    EntityMention,
    EvidenceRevision,
    EvidenceSegmentRef,
    TermResolution,
    TextSegmentRevision,
)

DECISIONS = frozenset({"NORMALIZE", "HISTORICAL_SYNONYM", "DISTINCT", "UNRESOLVED"})


@dataclass(frozen=True)
class TermSourceSpec:
    evidence_revision_id: UUID
    segment_revision_id: UUID
    start_offset: int
    end_offset: int


def _source(session: Session, spec: TermSourceSpec) -> dict:
    evidence = session.get(EvidenceRevision, spec.evidence_revision_id)
    segment = session.get(TextSegmentRevision, spec.segment_revision_id)
    ref = session.scalar(select(EvidenceSegmentRef.id).where(
        EvidenceSegmentRef.evidence_revision_id == spec.evidence_revision_id,
        EvidenceSegmentRef.segment_revision_id == spec.segment_revision_id,
    ))
    if evidence is None or segment is None or ref is None or (
        segment.source_revision_id != evidence.source_revision_id
    ):
        raise ValueError("term source must belong to the exact evidence revision")
    if not 0 <= spec.start_offset < spec.end_offset <= len(segment.original_text):
        raise ValueError("term source offsets exceed the original text")
    if hashlib.sha256(segment.original_text.encode("utf-8")).hexdigest() != segment.checksum:
        raise ValueError("term source checksum differs")
    return {
        "evidence_revision_id": str(evidence.id), "segment_revision_id": str(segment.id),
        "start_offset": spec.start_offset, "end_offset": spec.end_offset,
        "quote_text": segment.original_text[spec.start_offset:spec.end_offset],
        "segment_checksum": segment.checksum,
    }


def adjudicate_term(
    source_concept_id: UUID, *, decision: str, basis: str, actor_id: str,
    sources: tuple[TermSourceSpec, ...], canonical_name: str | None = None,
    concept_type: str | None = None, related_concept_id: UUID | None = None,
    mention_ids: tuple[UUID, ...] = (),
) -> UUID:
    """Clone selected exact mentions; never merge identities or modify an old candidate.

    An empty mention selection means all mentions of the source concept. Era and
    school are inherited, including nulls. A historical synonym names a reviewed
    comparison concept but retains an independent, source-scoped concept identity.
    """
    if decision not in DECISIONS:
        raise ValueError("unsupported term decision")
    if not basis.strip() or not actor_id.strip() or len(actor_id) > 120:
        raise ValueError("term decision requires basis and actor (1-120 characters)")
    if not sources or len(set(sources)) != len(sources):
        raise ValueError("term decision requires unique exact sources")
    if len(set(mention_ids)) != len(mention_ids):
        raise ValueError("selected mentions must be unique")
    with SessionLocal.begin() as session:
        # Sorted parent locks also serialize two curators using reversed comparisons.
        ids = {source_concept_id} | ({related_concept_id} if related_concept_id else set())
        parents = {row.id: row for row in session.scalars(select(Concept).where(
            Concept.id.in_(ids)
        ).order_by(Concept.id).with_for_update())}
        old = parents.get(source_concept_id)
        related = parents.get(related_concept_id)
        if old is None or (related_concept_id is not None and related is None):
            raise ValueError("source or related concept does not exist")
        if related_concept_id == source_concept_id:
            raise ValueError("comparison concept must have a distinct identity")
        if decision == "HISTORICAL_SYNONYM":
            if related is None or related.status != "REVIEWED":
                raise ValueError("historical synonym requires an explicit reviewed comparison concept")
            if canonical_name is not None or concept_type is not None:
                raise ValueError("historical synonym uses the comparison name and type")
            canonical_name, concept_type = related.canonical_name, related.concept_type
        else:
            canonical_name = canonical_name if canonical_name is not None else old.canonical_name
            concept_type = concept_type if concept_type is not None else old.concept_type
        if not canonical_name.strip() or len(canonical_name) > 300:
            raise ValueError("canonical name must be 1-300 characters")
        if not concept_type.strip() or len(concept_type) > 60:
            raise ValueError("concept type must be 1-60 characters")
        if decision == "UNRESOLVED" and (
            canonical_name != old.canonical_name or concept_type != old.concept_type
            or related is not None
        ):
            raise ValueError("unresolved decision must retain original meaning and unknowns")
        mentions = list(session.scalars(select(EntityMention).where(
            EntityMention.concept_id == old.id
        ).order_by(EntityMention.id)))
        if mention_ids:
            by_id = {mention.id: mention for mention in mentions}
            if any(mention_id not in by_id for mention_id in mention_ids):
                raise ValueError("selected mention must belong to the source concept")
            mentions = [by_id[mention_id] for mention_id in mention_ids]
        if not mentions:
            raise ValueError("term decision requires exact source mentions")
        evidence_ids = set(session.scalars(select(ConceptEvidence.evidence_revision_id).where(
            ConceptEvidence.concept_id == old.id
        )))
        proof = [_source(session, spec) for spec in sources]
        comparison = None
        if decision == "HISTORICAL_SYNONYM":
            comparison_evidence = set(session.scalars(select(ConceptEvidence.evidence_revision_id).where(
                ConceptEvidence.concept_id == related.id
            )))
            if not any(UUID(item["evidence_revision_id"]) in comparison_evidence for item in proof):
                raise ValueError("historical synonym requires exact comparison evidence sources")
            comparison = {
                "concept_id": str(related.id), "canonical_name": related.canonical_name,
                "concept_type": related.concept_type, "era": related.era, "school": related.school,
            }
        anchors = []
        for mention in mentions:
            evidence_id = next((item for item in sorted(evidence_ids) if session.scalar(
                select(EvidenceSegmentRef.id).where(
                    EvidenceSegmentRef.evidence_revision_id == item,
                    EvidenceSegmentRef.segment_revision_id == mention.segment_revision_id,
                )) is not None), None)
            if evidence_id is None:
                raise ValueError("source mention is not in the source concept evidence")
            anchor = _source(session, TermSourceSpec(
                evidence_id, mention.segment_revision_id, mention.start_offset, mention.end_offset,
            ))
            if anchor["quote_text"] != mention.surface_text:
                raise ValueError("source mention differs from exact original text")
            anchors.append({**anchor, "source_mention_id": str(mention.id)})
        evidence_ids = {UUID(item["evidence_revision_id"]) for item in [*anchors, *proof]}
        new_id_value = new_id()
        session.add(Concept(
            id=new_id_value, public_id=f"CON-{new_id_value}", canonical_name=canonical_name.strip(),
            concept_type=concept_type.strip(), era=old.era, school=old.school, status="DRAFT",
            requires_term_resolution=True,
        ))
        session.flush()
        session.add(ConceptTerm(
            concept_id=new_id_value, term=canonical_name.strip(), term_kind="PREFERRED",
            era=old.era, school=old.school,
        ))
        for surface in sorted({mention.surface_text for mention in mentions}):
            if surface != canonical_name.strip():
                session.add(ConceptTerm(
                    concept_id=new_id_value, term=surface,
                    term_kind="HISTORICAL" if decision == "HISTORICAL_SYNONYM" else "ORIGINAL",
                    era=old.era, school=old.school,
                ))
        for mention, anchor in zip(mentions, anchors, strict=True):
            clone_id = new_id()
            session.add(EntityMention(
                id=clone_id, concept_id=new_id_value,
                segment_revision_id=mention.segment_revision_id, surface_text=mention.surface_text,
                entity_type=concept_type.strip(), start_offset=mention.start_offset,
                end_offset=mention.end_offset,
                status="AMBIGUOUS_DRAFT" if decision == "UNRESOLVED" else "RESOLVED_DRAFT",
            ))
            anchor["resolved_mention_id"] = str(clone_id)
        session.add_all([ConceptEvidence(concept_id=new_id_value, evidence_revision_id=evidence_id)
                         for evidence_id in sorted(evidence_ids)])
        session.flush()  # Finish all components before freezing the adjudication record.
        resolution = TermResolution(
            id=new_id(), source_concept_id=old.id, resolved_concept_id=new_id_value,
            related_concept_id=related_concept_id, decision=decision,
            basis=basis.strip(), actor_id=actor_id.strip(), provenance={
                "era": old.era, "school": old.school,
                "canonical_name": canonical_name.strip(), "concept_type": concept_type.strip(),
                "mentions": anchors, "sources": proof,
                "comparison": comparison,
            },
        )
        session.add(resolution)
        session.flush()
        validate_term_resolution(session, new_id_value)
        append_event(session, event_type="term.adjudication_proposed", actor_id=actor_id.strip(),
                     aggregate_id=new_id_value, payload={
                         "resolution_id": str(resolution.id), "source_concept_id": str(old.id),
                         "decision": decision, "related_concept_id": (
                             str(related_concept_id) if related_concept_id else None),
                     })
        return new_id_value


def validate_term_resolution(session: Session, concept_id: UUID, *,
                             require_resolved: bool = False) -> dict | None:
    resolution = session.scalar(select(TermResolution).where(
        TermResolution.resolved_concept_id == concept_id
    ))
    if resolution is None:
        if require_resolved and (session.get(Concept, concept_id).requires_term_resolution
                                or session.scalar(select(EntityMention.id).where(
                                    EntityMention.concept_id == concept_id,
                                    EntityMention.status == "AMBIGUOUS_DRAFT",
                                ).limit(1)) is not None):
            raise ValueError("ambiguous term requires explicit human adjudication")
        return None
    if require_resolved and resolution.decision == "UNRESOLVED":
        raise ValueError("unresolved term cannot be approved or snapshotted")
    concept = session.get(Concept, concept_id)
    provenance = resolution.provenance
    if any(getattr(concept, key) != provenance[key] for key in (
        "canonical_name", "concept_type", "era", "school"
    )):
        raise ValueError("resolved concept differs from its frozen adjudication")
    evidence_ids = set(session.scalars(select(ConceptEvidence.evidence_revision_id).where(
        ConceptEvidence.concept_id == concept_id
    )))
    if require_resolved and resolution.decision == "HISTORICAL_SYNONYM":
        related = session.get(Concept, resolution.related_concept_id)
        if related is None or related.status != "REVIEWED":
            raise ValueError("historical synonym comparison must remain reviewed")
        if any(getattr(related, key) != provenance["comparison"][key] for key in (
            "canonical_name", "concept_type", "era", "school"
        )):
            raise ValueError("historical comparison differs from its frozen adjudication")
    for item in [*provenance["mentions"], *provenance["sources"]]:
        spec = TermSourceSpec(UUID(item["evidence_revision_id"]), UUID(item["segment_revision_id"]),
                              item["start_offset"], item["end_offset"])
        current = _source(session, spec)
        if spec.evidence_revision_id not in evidence_ids or any(
            current[key] != item[key] for key in ("quote_text", "segment_checksum")
        ):
            raise ValueError("term adjudication provenance differs")
        if require_resolved and session.get(EvidenceRevision, spec.evidence_revision_id).status != (
            "REVIEWED"
        ):
            raise ValueError("term adjudication evidence must be reviewed first")
    for item in provenance["mentions"]:
        mention = session.get(EntityMention, UUID(item["resolved_mention_id"]))
        if mention is None or mention.concept_id != concept_id or (
            str(mention.segment_revision_id), mention.start_offset, mention.end_offset,
            mention.surface_text, mention.entity_type
        ) != (item["segment_revision_id"], item["start_offset"], item["end_offset"],
              item["quote_text"], concept.concept_type):
            raise ValueError("resolved mention differs from its frozen adjudication")
    return {
        "resolution_id": str(resolution.id), "source_concept_id": str(resolution.source_concept_id),
        "related_concept_id": (str(resolution.related_concept_id)
                               if resolution.related_concept_id else None),
        "decision": resolution.decision, "basis": resolution.basis,
        "actor_id": resolution.actor_id, **provenance,
    }
