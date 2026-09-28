from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.api_contract import (
    Actor,
    ApiError,
    error_response,
    etag_for,
    resolve_public_id,
)
from tcm_platform.cloud_models import cloud_clients_from_environment
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import HealthState
from tcm_platform.local_auth import (
    COOKIE_NAME,
    bootstrap_local_session,
    current_actor,
    require_csrf,
    revoke_local_session,
)
from tcm_platform.models import (
    Evidence,
    EvidenceRevision,
    SourceDocument,
    SourceRevision,
    TaskJob,
    TextSegment,
    TextSegmentRevision,
)
from tcm_platform.retrieval import search_published

SCHEMA_REVISION = "0020_outbound_source_policy"


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bootstrap_secret: SecretStr


class LocalSessionResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str
    actor_id: str
    capabilities: list[str]
    expires_at: datetime
    csrf_token: str | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    job_id: str
    job_type: str
    status: str
    attempts: int
    max_attempts: int


class RetrievalEvidenceResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    evidence_id: str
    evidence_revision_no: int
    source_id: str
    source_title: str
    source_author: str | None
    source_era: str | None
    source_school: str | None
    source_edition: str | None
    source_publication_year: int | None
    source_revision_no: int
    quote_text: str
    context_before: str
    context_after: str
    citation_locator: dict
    segment_ids: list[str]
    matched_channels: list[str]
    retrieval_score: float
    rerank_score: float | None


def _public_retrieval_result(trace: dict) -> RetrievalEvidenceResponse:
    """Map internal provenance to a versioned, public HTTP representation."""
    with SessionLocal() as session:
        revision = session.get(EvidenceRevision, UUID(trace["evidence_revision_id"]))
        evidence = session.get(Evidence, revision.evidence_id)
        source_revision = session.get(SourceRevision, revision.source_revision_id)
        source = session.get(SourceDocument, source_revision.source_id)
        segment_ids = [
            session.get(TextSegment, session.get(TextSegmentRevision, UUID(value)).segment_id)
            .public_id
            for value in trace["segment_revision_ids"]
        ]
        locator = {key: trace["citation_locator"][key] for key in ("start", "end")}
        return RetrievalEvidenceResponse(
            evidence_id=evidence.public_id, evidence_revision_no=revision.revision_no,
            source_id=source.public_id, source_title=trace["source_title"],
            source_author=trace["source_author"], source_era=trace["source_era"],
            source_school=trace["source_school"], source_edition=trace["source_edition"],
            source_publication_year=trace["source_publication_year"],
            source_revision_no=trace["source_revision_no"], quote_text=trace["quote_text"],
            context_before=trace["context_before"], context_after=trace["context_after"],
            citation_locator=locator, segment_ids=segment_ids,
            matched_channels=trace["matched_channels"],
            retrieval_score=trace["retrieval_score"], rerank_score=trace["rerank_score"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: HealthState
    database: str
    schema_status: str = Field(alias="schema")
    blob_store: str
    preview_corpus: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="TCM Research Platform", version="0.1.0", lifespan=lifespan)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid4().hex)


@app.middleware("http")
async def local_api_boundary(request: Request, call_next):
    request.state.request_id = uuid4().hex
    if request.url.path.startswith("/api/v1/"):
        host = request.url.hostname
        if host not in {"127.0.0.1", "::1"}:
            response = error_response(ApiError(
                "LOOPBACK_REQUIRED", status=403, category="authorization",
                detail="local API requests require a loopback Host"), _request_id(request))
            response.headers["X-Request-ID"] = _request_id(request)
            return response
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            allowed = {origin.strip() for origin in settings.local_allowed_origins.split(",")
                       if origin.strip()}
            if request.headers.get("origin") not in allowed:
                response = error_response(ApiError(
                    "ORIGIN_DENIED", status=403, category="authorization",
                    detail="command Origin is not an allowed local application origin"),
                    _request_id(request))
                response.headers["X-Request-ID"] = _request_id(request)
                return response
    response = await call_next(request)
    response.headers["X-Request-ID"] = _request_id(request)
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return error_response(exc, _request_id(request))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, _: RequestValidationError):
    return error_response(ApiError("INVALID_REQUEST", status=422, category="validation",
                                   detail="request does not match the strict API contract"),
                          _request_id(request))


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    category = "availability" if exc.status_code >= 500 else "validation"
    return error_response(ApiError("SERVICE_UNAVAILABLE" if exc.status_code >= 500
                                   else "INVALID_REQUEST", status=exc.status_code,
                                   category=category, detail=str(exc.detail),
                                   retryable=exc.status_code >= 500), _request_id(request))


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, _: SQLAlchemyError):
    return error_response(ApiError("DATABASE_UNAVAILABLE", status=503,
                                   category="availability", detail="local database is unavailable",
                                   retryable=True), _request_id(request))


def _actor(request: Request) -> Actor:
    return current_actor(request.cookies.get(COOKIE_NAME))


def _mutating_actor(request: Request) -> Actor:
    actor = _actor(request)
    require_csrf(actor, request.headers.get("X-CSRF-Token"))
    return actor


@app.post("/api/v1/local-session/bootstrap", response_model=LocalSessionResponse)
def bootstrap(request: BootstrapRequest, response: Response) -> LocalSessionResponse:
    issued = bootstrap_local_session(request.bootstrap_secret.get_secret_value())
    response.set_cookie(COOKIE_NAME, issued.cookie_token, httponly=True,
                        samesite="strict", secure=settings.secure_session_cookie,
                        path="/api/v1", max_age=settings.session_ttl_seconds)
    response.headers["Cache-Control"] = "no-store"
    return LocalSessionResponse(session_id=issued.public_id, actor_id=issued.actor_id,
                                capabilities=list(issued.capabilities),
                                expires_at=issued.expires_at, csrf_token=issued.csrf_token)


@app.get("/api/v1/local-session", response_model=LocalSessionResponse)
def show_local_session(response: Response,
                       actor: Annotated[Actor, Depends(_actor)]) -> LocalSessionResponse:
    actor.require("session.manage")
    response.headers["ETag"] = etag_for(actor.session_public_id, actor.session_version)
    response.headers["Cache-Control"] = "no-store"
    return LocalSessionResponse(session_id=actor.session_public_id, actor_id=actor.actor_id,
                                capabilities=sorted(actor.capabilities),
                                expires_at=actor.expires_at)


@app.delete("/api/v1/local-session", status_code=204)
def delete_local_session(request: Request, response: Response,
                         actor: Annotated[Actor, Depends(_mutating_actor)]) -> None:
    revoke_local_session(actor, if_match=request.headers.get("If-Match"))
    response.delete_cookie(COOKIE_NAME, path="/api/v1")


@app.get("/api/v1/jobs/{job_public_id}", response_model=JobResponse)
def show_job(job_public_id: str, actor: Annotated[Actor, Depends(_actor)]) -> JobResponse:
    with SessionLocal() as session:
        job_id = resolve_public_id(session, "job", job_public_id, actor)
        job = session.get(TaskJob, job_id)
        return JobResponse(job_id=job.public_id, job_type=job.job_type,
                           status=job.status, attempts=job.attempts,
                           max_attempts=job.max_attempts)


@app.get("/api/v1/system/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database = "unavailable"
    schema = "unknown"
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            database = "connected"
            version = session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
            schema = "current" if version == SCHEMA_REVISION else "migration_required"
    except SQLAlchemyError:
        # Keep the health endpoint available while PostgreSQL starts or migration is pending.
        schema = "unavailable"
    blob_store = "available" if settings.data_root.is_dir() else "unavailable"
    state = (
        HealthState.DEGRADED
        if database == "connected" and schema == "current" and blob_store == "available"
        else HealthState.NOT_READY
    )
    return HealthResponse(state=state, database=database, schema=schema,
                          blob_store=blob_store,
                          preview_corpus=settings.preview_corpus)


@app.get("/api/v1/retrieval/search", response_model=list[RetrievalEvidenceResponse])
def search_retrieval(
    query: str = Query(min_length=1, max_length=2_000),
    limit: int = Query(default=10, ge=1, le=100),
    allow_remote_query: bool = Query(default=False),
) -> list[RetrievalEvidenceResponse]:
    try:
        embedder, reranker = cloud_clients_from_environment()
        traces = search_published(query, embedder=embedder, reranker=reranker, limit=limit,
                                  query_outbound_authorized=allow_remote_query)
        return [_public_retrieval_result(trace) for trace in traces]
    except ValueError as exc:
        status = 503 if ("not configured" in str(exc)
                         or "no published knowledge version" in str(exc)) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        status = 429 if "rate limit" in str(exc) else 503
        raise HTTPException(status_code=status, detail=str(exc)) from exc

