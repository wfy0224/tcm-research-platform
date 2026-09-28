"""Stable HTTP contracts and actor-aware command helpers for V1 APIs."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.enums import ResourceClass
from tcm_platform.jobs import enqueue_job
from tcm_platform.models import (
    Evidence,
    KnowledgeVersion,
    LocalSession,
    ResearchTask,
    SourceDocument,
    TaskJob,
)

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
PUBLIC_RESOURCES = {
    "source": (SourceDocument, "SRC-", "knowledge.read"),
    "evidence": (Evidence, "EV-", "knowledge.read"),
    "knowledge_version": (KnowledgeVersion, "KV-", "knowledge.read"),
    "research_task": (ResearchTask, "RT-", "research.read"),
    "job": (TaskJob, "JOB-", "jobs.read"),
    "local_session": (LocalSession, "LS-", "session.manage"),
}


class ApiError(Exception):
    def __init__(self, code: str, *, status: int, category: str,
                 detail: str, retryable: bool = False, audit_ref: str | None = None):
        self.code = code
        self.status = status
        self.category = category
        self.detail = detail
        self.retryable = retryable
        self.audit_ref = audit_ref
        super().__init__(detail)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: str
    category: str
    retryable: bool
    request_id: str
    audit_ref: str | None
    detail: str


class AcceptedJob(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    job_id: str
    status: str


@dataclass(frozen=True)
class Actor:
    actor_id: str
    session_public_id: str
    session_token_hash: str
    csrf_hash: str
    capabilities: frozenset[str]
    session_version: int
    expires_at: datetime

    def require(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise ApiError("CAPABILITY_DENIED", status=403, category="authorization",
                           detail="this local session lacks the required capability")


def error_response(error: ApiError, request_id: str) -> JSONResponse:
    body = ErrorEnvelope(code=error.code, category=error.category,
                         retryable=error.retryable, request_id=request_id,
                         audit_ref=error.audit_ref, detail=error.detail)
    return JSONResponse(status_code=error.status, content=body.model_dump(mode="json"))


def required_idempotency_key(value: str | None) -> str:
    if value is None or not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED", status=400, category="validation",
                       detail="Idempotency-Key must contain 1-200 ASCII letters, digits, or ._:-")
    return value


def etag_for(public_id: str, row_version: int) -> str:
    if row_version < 1:
        raise ValueError("row_version must be positive")
    digest = hashlib.sha256(f"{public_id}:{row_version}".encode()).hexdigest()[:24]
    return f'"{digest}"'


def require_if_match(value: str | None, public_id: str, row_version: int) -> None:
    if value is None:
        raise ApiError("PRECONDITION_REQUIRED", status=428, category="precondition",
                       detail="If-Match is required for this update")
    if value != etag_for(public_id, row_version):
        raise ApiError("VERSION_CONFLICT", status=412, category="conflict",
                       detail="resource version changed; fetch it again")


def resolve_public_id(session: Session, kind: str, value: str, actor: Actor) -> UUID:
    """Resolve an allowed external reference without accepting an internal UUID."""
    if kind not in PUBLIC_RESOURCES:
        raise ValueError("unknown public resource kind")
    model, prefix, capability = PUBLIC_RESOURCES[kind]
    actor.require(capability)
    if not value.startswith(prefix) or len(value) > 80:
        raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                       detail="public resource does not exist")
    internal_id = session.scalar(select(model.id).where(model.public_id == value))
    if internal_id is None:
        raise ApiError("RESOURCE_NOT_FOUND", status=404, category="reference",
                       detail="public resource does not exist")
    return internal_id


def enqueue_actor_job(session: Session, *, actor: Actor, capability: str,
                      idempotency_key: str, job_type: str, payload: dict,
                      resource_class: ResourceClass) -> TaskJob:
    """Application boundary: capability and key are checked before any job write."""
    actor.require(capability)
    key = required_idempotency_key(idempotency_key)
    digest = hashlib.sha256(f"{actor.actor_id}\x00{job_type}\x00{key}".encode()).hexdigest()
    try:
        return enqueue_job(session, idempotency_key=f"api:{digest}", job_type=job_type,
                           payload=payload, resource_class=resource_class,
                           actor_id=actor.actor_id)
    except ValueError as exc:
        raise ApiError("IDEMPOTENCY_CONFLICT", status=409, category="conflict",
                       detail="Idempotency-Key was used for a different command") from exc


def accepted_job_response(job: TaskJob) -> JSONResponse:
    body = AcceptedJob(job_id=job.public_id, status=job.status)
    return JSONResponse(status_code=202, content=body.model_dump(mode="json"),
                        headers={"Location": f"/api/v1/jobs/{job.public_id}"})
