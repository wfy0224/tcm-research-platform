"""Local knowledge workspace HTTP boundary over the existing application services."""

import base64
import binascii
import hashlib
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from tcm_platform.api_contract import (
    Actor,
    ApiError,
    accepted_job_response,
    enqueue_actor_job,
    required_idempotency_key,
    resolve_public_id,
)
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import ResourceClass
from tcm_platform.knowledge_extraction import EXTRACTOR_VERSION, extract_source_candidates
from tcm_platform.knowledge_publish import (
    ISSUE_TARGETS,
    REVIEW_TARGETS,
    activate_knowledge_version,
    compare_knowledge_versions,
    create_knowledge_version,
    open_quality_issue,
    resolve_quality_issue,
    review_object,
    supersede_reviewed_object,
)
from tcm_platform.knowledge_service import (
    IngredientSpec,
    create_concept,
    create_evidence,
    create_formula,
    create_herb,
    create_relation,
    trace_evidence,
)
from tcm_platform.local_auth import COOKIE_NAME, current_actor, require_csrf
from tcm_platform.models import (
    Concept,
    ConceptEvidence,
    ConceptTerm,
    Evidence,
    EvidenceRevision,
    Formula,
    FormulaEvidence,
    FormulaIngredient,
    FormulaRevision,
    Herb,
    HerbEvidence,
    HerbTerm,
    ImportJob,
    IndexBuild,
    KnowledgeExtraction,
    KnowledgeRelation,
    KnowledgeRuntimeState,
    KnowledgeVersion,
    KnowledgeVersionItem,
    QualityIssue,
    RelationEvidence,
    SourceDocument,
    SourceRevision,
    TaskJob,
    TextSegment,
    TextSegmentRevision,
)
from tcm_platform.publication_config import (
    is_local_configuration,
    publication_configuration,
    validate_local_configuration,
)
from tcm_platform.source_import import SourceMetadata, import_file

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ImportRequest(StrictModel):
    metadata: SourceMetadata
    file_format: Literal["txt", "pdf", "docx"]
    content_base64: str = Field(min_length=1)
    source_id: str | None = None


class EvidenceDraft(StrictModel):
    segment_ids: list[str] = Field(min_length=1, max_length=100)
    strength: Literal["DIRECT", "INDIRECT", "INTERPRETIVE", "EMPIRICAL", "BACKGROUND", "UNVERIFIED"]
    evidence_id: str | None = None


class ConceptDraft(StrictModel):
    canonical_name: str = Field(min_length=1, max_length=300)
    concept_type: str = Field(min_length=1, max_length=60)
    evidence_id: str
    evidence_revision_no: int = Field(ge=1)
    terms: list[str] = Field(default_factory=list, max_length=100)
    era: str | None = None
    school: str | None = None


class RelationDraft(StrictModel):
    subject_id: str
    object_id: str
    relation_type: str = Field(min_length=1, max_length=80)
    assertion_text: str = Field(min_length=1, max_length=4000)
    evidence_id: str
    evidence_revision_no: int = Field(ge=1)


class HerbDraft(StrictModel):
    canonical_name: str = Field(min_length=1, max_length=300)
    evidence_id: str
    evidence_revision_no: int = Field(ge=1)
    terms: list[str] = Field(default_factory=list, max_length=100)
    era: str | None = None
    school: str | None = None


class IngredientDraft(StrictModel):
    original_name: str = Field(min_length=1, max_length=300)
    herb_id: str | None = None
    amount_original: str | None = None
    amount_normalized: str | None = None
    unit: str | None = None
    dose_ratio: str | None = None
    role: str | None = None
    processing: str | None = None


class FormulaDraft(StrictModel):
    original_name: str = Field(min_length=1, max_length=300)
    evidence_id: str
    evidence_revision_no: int = Field(ge=1)
    ingredients: list[IngredientDraft] = Field(min_length=1, max_length=100)
    formula_id: str | None = None
    era: str | None = None
    school: str | None = None
    indications: str | None = None
    effects: str | None = None
    method: str | None = None
    dosage_form: str | None = None
    preparation: str | None = None
    cautions: str | None = None


class ReviewRequest(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(min_length=1, max_length=4000)


class IssueRequest(StrictModel):
    target_kind: str
    target_ref: str
    issue_type: str = Field(min_length=1, max_length=80)
    severity: Literal["BLOCKER", "WARNING", "INFO"]
    description: str = Field(min_length=1, max_length=4000)


class ResolveIssueRequest(StrictModel):
    note: str = Field(min_length=1, max_length=4000)
    waive: bool = False


class SupersedeRequest(StrictModel):
    replacement_id: str


class PublishRequest(StrictModel):
    strategy: Literal["local-fts-exact-v1", "hybrid-rrf-v1"] | None = None
    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    rerank_model: str | None = Field(default=None, min_length=1, max_length=200)
    embedding_endpoint: str | None = Field(default=None, min_length=1, max_length=500)
    rerank_endpoint: str | None = Field(default=None, min_length=1, max_length=500)


class ActivateRequest(StrictModel):
    index_build_id: str


def _read_actor(request: Request) -> Actor:
    actor = current_actor(request.cookies.get(COOKIE_NAME))
    actor.require("knowledge.read")
    return actor


def _write_actor(request: Request) -> Actor:
    actor = _read_actor(request)
    actor.require("knowledge.write")
    require_csrf(actor, request.headers.get("X-CSRF-Token"))
    return actor


def _invalid(exc: ValueError, *, conflict: bool = False) -> ApiError:
    return ApiError("KNOWLEDGE_CONFLICT" if conflict else "INVALID_KNOWLEDGE_COMMAND",
                    status=409 if conflict else 400,
                    category="conflict" if conflict else "validation", detail=str(exc))


def _opaque(kind: str, value: UUID) -> str:
    return f"{kind}-{hashlib.sha256(kind.encode() + value.bytes).hexdigest()[:32]}"


def _opaque_row(session, model, kind: str, public_id: str):
    if not public_id.startswith(f"{kind}-") or len(public_id) != len(kind) + 33:
        raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                       detail="public resource does not exist")
    for row in session.scalars(select(model)):
        if _opaque(kind, row.id) == public_id:
            return row
    raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                   detail="public resource does not exist")


def _revision(session, kind: str, ref: str, actor: Actor):
    public_id, sep, number = ref.rpartition("@")
    if not sep or not number.isdecimal() or int(number) < 1:
        raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                       detail="revision reference must be a public ID followed by @revision_no")
    if kind == "evidence_revision":
        parent_id = resolve_public_id(session, "evidence", public_id, actor)
        model, field = EvidenceRevision, EvidenceRevision.evidence_id
    elif kind == "source_revision":
        parent_id = resolve_public_id(session, "source", public_id, actor)
        model, field = SourceRevision, SourceRevision.source_id
    elif kind == "formula_revision":
        parent_id = resolve_public_id(session, "formula", public_id, actor)
        model, field = FormulaRevision, FormulaRevision.formula_id
    elif kind == "text_segment_revision":
        actor.require("knowledge.read")
        segment = session.scalar(select(TextSegment).where(TextSegment.public_id == public_id))
        if segment is None:
            raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                           detail="segment does not exist")
        model, field, parent_id = TextSegmentRevision, TextSegmentRevision.segment_id, segment.id
        source_revision = session.scalar(select(SourceRevision).where(
            SourceRevision.source_id == segment.source_id,
            SourceRevision.revision_no == int(number)))
        row = session.scalar(select(model).where(field == parent_id,
                                                  model.source_revision_id == source_revision.id)) if source_revision else None
        if row is None:
            raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                           detail="segment revision does not exist")
        return row
    else:
        raise ApiError("INVALID_TARGET", status=400, category="validation",
                       detail="unsupported revision target")
    row = session.scalar(select(model).where(field == parent_id,
                                             model.revision_no == int(number)))
    if row is None:
        raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                       detail="revision does not exist")
    return row


def _target(session, kind: str, ref: str, actor: Actor):
    if kind in {"evidence_revision", "source_revision", "formula_revision",
                "text_segment_revision"}:
        return _revision(session, kind, ref, actor)
    if kind in {"concept", "relation", "herb"}:
        return session.get(ISSUE_TARGETS[kind], resolve_public_id(session, kind, ref, actor))
    if kind == "index_build":
        return _opaque_row(session, IndexBuild, "IB", ref)
    raise ApiError("INVALID_TARGET", status=400, category="validation",
                   detail="unsupported quality or review target")


def _evidence_revision(session, public_id: str, revision_no: int, actor: Actor):
    return _revision(session, "evidence_revision", f"{public_id}@{revision_no}", actor)


def _evidence_view(session, revision: EvidenceRevision) -> dict:
    trace = trace_evidence(revision.id)
    evidence = session.get(Evidence, revision.evidence_id)
    source = session.get(SourceDocument, evidence.source_id)
    source_revision = session.get(SourceRevision, revision.source_revision_id)
    segments = [session.get(TextSegment, session.get(TextSegmentRevision, UUID(value)).segment_id)
                for value in trace["segment_revision_ids"]]
    return {
        "evidence_id": evidence.public_id, "revision_no": revision.revision_no,
        "status": revision.status, "evidence_strength": revision.evidence_strength,
        "source_id": source.public_id, "source_title": source.title,
        "source_revision_no": source_revision.revision_no,
        "quote_text": trace["quote_text"], "context_before": trace["context_before"],
        "context_after": trace["context_after"],
        "citation_locator": {"start": trace["citation_locator"]["start"],
                             "end": trace["citation_locator"]["end"]},
        "segment_ids": [row.public_id for row in segments],
    }


@router.post("/sources/import", status_code=202)
def import_source(payload: ImportRequest, request: Request,
                  actor: Annotated[Actor, Depends(_write_actor)]):
    key = required_idempotency_key(request.headers.get("Idempotency-Key"))
    if payload.metadata.source_type == "PATIENT_CASE":
        raise ApiError("SOURCE_TYPE_UNAVAILABLE", status=400, category="validation",
                       detail="patient cases are outside the V1 knowledge API")
    if len(payload.content_base64) > ((settings.max_import_bytes + 2) // 3) * 4:
        raise ApiError("FILE_TOO_LARGE", status=413, category="validation",
                       detail="source file exceeds the configured import limit")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except binascii.Error as exc:
        raise ApiError("INVALID_FILE", status=400, category="validation",
                       detail="content_base64 is invalid") from exc
    if not content or len(content) > settings.max_import_bytes:
        raise ApiError("INVALID_FILE", status=413, category="validation",
                       detail="source file is empty or too large")
    with SessionLocal() as session:
        source_id = (resolve_public_id(session, "source", payload.source_id, actor)
                     if payload.source_id else None)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=settings.data_root, suffix=f".{payload.file_format}",
                                     delete=False) as temporary:
        temporary.write(content)
        path = Path(temporary.name)
    try:
        result = import_file(path, payload.metadata, request_key=f"api:{actor.actor_id}:{key}",
                             source_id=source_id, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc, conflict="request key" in str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
    with SessionLocal() as session:
        source = session.get(SourceDocument, result.source_id)
        revision = session.get(SourceRevision, result.source_revision_id)
        job = session.get(TaskJob, result.task_job_id) if result.task_job_id else None
        body = {"source_id": source.public_id, "revision_no": revision.revision_no,
                "status": result.status, "job_id": job.public_id if job else None}
        return JSONResponse(status_code=202 if job else 201, content=body,
                            headers={"Location": f"/api/v1/jobs/{job.public_id}"} if job else {})


@router.get("/sources")
def list_sources(actor: Annotated[Actor, Depends(_read_actor)],
                 limit: int = Query(default=50, ge=1, le=100)):
    with SessionLocal() as session:
        sources = session.scalars(select(SourceDocument).order_by(
            SourceDocument.created_at.desc(), SourceDocument.id.desc()).limit(limit)).all()
        return [{"source_id": row.public_id, "title": row.title,
                 "source_type": row.source_type, "status": row.status,
                 "data_level": row.data_level} for row in sources]


@router.get("/published-sources")
def published_sources(actor: Annotated[Actor, Depends(_read_actor)]):
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime is None or runtime.active_knowledge_version_id is None:
            return []
        rows = session.scalars(select(SourceDocument).join(
            Evidence, Evidence.source_id == SourceDocument.id).join(
            EvidenceRevision, EvidenceRevision.evidence_id == Evidence.id).join(
            KnowledgeVersionItem,
            KnowledgeVersionItem.evidence_revision_id == EvidenceRevision.id).where(
                KnowledgeVersionItem.knowledge_version_id == runtime.active_knowledge_version_id,
                EvidenceRevision.status == "REVIEWED").distinct().order_by(SourceDocument.title))
        return [{"source_id": row.public_id, "title": row.title, "status": row.status,
                 "data_level": row.data_level, "outbound_authorized": row.outbound_authorized}
                for row in rows]


@router.get("/publication-config")
def publication_config(actor: Annotated[Actor, Depends(_read_actor)]):
    try:
        return {**publication_configuration(), "extractor_version": EXTRACTOR_VERSION}
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.get("/sources/{source_public_id}")
def source_detail(source_public_id: str, actor: Annotated[Actor, Depends(_read_actor)]):
    with SessionLocal() as session:
        source = session.get(SourceDocument, resolve_public_id(session, "source", source_public_id, actor))
        revisions = session.scalars(select(SourceRevision).where(
            SourceRevision.source_id == source.id).order_by(SourceRevision.revision_no)).all()
        jobs = {row.source_revision_id: row for row in session.scalars(select(ImportJob).where(
            ImportJob.source_revision_id.in_([revision.id for revision in revisions])))}
        return {"source_id": source.public_id, "title": source.title, "author": source.author,
                "era": source.era, "school": source.school, "edition": source.edition,
                "publisher": source.publisher, "publication_year": source.publication_year,
                "language": source.language, "copyright_status": source.copyright_status,
                "source_type": source.source_type, "status": source.status,
                "data_level": source.data_level, "outbound_authorized": source.outbound_authorized,
                "revisions": [{"revision_no": row.revision_no, "file_format": row.file_format,
                               "file_size_bytes": row.file_size_bytes,
                               "status": jobs[row.id].status if row.id in jobs else "UNKNOWN",
                               "error_code": jobs[row.id].error_code if row.id in jobs else None}
                              for row in revisions]}


@router.get("/sources/{source_public_id}/revisions/{revision_no}/segments")
def source_segments(source_public_id: str, revision_no: int,
                    actor: Annotated[Actor, Depends(_read_actor)],
                    limit: int = Query(default=100, ge=1, le=500),
                    after: int = Query(default=-1, ge=-1)):
    with SessionLocal() as session:
        revision = _revision(
            session, "source_revision", f"{source_public_id}@{revision_no}", actor)
        rows = session.scalars(select(TextSegmentRevision).where(
            TextSegmentRevision.source_revision_id == revision.id,
            TextSegmentRevision.sequence_no > after).order_by(
                TextSegmentRevision.sequence_no).limit(limit)).all()
        return [{"segment_id": session.get(TextSegment, row.segment_id).public_id,
                 "source_revision_no": revision_no, "sequence_no": row.sequence_no,
                 "segment_type": row.segment_type, "original_text": row.original_text,
                 "normalized_text": row.normalized_text, "context_before": row.context_before,
                 "context_after": row.context_after, "locator": row.structural_locator,
                 "parent_segment_id": (session.get(TextSegment, row.parent_segment_id).public_id
                                       if row.parent_segment_id else None),
                 "page_no": row.page_no, "chapter_no": row.chapter_no,
                 "paragraph_no": row.paragraph_no}
                for row in rows]


def _candidate_view(session, batch: KnowledgeExtraction) -> dict:
    """Project a frozen extraction manifest; all external references are public IDs."""
    manifest = batch.manifest
    source_revision = session.get(SourceRevision, batch.source_revision_id)
    source = session.get(SourceDocument, source_revision.source_id)
    evidence_ids = dict.fromkeys(row["evidence_revision_id"] for row in (
        *manifest["segments"], *manifest.get("formulas", [])) if row["evidence_revision_id"])
    evidence = [_evidence_view(session, session.get(EvidenceRevision, UUID(value)))
                for value in evidence_ids]
    segments = []
    concept_ids, relation_ids = {}, {}
    for item in manifest["segments"]:
        segment_ref = _public_ref(session, "text_segment_revision", UUID(item["segment_revision_id"]))
        segments.append({
            "segment_ref": segment_ref, "text_checksum": item["text_checksum"],
            "structural_locator": item["structural_locator"],
            "evidence_ref": (_public_ref(session, "evidence_revision", UUID(item["evidence_revision_id"]))
                             if item["evidence_revision_id"] else None),
            "mentions": [{"mention_id": _opaque("EM", UUID(mention["mention_id"])),
                          "concept_id": session.get(Concept, UUID(mention["concept_id"])).public_id,
                          **{key: mention[key] for key in (
                              "surface_text", "entity_type", "start_offset", "end_offset", "ambiguous")}}
                         for mention in item["mentions"]],
            "relations": [{"relation_id": session.get(
                KnowledgeRelation, UUID(relation["relation_id"])).public_id,
                **{key: relation[key] for key in (
                    "subject_start", "object_start", "start_offset", "end_offset",
                    "assertion_text", "relation_type")}} for relation in item["relations"]],
        })
        concept_ids.update(dict.fromkeys(mention["concept_id"] for mention in item["mentions"]))
        relation_ids.update(dict.fromkeys(relation["relation_id"] for relation in item["relations"]))
    concepts, relations, formulas = [], [], []
    for value in concept_ids:
        row = session.get(Concept, UUID(value))
        refs = session.scalars(select(ConceptEvidence.evidence_revision_id).where(
            ConceptEvidence.concept_id == row.id))
        concepts.append({"concept_id": row.public_id, "canonical_name": row.canonical_name,
                         "concept_type": row.concept_type, "status": row.status,
                         "evidence_refs": [_public_ref(session, "evidence_revision", ref) for ref in refs]})
    for value in relation_ids:
        row = session.get(KnowledgeRelation, UUID(value))
        refs = session.scalars(select(RelationEvidence.evidence_revision_id).where(
            RelationEvidence.relation_id == row.id))
        relations.append({"relation_id": row.public_id, "status": row.status,
                          "subject_id": session.get(Concept, row.subject_concept_id).public_id,
                          "object_id": session.get(Concept, row.object_concept_id).public_id,
                          "relation_type": row.relation_type, "assertion_text": row.assertion_text,
                          "evidence_refs": [_public_ref(session, "evidence_revision", ref) for ref in refs]})
    for item in manifest.get("formulas", []):
        row = session.get(FormulaRevision, UUID(item["formula_revision_id"]))
        formulas.append({"formula_id": session.get(Formula, row.formula_id).public_id,
                         "revision_no": row.revision_no, "original_name": row.original_name,
                         "status": row.status, "method": item["method"],
                         "ingredients": [{key: value for key, value in ingredient.items()
                                          if key != "herb_id"} for ingredient in item["ingredients"]],
                         "evidence_refs": [_public_ref(session, "evidence_revision",
                                                       UUID(item["evidence_revision_id"]))],
                         "field_sources": [{"segment_ref": _public_ref(
                             session, "text_segment_revision", UUID(span["segment_revision_id"])),
                             **{key: span[key] for key in (
                                 "field_key", "start_offset", "end_offset", "basis")}}
                             for span in item["field_sources"]]})
    return {"extraction_id": _opaque("EX", batch.id), "source_id": source.public_id,
            "revision_no": source_revision.revision_no, "extractor_version": batch.extractor_version,
            "status": manifest["status"],
            **{key: manifest[key] for key in (
                "segment_count", "mention_count", "relation_count", "concept_count", "formula_count")},
            "segments": segments, "evidence": evidence,
            "concepts": concepts, "relations": relations, "formulas": formulas}


@router.post("/sources/{source_public_id}/revisions/{revision_no}/extract")
def extract_candidates(source_public_id: str, revision_no: int,
                       actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        revision_id = _revision(session, "source_revision",
                                f"{source_public_id}@{revision_no}", actor).id
    try:
        result = extract_source_candidates(revision_id, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc, conflict=True) from exc
    with SessionLocal() as session:
        return _candidate_view(session, session.get(KnowledgeExtraction, UUID(result["extraction_id"])))


@router.get("/sources/{source_public_id}/revisions/{revision_no}/candidates")
def source_candidates(source_public_id: str, revision_no: int,
                      actor: Annotated[Actor, Depends(_read_actor)]):
    with SessionLocal() as session:
        revision = _revision(session, "source_revision", f"{source_public_id}@{revision_no}", actor)
        batch = session.scalar(select(KnowledgeExtraction).where(
            KnowledgeExtraction.source_revision_id == revision.id,
            KnowledgeExtraction.extractor_version == EXTRACTOR_VERSION))
        if batch is None:
            raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                           detail="source revision has no current extraction batch")
        return _candidate_view(session, batch)


@router.post("/drafts/evidence", status_code=201)
def draft_evidence(payload: EvidenceDraft, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        segments = [_revision(session, "text_segment_revision", value, actor).id
                    for value in payload.segment_ids]
        evidence_id = (resolve_public_id(session, "evidence", payload.evidence_id, actor)
                       if payload.evidence_id else None)
    try:
        revision_id = create_evidence(segments, strength=payload.strength,
                                      evidence_id=evidence_id, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    with SessionLocal() as session:
        return _evidence_view(session, session.get(EvidenceRevision, revision_id))


@router.get("/evidence")
def list_evidence(actor: Annotated[Actor, Depends(_read_actor)],
                  source_id: str | None = None, version_id: str | None = None,
                  limit: int = Query(default=50, ge=1, le=100)):
    with SessionLocal() as session:
        query = select(EvidenceRevision).join(Evidence).order_by(
            EvidenceRevision.created_at.desc(), EvidenceRevision.id.desc())
        if source_id:
            query = query.where(Evidence.source_id == resolve_public_id(session, "source", source_id, actor))
        if version_id:
            version = resolve_public_id(session, "knowledge_version", version_id, actor)
            query = query.join(KnowledgeVersionItem,
                               KnowledgeVersionItem.evidence_revision_id == EvidenceRevision.id).where(
                                   KnowledgeVersionItem.knowledge_version_id == version)
        return [_evidence_view(session, row) for row in session.scalars(query.limit(limit))]


@router.post("/evidence/batch")
def evidence_batch(refs: list[str], request: Request,
                   actor: Annotated[Actor, Depends(_read_actor)]):
    require_csrf(actor, request.headers.get("X-CSRF-Token"))
    if not refs or len(refs) > 100:
        raise ApiError("INVALID_REQUEST", status=400, category="validation",
                       detail="batch requires 1-100 evidence revision references")
    with SessionLocal() as session:
        return [_evidence_view(session, _revision(session, "evidence_revision", ref, actor))
                for ref in refs]


@router.get("/evidence/{evidence_public_id}")
def evidence_detail(evidence_public_id: str,
                    actor: Annotated[Actor, Depends(_read_actor)],
                    revision_no: int | None = Query(default=None, ge=1)):
    with SessionLocal() as session:
        evidence_id = resolve_public_id(session, "evidence", evidence_public_id, actor)
        query = select(EvidenceRevision).where(EvidenceRevision.evidence_id == evidence_id)
        if revision_no is not None:
            query = query.where(EvidenceRevision.revision_no == revision_no)
        row = session.scalar(query.order_by(EvidenceRevision.revision_no.desc()).limit(1))
        if row is None:
            raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                           detail="evidence revision does not exist")
        return _evidence_view(session, row)


@router.post("/drafts/concepts", status_code=201)
def draft_concept(payload: ConceptDraft, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        revision = _evidence_revision(session, payload.evidence_id, payload.evidence_revision_no, actor)
    try:
        object_id = create_concept(payload.canonical_name, concept_type=payload.concept_type,
                                   evidence_revision_id=revision.id, terms=tuple(payload.terms),
                                   era=payload.era, school=payload.school, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    with SessionLocal() as session:
        return {"concept_id": session.get(Concept, object_id).public_id, "status": "DRAFT"}


@router.post("/drafts/relations", status_code=201)
def draft_relation(payload: RelationDraft, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        subject_id = resolve_public_id(session, "concept", payload.subject_id, actor)
        object_id = resolve_public_id(session, "concept", payload.object_id, actor)
        revision = _evidence_revision(session, payload.evidence_id, payload.evidence_revision_no, actor)
    try:
        relation_id = create_relation(subject_id, object_id, relation_type=payload.relation_type,
                                      assertion_text=payload.assertion_text,
                                      evidence_revision_id=revision.id, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    with SessionLocal() as session:
        return {"relation_id": session.get(KnowledgeRelation, relation_id).public_id,
                "status": "DRAFT"}


@router.post("/drafts/herbs", status_code=201)
def draft_herb(payload: HerbDraft, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        revision = _evidence_revision(session, payload.evidence_id, payload.evidence_revision_no, actor)
    try:
        herb_id = create_herb(payload.canonical_name, evidence_revision_id=revision.id,
                              terms=tuple(payload.terms), era=payload.era, school=payload.school,
                              actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    with SessionLocal() as session:
        return {"herb_id": session.get(Herb, herb_id).public_id, "status": "DRAFT"}


@router.post("/drafts/formulas", status_code=201)
def draft_formula(payload: FormulaDraft, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        revision = _evidence_revision(session, payload.evidence_id, payload.evidence_revision_no, actor)
        formula_id = (resolve_public_id(session, "formula", payload.formula_id, actor)
                      if payload.formula_id else None)
        ingredients = tuple(IngredientSpec(
            original_name=row.original_name,
            herb_id=resolve_public_id(session, "herb", row.herb_id, actor) if row.herb_id else None,
            amount_original=row.amount_original, amount_normalized=row.amount_normalized,
            unit=row.unit, dose_ratio=row.dose_ratio, role=row.role,
            processing=row.processing) for row in payload.ingredients)
    try:
        revision_id = create_formula(payload.original_name, evidence_revision_id=revision.id,
                                     ingredients=ingredients, formula_id=formula_id,
                                     era=payload.era, school=payload.school,
                                     indications=payload.indications, effects=payload.effects,
                                     method=payload.method, dosage_form=payload.dosage_form,
                                     preparation=payload.preparation, cautions=payload.cautions,
                                     actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    with SessionLocal() as session:
        row = session.get(FormulaRevision, revision_id)
        return {"formula_id": session.get(Formula, row.formula_id).public_id,
                "revision_no": row.revision_no, "status": row.status}


@router.get("/drafts/{kind}")
def list_drafts(kind: Literal["concept", "relation", "herb", "formula_revision"],
                actor: Annotated[Actor, Depends(_read_actor)],
                limit: int = Query(default=50, ge=1, le=100)):
    models = {"concept": Concept, "relation": KnowledgeRelation,
              "herb": Herb, "formula_revision": FormulaRevision}
    with SessionLocal() as session:
        rows = session.scalars(select(models[kind]).order_by(models[kind].created_at.desc()).limit(limit))
        return [{"ref": (f"{session.get(Formula, row.formula_id).public_id}@{row.revision_no}"
                         if kind == "formula_revision" else row.public_id),
                 "status": row.status} for row in rows]


@router.get("/drafts/{kind}/{target_ref}")
def draft_detail(kind: Literal["concept", "relation", "herb", "formula_revision"],
                 target_ref: str, actor: Annotated[Actor, Depends(_read_actor)]):
    links = {
        "concept": (ConceptEvidence, ConceptEvidence.concept_id),
        "relation": (RelationEvidence, RelationEvidence.relation_id),
        "herb": (HerbEvidence, HerbEvidence.herb_id),
        "formula_revision": (FormulaEvidence, FormulaEvidence.formula_revision_id),
    }
    with SessionLocal() as session:
        row = _target(session, kind, target_ref, actor)
        link_model, field = links[kind]
        evidence_ids = session.scalars(select(link_model.evidence_revision_id).where(
            field == row.id)).all()
        detail = {"ref": target_ref, "kind": kind, "status": row.status,
                  "evidence": [_evidence_view(session, session.get(EvidenceRevision, value))
                               for value in evidence_ids]}
        if kind == "concept":
            detail.update(canonical_name=row.canonical_name, concept_type=row.concept_type,
                          era=row.era, school=row.school,
                          terms=list(session.scalars(select(ConceptTerm.term).where(
                              ConceptTerm.concept_id == row.id))))
        elif kind == "relation":
            detail.update(subject_id=session.get(Concept, row.subject_concept_id).public_id,
                          object_id=session.get(Concept, row.object_concept_id).public_id,
                          relation_type=row.relation_type, assertion_text=row.assertion_text)
        elif kind == "herb":
            detail.update(canonical_name=row.canonical_name, era=row.era, school=row.school,
                          terms=list(session.scalars(select(HerbTerm.term).where(
                              HerbTerm.herb_id == row.id))))
        else:
            detail.update(original_name=row.original_name, era=row.era, school=row.school,
                          indications=row.indications, effects=row.effects, method=row.method,
                          dosage_form=row.dosage_form, preparation=row.preparation,
                          cautions=row.cautions,
                          ingredients=[{
                              "original_name": ingredient.original_name,
                              "herb_id": (session.get(Herb, ingredient.herb_id).public_id
                                          if ingredient.herb_id else None),
                              "amount_original": ingredient.amount_original,
                              "amount_normalized": ingredient.amount_normalized,
                              "unit": ingredient.unit, "dose_ratio": ingredient.dose_ratio,
                              "role": ingredient.role, "processing": ingredient.processing,
                          } for ingredient in session.scalars(select(FormulaIngredient).where(
                              FormulaIngredient.formula_revision_id == row.id).order_by(
                                  FormulaIngredient.sequence_no))])
        return detail


@router.post("/reviews/{kind}/{target_ref}", status_code=201)
def review(kind: Literal["evidence_revision", "concept", "relation", "herb", "formula_revision"],
           target_ref: str, payload: ReviewRequest,
           actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        target = _target(session, kind, target_ref, actor)
    try:
        review_object(kind, target.id, reviewer_id=actor.actor_id,
                      decision=payload.decision, note=payload.note)
    except ValueError as exc:
        raise _invalid(exc, conflict=True) from exc
    return {"target_ref": target_ref, "status": "REVIEWED" if payload.decision == "APPROVE" else "REJECTED"}


@router.post("/supersessions/{kind}/{old_ref}", status_code=201)
def supersede(kind: Literal["concept", "relation", "herb"], old_ref: str,
              payload: SupersedeRequest, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        old_id = resolve_public_id(session, kind, old_ref, actor)
        new_id = resolve_public_id(session, kind, payload.replacement_id, actor)
    try:
        revision_no = supersede_reviewed_object(kind, old_id, new_id, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc, conflict=True) from exc
    return {"old_ref": old_ref, "replacement_id": payload.replacement_id,
            "revision_no": revision_no}


@router.post("/quality-issues", status_code=201)
def create_issue(payload: IssueRequest, actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        target = _target(session, payload.target_kind, payload.target_ref, actor)
    try:
        issue_id = open_quality_issue(payload.target_kind, target.id,
                                      issue_type=payload.issue_type, severity=payload.severity,
                                      description=payload.description, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc) from exc
    return {"issue_id": _opaque("QI", issue_id), "status": "OPEN"}


@router.get("/quality-issues")
def list_issues(actor: Annotated[Actor, Depends(_read_actor)],
                status: Literal["OPEN", "RESOLVED", "WAIVED"] | None = None,
                limit: int = Query(default=100, ge=1, le=500)):
    with SessionLocal() as session:
        query = select(QualityIssue).order_by(QualityIssue.created_at.desc())
        if status:
            query = query.where(QualityIssue.status == status)
        return [{"issue_id": _opaque("QI", row.id), "issue_type": row.issue_type,
                 "severity": row.severity, "target_kind": row.target_kind,
                 "target_ref": _public_ref(session, row.target_kind, row.target_id),
                 "description": row.description, "status": row.status,
                 "resolution_note": row.resolution_note} for row in session.scalars(query.limit(limit))]


@router.get("/quality-report")
def quality_report(actor: Annotated[Actor, Depends(_read_actor)]):
    with SessionLocal() as session:
        counts = {"BLOCKER": 0, "WARNING": 0, "INFO": 0}
        for severity, count in session.execute(select(
            QualityIssue.severity, func.count(QualityIssue.id)).where(
                QualityIssue.status == "OPEN").group_by(QualityIssue.severity)):
            counts[severity] = count
        runtime = session.get(KnowledgeRuntimeState, 1)
        version = (session.get(KnowledgeVersion, runtime.active_knowledge_version_id)
                   if runtime and runtime.active_knowledge_version_id else None)
        return {"open_issues": counts, "publication_blocked": counts["BLOCKER"] > 0,
                "active_version_id": version.public_id if version else None}


@router.post("/quality-issues/{issue_public_id}/resolve")
def resolve_issue(issue_public_id: str, payload: ResolveIssueRequest,
                  actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        issue = _opaque_row(session, QualityIssue, "QI", issue_public_id)
        issue_id = issue.id
    try:
        resolve_quality_issue(issue_id, reviewer_id=actor.actor_id,
                              note=payload.note, waive=payload.waive)
    except ValueError as exc:
        raise _invalid(exc, conflict=True) from exc
    return {"issue_id": issue_public_id, "status": "WAIVED" if payload.waive else "RESOLVED"}


def _public_ref(session, kind: str, object_id: UUID) -> str:
    if kind in {"evidence_revision", "source_revision", "formula_revision"}:
        model = ISSUE_TARGETS[kind]
        row = session.get(model, object_id)
        identity_kind = {"evidence_revision": (Evidence, "evidence_id"),
                         "source_revision": (SourceDocument, "source_id"),
                         "formula_revision": (Formula, "formula_id")}[kind]
        return f"{session.get(identity_kind[0], getattr(row, identity_kind[1])).public_id}@{row.revision_no}"
    if kind == "text_segment_revision":
        row = session.get(TextSegmentRevision, object_id)
        source_revision = session.get(SourceRevision, row.source_revision_id)
        return f"{session.get(TextSegment, row.segment_id).public_id}@{source_revision.revision_no}"
    if kind == "index_build":
        return _opaque("IB", object_id)
    return session.get(ISSUE_TARGETS[kind], object_id).public_id


@router.post("/versions", status_code=201)
def snapshot_version(actor: Annotated[Actor, Depends(_write_actor)]):
    try:
        version_id = create_knowledge_version(actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc, conflict=True) from exc
    with SessionLocal() as session:
        row = session.get(KnowledgeVersion, version_id)
        return {"version_id": row.public_id, "version_no": row.version_no,
                "status": row.status, "manifest_hash": row.manifest_hash}


@router.get("/versions")
def list_versions(actor: Annotated[Actor, Depends(_read_actor)],
                  limit: int = Query(default=50, ge=1, le=100)):
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        rows = session.scalars(select(KnowledgeVersion).order_by(
            KnowledgeVersion.version_no.desc()).limit(limit))
        return [{"version_id": row.public_id, "version_no": row.version_no,
                 "status": row.status, "active": runtime is not None and
                 runtime.active_knowledge_version_id == row.id,
                 "manifest_hash": row.manifest_hash} for row in rows]


@router.get("/versions/{version_public_id}")
def version_detail(version_public_id: str, actor: Annotated[Actor, Depends(_read_actor)]):
    with SessionLocal() as session:
        version_id = resolve_public_id(session, "knowledge_version", version_public_id, actor)
        version = session.get(KnowledgeVersion, version_id)
        builds = session.scalars(select(IndexBuild).where(IndexBuild.knowledge_version_id == version_id)
                                 .order_by(IndexBuild.created_at.desc())).all()
        runtime = session.get(KnowledgeRuntimeState, 1)
        counts = {kind: 0 for kind in REVIEW_TARGETS}
        for row in session.scalars(select(KnowledgeVersionItem).where(
            KnowledgeVersionItem.knowledge_version_id == version_id)):
            for kind, (_, field) in REVIEW_TARGETS.items():
                counts[kind] += getattr(row, field) is not None
        return {"version_id": version.public_id, "version_no": version.version_no,
                "status": version.status, "manifest_hash": version.manifest_hash,
                "reference_manifest_hash": version.reference_manifest_hash,
                "active": runtime is not None and runtime.active_knowledge_version_id == version_id,
                "item_counts": counts,
                "index_builds": [{"index_build_id": _opaque("IB", row.id),
                                  "status": row.status, "fts_status": row.fts_status,
                                  "vector_status": row.vector_status}
                                 for row in builds]}


@router.post("/versions/{version_public_id}/publish")
def publish_version(version_public_id: str, payload: PublishRequest, request: Request,
                    actor: Annotated[Actor, Depends(_write_actor)]):
    key = required_idempotency_key(request.headers.get("Idempotency-Key"))
    configuration = payload.model_dump()
    if all(value is None for value in configuration.values()):
        try:
            configuration = publication_configuration()["configuration"]
        except ValueError as exc:
            raise _invalid(exc) from exc
    else:
        configuration["strategy"] = configuration["strategy"] or "hybrid-rrf-v1"
    if is_local_configuration(configuration):
        try:
            validate_local_configuration(configuration)
        except ValueError as exc:
            raise _invalid(exc) from exc
    elif any(configuration[key] is None for key in (
        "embedding_model", "rerank_model", "embedding_endpoint", "rerank_endpoint",
    )):
        raise ApiError("INVALID_KNOWLEDGE_COMMAND", status=400, category="validation",
                       detail="hybrid publication requires all configured model routes")
    with SessionLocal.begin() as session:
        version_id = resolve_public_id(session, "knowledge_version", version_public_id, actor)
        version = session.scalar(select(KnowledgeVersion).where(
            KnowledgeVersion.id == version_id).with_for_update())
        jobs = [row for row in session.scalars(select(TaskJob).where(
            TaskJob.job_type == "knowledge.publish").order_by(
                TaskJob.created_at.desc(), TaskJob.id.desc()))
                if row.payload.get("version_id") == str(version_id)]
        if any(row.payload.get("configuration") != configuration for row in jobs):
            raise ApiError("KNOWLEDGE_CONFLICT", status=409, category="conflict",
                           detail="knowledge version already has a different index configuration")
        running = next((row for row in jobs if row.status != "FAILED"), None)
        if running is not None:
            return accepted_job_response(running)
        if version.status not in {"PRE_PUBLISH_SNAPSHOT", "INDEXING", "VALIDATING"}:
            raise ApiError("KNOWLEDGE_CONFLICT", status=409, category="conflict",
                           detail="knowledge version is not eligible for publication")
        job = enqueue_actor_job(session, actor=actor, capability="knowledge.write",
                                idempotency_key=key, job_type="knowledge.publish",
                                payload={"version_id": str(version_id),
                                         "configuration": configuration},
                                resource_class=ResourceClass.EMBEDDING)
        return accepted_job_response(job)


@router.post("/versions/{version_public_id}/activate")
def activate_version(version_public_id: str, payload: ActivateRequest,
                     actor: Annotated[Actor, Depends(_write_actor)]):
    with SessionLocal() as session:
        version_id = resolve_public_id(session, "knowledge_version", version_public_id, actor)
        build = _opaque_row(session, IndexBuild, "IB", payload.index_build_id)
        build_id = build.id
    try:
        snapshot_id = activate_knowledge_version(version_id, build_id, actor_id=actor.actor_id)
    except ValueError as exc:
        raise _invalid(exc, conflict=True) from exc
    return {"version_id": version_public_id, "active": True,
            "release_snapshot_id": _opaque("RS", snapshot_id) if snapshot_id else None}


@router.get("/versions/{left_public_id}/compare/{right_public_id}")
def compare_versions(left_public_id: str, right_public_id: str,
                     actor: Annotated[Actor, Depends(_read_actor)]):
    with SessionLocal() as session:
        left_id = resolve_public_id(session, "knowledge_version", left_public_id, actor)
        right_id = resolve_public_id(session, "knowledge_version", right_public_id, actor)
    difference = compare_knowledge_versions(left_id, right_id)
    with SessionLocal() as session:
        def convert(value):
            if isinstance(value, str):
                try:
                    object_id = UUID(value)
                except ValueError:
                    return value
                for kind, (model, _) in REVIEW_TARGETS.items():
                    if session.get(model, object_id) is not None:
                        return _public_ref(session, kind, object_id)
                for model in (Evidence, Formula, Concept, Herb, KnowledgeRelation):
                    row = session.get(model, object_id)
                    if row is not None:
                        return row.public_id
                return _opaque("REF", object_id)
            if isinstance(value, list):
                return [convert(row) for row in value]
            if isinstance(value, dict):
                return {key: convert(row) for key, row in value.items()}
            return value
        return convert(difference)
