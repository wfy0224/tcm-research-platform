"""Conservative local rules: exact mentions and explicitly named conditions, all drafts."""

import re
from dataclasses import asdict, dataclass
from itertools import groupby
from uuid import UUID

from sqlalchemy import select

from tcm_platform.audit import append_event
from tcm_platform.db import SessionLocal
from tcm_platform.ids import new_id
from tcm_platform.knowledge_formula_extraction import scan_formula_candidates
from tcm_platform.knowledge_formula_provenance import FormulaFieldSourceSpec
from tcm_platform.knowledge_service import (
    CITABLE_SEGMENT_TYPES,
    create_concept,
    create_entity_mention,
    create_evidence,
    create_formula,
    create_relation,
    trace_evidence,
)
from tcm_platform.models import (
    ConceptEvidence,
    EntityMention,
    ImportJob,
    KnowledgeExtraction,
    SourceRevision,
    TextSegmentRevision,
)

# This is an engineering seed vocabulary, not a clinical ontology or synonym map.
# A change to the vocabulary or rules MUST increment the persisted version.
EXTRACTOR_VERSION = "local-exact-terms/v5"
TERMS = {
    "CONDITION": ("太陽病", "太陽中風", "中風", "傷寒", "溫病", "風溫", "壞病"),
    "SYMPTOM": ("脈浮", "脈緩", "脈浮緊", "脈微弱", "脈洪大", "頭痛", "頭項強痛",
                "發熱", "惡寒", "惡風", "汗出", "自汗出", "小便不利", "乾嘔", "譫語",
                "厥逆", "咽中乾", "煩躁", "項背強几几"),
    "FORMULA": ("桂枝湯", "桂枝加葛根湯", "桂枝加附子湯", "桂枝去芍藥加附子湯",
                "桂枝麻黃各半湯", "桂枝二麻黃一湯", "白虎加人參湯", "桂枝二越婢一湯",
                "甘草乾薑湯", "芍藥甘草湯", "調胃承氣湯", "承氣湯", "四逆湯"),
}


@dataclass(frozen=True)
class MentionCandidate:
    surface_text: str
    entity_type: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class RelationCandidate:
    subject_start: int
    object_start: int
    start_offset: int
    end_offset: int
    assertion_text: str
    relation_type: str = "NAMED_AS"


def scan_candidates(original_text: str) -> tuple[list[MentionCandidate], list[RelationCandidate]]:
    """Offsets are Python Unicode character indices into untouched original text."""
    term_types = {}
    for kind, terms in TERMS.items():
        for term in terms:
            term_types.setdefault(term, set()).add(kind)
    if not term_types:
        return [], []
    pattern = re.compile("|".join(re.escape(term) for term in sorted(
        term_types, key=lambda term: (-len(term), term)
    )))
    mentions = [MentionCandidate(match.group(), kind, *match.span())
                for match in pattern.finditer(original_text)
                for kind in sorted(term_types[match.group()])]
    conditions = TERMS.get("CONDITION", ())
    if not conditions:
        return mentions, []
    naming_pattern = re.compile(r"(?:名為|名曰|者，為)(" + "|".join(
        re.escape(term) for term in sorted(conditions, key=lambda term: (-len(term), term))
    ) + r")")
    relations = []
    for clause in re.finditer(r"[^。；！？\n]+[。；！？]?", original_text):
        for naming in naming_pattern.finditer(clause.group()):
            object_start = clause.start() + naming.start(1)
            target = next((m for m in mentions if m.start_offset == object_start
                           and len(term_types[m.surface_text]) == 1), None)
            subject = next((m for m in mentions if m.entity_type == "CONDITION"
                            and len(term_types[m.surface_text]) == 1
                            and clause.start() <= m.start_offset < object_start), None)
            if target is not None and subject is not None and subject.surface_text != target.surface_text:
                relations.append(RelationCandidate(
                    subject.start_offset, object_start, clause.start(), clause.end(), clause.group(),
                ))
    return mentions, relations


def extract_source_candidates(source_revision_id: UUID, *, actor_id: str = "local-curator") -> dict:
    """Freeze one batch and all draft objects in the same transaction; serialize replays."""
    if not actor_id.strip() or len(actor_id) > 120:
        raise ValueError("actor must be 1-120 characters")
    with SessionLocal.begin() as session:
        source = session.scalar(select(SourceRevision).where(
            SourceRevision.id == source_revision_id
        ).with_for_update())
        if source is None:
            raise ValueError("source revision does not exist")
        previous = session.scalar(select(KnowledgeExtraction).where(
            KnowledgeExtraction.source_revision_id == source_revision_id,
            KnowledgeExtraction.extractor_version == EXTRACTOR_VERSION,
        ))
        if previous is not None:
            return {"extraction_id": str(previous.id), **previous.manifest}
        imported = session.scalar(select(ImportJob).where(
            ImportJob.source_revision_id == source_revision_id
        ))
        if imported is None or imported.status != "SEGMENTED":
            raise ValueError("source revision has not completed segmentation")
        segments = list(session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == source_revision_id,
            TextSegmentRevision.segment_type.in_(CITABLE_SEGMENT_TYPES),
        ).order_by(TextSegmentRevision.sequence_no)))
        # The resolver stores paragraphs and their sentence children. Extract each
        # original character once, keeping the full paragraph's conditional context.
        citable_segment_ids = {segment.segment_id for segment in segments}
        segments = [segment for segment in segments
                    if segment.parent_segment_id not in citable_segment_ids]
        # Read frozen source metadata, never the mutable SourceDocument fields.
        era = source.metadata_snapshot.get("era")
        school = source.metadata_snapshot.get("school")
        manifest = {
            "source_revision_id": str(source.id), "extractor_version": EXTRACTOR_VERSION,
            "era": era, "school": school, "segments": [],
            "segment_count": len(segments), "mention_count": 0, "relation_count": 0,
            "concept_count": 0, "status": "DRAFT",
            "formulas": [], "formula_count": 0,
        }
        concept_ids = {}
        for segment in segments:
            mentions, relations = scan_candidates(segment.original_text)
            row = {"segment_revision_id": str(segment.id), "text_checksum": segment.checksum,
                   "structural_locator": segment.structural_locator, "evidence_revision_id": None,
                   "mentions": [], "relations": []}
            manifest["segments"].append(row)
            if not mentions:
                continue
            evidence_id = create_evidence([segment.id], strength="DIRECT", actor_id=actor_id,
                                          _session=session)
            row["evidence_revision_id"] = str(evidence_id)
            concepts_by_start = {}
            linked = set()
            for mention in mentions:
                ambiguous = sum(m.start_offset == mention.start_offset for m in mentions) > 1
                mention_id = create_entity_mention(
                    segment.id, start_offset=mention.start_offset, end_offset=mention.end_offset,
                    entity_type=mention.entity_type, actor_id=actor_id, _session=session,
                )
                key = (mention.entity_type, mention.surface_text, era, school)
                concept_id = concept_ids.get(key)
                if concept_id is None:
                    concept_id = create_concept(
                        mention.surface_text, concept_type=mention.entity_type,
                        evidence_revision_id=evidence_id, mention_ids=(mention_id,),
                        era=era, school=school, actor_id=actor_id, _session=session,
                        requires_term_resolution=ambiguous,
                    )
                    concept_ids[key] = concept_id
                    linked.add(concept_id)
                else:
                    if concept_id not in linked:
                        session.add(ConceptEvidence(concept_id=concept_id,
                                                    evidence_revision_id=evidence_id))
                        linked.add(concept_id)
                    entity = session.get(EntityMention, mention_id)
                    entity.concept_id = concept_id
                    entity.status = "RESOLVED_DRAFT"
                if ambiguous:
                    session.get(EntityMention, mention_id).status = "AMBIGUOUS_DRAFT"
                concepts_by_start[mention.start_offset] = concept_id
                row["mentions"].append({**asdict(mention), "mention_id": str(mention_id),
                                        "concept_id": str(concept_id), "ambiguous": ambiguous})
            for relation in relations:
                relation_id = create_relation(
                    concepts_by_start[relation.subject_start], concepts_by_start[relation.object_start],
                    relation_type=relation.relation_type, assertion_text=relation.assertion_text,
                    evidence_revision_id=evidence_id, actor_id=actor_id, _session=session,
                )
                row["relations"].append({**asdict(relation), "relation_id": str(relation_id)})
            manifest["mention_count"] += len(mentions)
            manifest["relation_count"] += len(relations)
        manifest["concept_count"] = len(concept_ids)
        # Cross-paragraph formulas must stay within a contiguous sibling range.
        # Paragraph/sentence duplication was removed above; never join across parents/types.
        for _, siblings in groupby(segments, key=lambda s: (s.parent_segment_id, s.segment_type)):
            group = list(siblings)
            for candidate in scan_formula_candidates([s.original_text for s in group]):
                cited = [group[i] for i in candidate.segment_indices]
                evidence_id = create_evidence([s.id for s in cited], strength="DIRECT",
                                              actor_id=actor_id, _session=session)
                sources = tuple(FormulaFieldSourceSpec(
                    field_key=span.field_key, evidence_revision_id=evidence_id,
                    segment_revision_id=group[span.segment_index].id,
                    start_offset=span.start_offset, end_offset=span.end_offset, basis=span.basis,
                ) for span in candidate.spans)
                revision_id = create_formula(
                    candidate.original_name, ingredients=candidate.ingredients,
                    method=candidate.method, evidence_revision_id=evidence_id,
                    field_sources=sources, actor_id=actor_id, _session=session,
                )
                manifest["formulas"].append({
                    "formula_revision_id": str(revision_id),
                    "original_name": candidate.original_name, "method": candidate.method,
                    "ingredients": [asdict(i) for i in candidate.ingredients],
                    "evidence_revision_id": str(evidence_id),
                    "segment_revision_ids": [str(s.id) for s in cited],
                    "field_sources": [{
                        "field_key": s.field_key, "segment_revision_id": str(s.segment_revision_id),
                        "start_offset": s.start_offset, "end_offset": s.end_offset, "basis": s.basis,
                    } for s in sources], "status": "DRAFT",
                })
        manifest["formula_count"] = len(manifest["formulas"])
        extraction_id = new_id()
        session.add(KnowledgeExtraction(id=extraction_id, source_revision_id=source.id,
                                        extractor_version=EXTRACTOR_VERSION, manifest=manifest))
        append_event(session, event_type="knowledge.candidates_extracted", actor_id=actor_id,
                     aggregate_id=extraction_id, payload={
                         "source_revision_id": str(source.id), "extractor_version": EXTRACTOR_VERSION,
                         "mention_count": manifest["mention_count"],
                         "relation_count": manifest["relation_count"],
                         "formula_count": manifest["formula_count"],
                     })
        return {"extraction_id": str(extraction_id), **manifest}


def trace_extraction(extraction_id: UUID) -> dict:
    """Return the frozen spans alongside the existing exact evidence provenance chain."""
    with SessionLocal() as session:
        batch = session.get(KnowledgeExtraction, extraction_id)
        if batch is None:
            raise ValueError("knowledge extraction does not exist")
        manifest = batch.manifest
    evidence_ids = dict.fromkeys(row["evidence_revision_id"] for row in (
        *manifest["segments"], *manifest.get("formulas", []),
    ) if row["evidence_revision_id"] is not None)
    evidence = [trace_evidence(UUID(evidence_id)) for evidence_id in evidence_ids]
    return {"extraction_id": str(extraction_id), "manifest": manifest, "evidence": evidence}
