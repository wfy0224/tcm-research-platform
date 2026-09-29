"""Public research controls, persisted detail views and task event stream."""

import asyncio
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from tcm_platform.api_contract import (
    Actor,
    ApiError,
    accepted_job_response,
    required_idempotency_key,
    resolve_public_id,
)
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.local_auth import COOKIE_NAME, current_actor, require_csrf
from tcm_platform.models import (
    Artifact,
    EventLog,
    Evidence,
    EvidenceRevision,
    HumanReviewRequest,
    ReportExport,
    ResearchTask,
    SourceDocument,
    StructuredReport,
    TaskJob,
)
from tcm_platform.report_export import queue_report_export
from tcm_platform.research_service import (
    cancel_research_task,
    create_research_task,
    request_research_pause,
    resume_research_task,
    start_research_task,
)
from tcm_platform.research_views import public_ref, task_details
from tcm_platform.stop_service import resolve_human_review
from tcm_platform.storage import ContentAddressedStore

router = APIRouter(prefix="/api/v1/research", tags=["research"])


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CreateTaskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2_000)
    source_ids: list[str] = Field(default_factory=list, max_length=100)


class StartTaskRequest(StrictModel):
    model_version: str = Field(min_length=3, max_length=200)
    allow_question_outbound: bool = False


class ResolveReviewRequest(StrictModel):
    note: str = Field(min_length=1, max_length=2_000)


class TaskResponse(StrictModel):
    task_id: str
    question: str
    status: str
    control_state: str
    source_ids: list[str]
    allowed_actions: list[str]
    job_id: str | None
    report_available: bool


class ExportResponse(StrictModel):
    file_format: str
    status: str
    job_id: str
    download_url: str | None


class ReportResponse(StrictModel):
    task_id: str
    schema_version: str
    content_hash: str
    question: str
    counts: dict[str, int]
    sections: dict[str, list[dict]]
    open_disputes: list[dict]
    unresolved_gaps: list[dict]
    excluded_claim_count: int


def _read_actor(request: Request) -> Actor:
    actor = current_actor(request.cookies.get(COOKIE_NAME))
    actor.require("research.read")
    return actor


def _write_actor(request: Request) -> Actor:
    actor = current_actor(request.cookies.get(COOKIE_NAME))
    actor.require("research.write")
    require_csrf(actor, request.headers.get("X-CSRF-Token"))
    return actor


def _task_response(session, task: ResearchTask) -> TaskResponse:
    source_ids = [UUID(value) for value in task.draft_scope.get("source_ids", [])]
    sources = {source.id: source.public_id for source in session.scalars(
        select(SourceDocument).where(SourceDocument.id.in_(source_ids)))}
    job = session.scalar(select(TaskJob).where(
        TaskJob.idempotency_key == f"research:{task.id}:run:v1"))
    report_available = session.scalar(select(StructuredReport.id).where(
        StructuredReport.task_id == task.id)) is not None
    actions = []
    if task.status == "CREATED":
        actions.extend(("start", "cancel"))
    elif task.status == "WAITING_HUMAN":
        if session.scalar(select(HumanReviewRequest.id).where(
            HumanReviewRequest.task_id == task.id,
            HumanReviewRequest.status == "PENDING")) is not None:
            actions.append("resolve_review")
    elif task.status not in {"COMPLETED", "CANCELLED"} and job is not None:
        if task.control_state == "ACTIVE" and job.status in {
            "RUNNING", "PENDING", "RETRY_WAIT",
        }:
            actions.extend(("pause", "cancel"))
        elif task.control_state in {"PAUSED", "PAUSE_REQUESTED"}:
            actions.extend(("resume", "cancel"))
        elif task.control_state == "CANCEL_REQUESTED":
            actions.append("cancel")
    if task.status == "COMPLETED" and report_available:
        actions.append("export")
    return TaskResponse(
        task_id=task.public_id, question=task.question, status=task.status,
        control_state=task.control_state,
        source_ids=[sources[value] for value in source_ids if value in sources],
        allowed_actions=actions, job_id=job.public_id if job else None,
        report_available=report_available,
    )


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(payload: CreateTaskRequest, request: Request,
                actor: Annotated[Actor, Depends(_write_actor)]) -> JSONResponse:
    key = required_idempotency_key(request.headers.get("Idempotency-Key"))
    with SessionLocal() as session:
        source_ids = [resolve_public_id(session, "source", value, actor)
                      for value in payload.source_ids]
    try:
        task_id = create_research_task(payload.question, source_ids=source_ids,
                                       actor_id=actor.actor_id, idempotency_key=key)
    except ValueError as exc:
        code = "IDEMPOTENCY_CONFLICT" if "idempotency" in str(exc) else "INVALID_REQUEST"
        raise ApiError(code, status=409 if code == "IDEMPOTENCY_CONFLICT" else 400,
                       category="conflict" if code == "IDEMPOTENCY_CONFLICT" else "validation",
                       detail=str(exc)) from exc
    with SessionLocal() as session:
        task = session.get(ResearchTask, task_id)
        body = _task_response(session, task)
    return JSONResponse(status_code=201, content=body.model_dump(mode="json"),
                        headers={"Location": f"/api/v1/research/tasks/{body.task_id}"})


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(actor: Annotated[Actor, Depends(_read_actor)],
               limit: int = 50) -> list[TaskResponse]:
    if not 1 <= limit <= 100:
        raise ApiError("INVALID_REQUEST", status=400, category="validation",
                       detail="limit must be between 1 and 100")
    with SessionLocal() as session:
        tasks = session.scalars(select(ResearchTask).order_by(
            ResearchTask.created_at.desc(), ResearchTask.id.desc()).limit(limit)).all()
        return [_task_response(session, task) for task in tasks]


@router.get("/tasks/{task_public_id}", response_model=TaskResponse)
def get_task(task_public_id: str,
             actor: Annotated[Actor, Depends(_read_actor)]) -> TaskResponse:
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        return _task_response(session, session.get(ResearchTask, task_id))


@router.post("/tasks/{task_public_id}/start")
def start_task(task_public_id: str, payload: StartTaskRequest, request: Request,
               actor: Annotated[Actor, Depends(_write_actor)]) -> JSONResponse:
    required_idempotency_key(request.headers.get("Idempotency-Key"))
    provider, separator, model = payload.model_version.partition("/")
    if not separator or not model or provider not in {"siliconflow", "deepseek"}:
        raise ApiError("INVALID_MODEL_ROUTE", status=400, category="validation",
                       detail="model_version must use a supported provider/model route")
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
    try:
        start_research_task(task_id, model_version=payload.model_version,
                            actor_id=actor.actor_id,
                            question_outbound_authorized=payload.allow_question_outbound,
                            idempotent=True)
    except ValueError as exc:
        raise ApiError("RESEARCH_START_CONFLICT", status=409, category="conflict",
                       detail=str(exc)) from exc
    with SessionLocal() as session:
        job = session.scalar(select(TaskJob).where(
            TaskJob.idempotency_key == f"research:{task_id}:run:v1"))
        return accepted_job_response(job)


def _control(task_public_id: str, request: Request, actor: Actor,
             action: Literal["pause", "resume", "cancel"]) -> TaskResponse:
    key = required_idempotency_key(request.headers.get("Idempotency-Key"))
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
    command = {"pause": request_research_pause, "resume": resume_research_task,
               "cancel": cancel_research_task}[action]
    try:
        if action == "cancel":
            command(task_id, actor_id=actor.actor_id)
        else:
            command(task_id, actor_id=actor.actor_id, idempotency_key=key)
    except ValueError as exc:
        raise ApiError("RESEARCH_CONTROL_CONFLICT", status=409, category="conflict",
                       detail=str(exc)) from exc
    with SessionLocal() as session:
        return _task_response(session, session.get(ResearchTask, task_id))


@router.post("/tasks/{task_public_id}/pause", response_model=TaskResponse)
def pause_task(task_public_id: str, request: Request,
               actor: Annotated[Actor, Depends(_write_actor)]) -> TaskResponse:
    return _control(task_public_id, request, actor, "pause")


@router.post("/tasks/{task_public_id}/resume", response_model=TaskResponse)
def resume_task(task_public_id: str, request: Request,
                actor: Annotated[Actor, Depends(_write_actor)]) -> TaskResponse:
    return _control(task_public_id, request, actor, "resume")


@router.post("/tasks/{task_public_id}/cancel", response_model=TaskResponse)
def cancel_task(task_public_id: str, request: Request,
                actor: Annotated[Actor, Depends(_write_actor)]) -> TaskResponse:
    return _control(task_public_id, request, actor, "cancel")


def _details(task_public_id: str, actor: Actor) -> dict:
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        return {"task_id": task_public_id, **task_details(session, task_id)}


@router.get("/tasks/{task_public_id}/details")
def get_details(task_public_id: str,
                actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    return _details(task_public_id, actor)


@router.get("/tasks/{task_public_id}/claims")
def get_claims(task_public_id: str,
               actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    detail = _details(task_public_id, actor)
    return {"task_id": task_public_id, "claims": detail["claims"]}


@router.get("/tasks/{task_public_id}/audits")
def get_audits(task_public_id: str,
               actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    detail = _details(task_public_id, actor)
    return {"task_id": task_public_id, "audits": detail["audits"]}


@router.get("/tasks/{task_public_id}/debate")
def get_debate(task_public_id: str,
               actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    detail = _details(task_public_id, actor)
    return {"task_id": task_public_id, "debate": detail["debate"]}


@router.get("/tasks/{task_public_id}/disputes")
def get_disputes(task_public_id: str,
                 actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    detail = _details(task_public_id, actor)
    return {"task_id": task_public_id, "disputes": detail["disputes"],
            "evidence_gaps": detail["evidence_gaps"]}


@router.get("/tasks/{task_public_id}/human-reviews")
def get_human_reviews(task_public_id: str,
                      actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    detail = _details(task_public_id, actor)
    return {"task_id": task_public_id, "human_reviews": detail["human_reviews"]}


@router.post("/tasks/{task_public_id}/human-reviews/{review_ref}/resolve",
             response_model=TaskResponse)
def resolve_review(task_public_id: str, review_ref: str, payload: ResolveReviewRequest,
                   request: Request,
                   actor: Annotated[Actor, Depends(_write_actor)]) -> TaskResponse:
    required_idempotency_key(request.headers.get("Idempotency-Key"))
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        reviews = session.scalars(select(HumanReviewRequest).where(
            HumanReviewRequest.task_id == task_id)).all()
        review = next((row for row in reviews if public_ref("HREV", row.id) == review_ref),
                      None)
        if review is None:
            raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                           detail="human review does not exist")
        if review.status == "RESOLVED" and review.resolved_by == actor.actor_id \
                and review.resolution_note == payload.note.strip():
            return _task_response(session, session.get(ResearchTask, task_id))
        review_id = review.id
    try:
        resolve_human_review(review_id, reviewer_id=actor.actor_id, note=payload.note,
                             idempotent=True)
    except ValueError as exc:
        raise ApiError("HUMAN_REVIEW_CONFLICT", status=409, category="conflict",
                       detail=str(exc)) from exc
    with SessionLocal() as session:
        return _task_response(session, session.get(ResearchTask, task_id))


@router.get("/tasks/{task_public_id}/events")
async def stream_task_events(task_public_id: str, request: Request,
                             actor: Annotated[Actor, Depends(_read_actor)],
                             follow: bool = True) -> StreamingResponse:
    raw_cursor = request.headers.get("Last-Event-ID", "0")
    if (not raw_cursor.isascii() or not raw_cursor.isdecimal()
            or len(raw_cursor) > 10 or int(raw_cursor) > 2_147_483_647):
        raise ApiError("INVALID_EVENT_CURSOR", status=400, category="validation",
                       detail="Last-Event-ID must be a nonnegative decimal sequence")
    cursor = int(raw_cursor)
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        latest = session.scalar(select(EventLog.sequence_no).order_by(
            EventLog.sequence_no.desc()).limit(1)) or 0
    if cursor > latest:
        raise ApiError("INVALID_EVENT_CURSOR", status=400, category="validation",
                       detail="Last-Event-ID is ahead of the event log")

    async def events():
        nonlocal cursor
        snapshot = {"task_id": task_public_id,
                    "url": f"/api/v1/research/tasks/{task_public_id}"}
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
        while True:
            if await request.is_disconnected():
                return
            try:
                current_actor(request.cookies.get(COOKIE_NAME)).require("research.read")
            except ApiError:
                return
            with SessionLocal() as session:
                rows = session.scalars(select(EventLog).where(
                    EventLog.aggregate_id == str(task_id),
                    EventLog.event_type.like("research_task.%"),
                    EventLog.sequence_no > cursor).order_by(
                    EventLog.sequence_no).limit(100)).all()
                batch = [(row.sequence_no, row.event_type) for row in rows]
            for sequence_no, event_type in batch:
                cursor = sequence_no
                data = json.dumps({"task_id": task_public_id})
                yield f"id: {cursor}\nevent: {event_type}\ndata: {data}\n\n"
            if len(batch) == 100:
                continue
            if not follow:
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


def _public_evidence(session, row: dict) -> dict:
    revision = session.get(EvidenceRevision, UUID(row["evidence_revision_id"]))
    evidence = session.get(Evidence, revision.evidence_id)
    source = session.get(SourceDocument, UUID(row["source_id"]))
    return {
        "evidence_id": evidence.public_id, "evidence_revision_no": revision.revision_no,
        "source_id": source.public_id, "source_title": row["source_title"],
        "source_edition": row["source_edition"],
        "source_revision_no": row["source_revision_no"],
        "quote_text": row["quote_text"], "context_before": row["context_before"],
        "context_after": row["context_after"],
        "citation_locator": row["citation_locator"],
        "evidence_strength": row.get("evidence_strength"),
    }


@router.get("/tasks/{task_public_id}/report", response_model=ReportResponse)
def get_report(task_public_id: str,
               actor: Annotated[Actor, Depends(_read_actor)]) -> ReportResponse:
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        task = session.get(ResearchTask, task_id)
        report = session.scalar(select(StructuredReport).where(
            StructuredReport.task_id == task_id))
        if task.status != "COMPLETED" or report is None:
            raise ApiError("REPORT_NOT_READY", status=409, category="conflict",
                           detail="this research task has no final report yet")
        content = report.content
        sections = {category: [{
            "assertion_text": finding["assertion_text"],
            "claim_type": finding["claim_type"],
            "agent_role": finding["agent_role"],
            "audit_verdict": finding["audit_verdict"],
            "audit_rationale": finding["audit_rationale"],
            "reason_type": (
                "AUDIT" if finding["reason_id"] == finding["audit_result_id"]
                else "DISPUTE" if finding["reason_id"] in finding["dispute_ids"]
                else "EVIDENCE_GAP"
            ),
            "evidence": [_public_evidence(session, row) for row in finding["evidence"]],
        } for finding in rows] for category, rows in content["sections"].items()}
        return ReportResponse(
            task_id=task.public_id, schema_version=report.schema_version,
            content_hash=report.content_hash, question=content["question"],
            counts=content["counts"], sections=sections,
            open_disputes=[{"reason_code": row["reason_code"],
                            "rationale_summary": row["rationale_summary"]}
                           for row in content["open_disputes"]],
            unresolved_gaps=[{"reason_code": row["reason_code"],
                              "rationale_summary": row["rationale_summary"]}
                             for row in content["unresolved_gaps"]],
            excluded_claim_count=content["excluded_claim_count"],
        )


def _export(session, task_id: UUID, file_format: str) -> tuple[ReportExport, TaskJob]:
    if file_format not in {"markdown", "docx"}:
        raise ApiError("INVALID_FORMAT", status=400, category="validation",
                       detail="format must be markdown or docx")
    export = session.scalar(select(ReportExport).where(
        ReportExport.task_id == task_id, ReportExport.file_format == file_format)
        .order_by(ReportExport.created_at.desc()).limit(1))
    if export is None:
        raise ApiError("EXPORT_NOT_FOUND", status=404, category="reference",
                       detail="report export does not exist")
    return export, session.get(TaskJob, export.job_id)


@router.post("/tasks/{task_public_id}/exports/{file_format}")
def queue_export(task_public_id: str, file_format: Literal["markdown", "docx"],
                 request: Request,
                 actor: Annotated[Actor, Depends(_write_actor)]) -> JSONResponse:
    required_idempotency_key(request.headers.get("Idempotency-Key"))
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
    try:
        queue_report_export(task_id, file_format, actor_id=actor.actor_id)
    except ValueError as exc:
        raise ApiError("REPORT_NOT_READY", status=409, category="conflict",
                       detail=str(exc)) from exc
    with SessionLocal() as session:
        _, job = _export(session, task_id, file_format)
        return accepted_job_response(job)


@router.get("/tasks/{task_public_id}/exports/{file_format}", response_model=ExportResponse)
def get_export(task_public_id: str, file_format: str,
               actor: Annotated[Actor, Depends(_read_actor)]) -> ExportResponse:
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        export, job = _export(session, task_id, file_format)
        url = (f"/api/v1/research/tasks/{task_public_id}/exports/{file_format}/download"
               if export.artifact_id is not None else None)
        return ExportResponse(file_format=file_format, status=job.status,
                              job_id=job.public_id, download_url=url)


@router.get("/tasks/{task_public_id}/exports/{file_format}/download")
def download_export(task_public_id: str, file_format: str,
                    actor: Annotated[Actor, Depends(_read_actor)]) -> FileResponse:
    with SessionLocal() as session:
        task_id = resolve_public_id(session, "research_task", task_public_id, actor)
        export, job = _export(session, task_id, file_format)
        if job.status != "COMPLETED" or export.artifact_id is None:
            raise ApiError("EXPORT_NOT_READY", status=409, category="conflict",
                           detail="report export is not complete")
        artifact = session.get(Artifact, export.artifact_id)
        path = ContentAddressedStore(settings.data_root).path_for(artifact.blob_sha256)
        if not path.is_file():
            raise ApiError("EXPORT_UNAVAILABLE", status=503, category="availability",
                           detail="report export file is unavailable", retryable=True)
        filename = f"research-{task_public_id}.{'md' if file_format == 'markdown' else 'docx'}"
    return FileResponse(path, filename=filename, media_type=(
        "text/markdown; charset=utf-8" if file_format == "markdown"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        headers={"Cache-Control": "no-store"})
