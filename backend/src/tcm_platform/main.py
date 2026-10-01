import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal
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
from tcm_platform.knowledge_api import router as knowledge_router
from tcm_platform.local_auth import (
    COOKIE_NAME,
    IssuedSession,
    bootstrap_local_session,
    current_actor,
    development_local_session,
    require_csrf,
    revoke_local_session,
)
from tcm_platform.model_errors import ModelCredentialMissing, ModelCredentialUnavailable
from tcm_platform.models import (
    Evidence,
    EvidenceRevision,
    SourceDocument,
    SourceRevision,
    TaskJob,
    TextSegment,
    TextSegmentRevision,
)
from tcm_platform.research_api import router as research_router
from tcm_platform.research_capabilities import router as research_capabilities_router
from tcm_platform.research_model_settings import router as research_model_settings_router
from tcm_platform.retrieval import RetrievalExecution, search_published

SCHEMA_REVISION = "0026_term_resolution"


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
    failure_reason: str | None = None


class RetrievalDiversityResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    policy: Literal["source-context/v1"]
    relevance_rank: int
    source_occurrence: int
    context_overlap: float
    selection_score: float


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
    diversity: RetrievalDiversityResponse | None = None


class RetrievalSearchResponse(BaseModel):
    query_text: str
    normalized_query: str
    mode: Literal["LOCAL", "HYBRID", "DEGRADED"]
    reasons: list[str]
    channels: list[str]
    results: list[RetrievalEvidenceResponse]


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
            retrieval_score=trace["retrieval_score"], rerank_score=trace["rerank_score"],
            diversity=trace.get("diversity"))


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
app.include_router(research_router)
app.include_router(research_capabilities_router)
app.include_router(research_model_settings_router)
app.include_router(knowledge_router)


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


def _session_response(issued: IssuedSession, response: Response) -> LocalSessionResponse:
    response.set_cookie(COOKIE_NAME, issued.cookie_token, httponly=True,
                        samesite="strict", secure=settings.secure_session_cookie,
                        path="/api/v1", max_age=settings.session_ttl_seconds)
    response.headers["Cache-Control"] = "no-store"
    return LocalSessionResponse(session_id=issued.public_id, actor_id=issued.actor_id,
                                capabilities=list(issued.capabilities),
                                expires_at=issued.expires_at, csrf_token=issued.csrf_token)


@app.get("/api/v1/local-session/config")
def local_session_config(response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {"development_auto_session": settings.development_auto_session}


@app.post("/api/v1/local-session/development", response_model=LocalSessionResponse)
def development_session(request: Request, response: Response) -> LocalSessionResponse:
    return _session_response(development_local_session(request.cookies.get(COOKIE_NAME)), response)


@app.post("/api/v1/local-session/bootstrap", response_model=LocalSessionResponse)
def bootstrap(request: BootstrapRequest, response: Response) -> LocalSessionResponse:
    return _session_response(
        bootstrap_local_session(request.bootstrap_secret.get_secret_value()), response)


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
                           max_attempts=job.max_attempts,
                           failure_reason=_job_failure_reason(job))


def _job_failure_reason(job: TaskJob) -> str | None:
    """Expose actionable failure classes without returning raw exception text."""
    if not job.last_error or job.status not in {"FAILED", "RETRY_WAIT"}:
        return None
    error = job.last_error.casefold()
    from tcm_platform.research_failures import report_review_exhausted
    if report_review_exhausted(job.last_error):
        return "综合回答三稿均未通过复核。可保存已有研究报告，保留已审计结果、辩论和待修订草稿，再继续修订。"
    if "credential" in error or "api key" in error or "api_key" in error:
        return "研究模型凭据不可用，请联系管理员核对模型连接。"
    if "outbound" in error or "authorized" in error or "authorization" in error:
        return "当前来源或研究问题尚未满足模型外发授权条件。"
    if "modelresponse" in error or "json" in error or "protocol" in error:
        return "模型返回内容未通过格式或引用校验，请核对模型配置后重试。"
    if any(value in error for value in ("timeout", "network", "connection", "unavailable", "urlerror", "http")):
        return "模型服务或网络暂不可用，系统会按任务重试策略处理。"
    if "index" in error or "knowledge version" in error:
        return "知识版本或索引尚未就绪，请先在知识工作区完成发布。"
    return "任务未完成，请核对来源、审核与模型配置后重试。"


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


@app.get("/api/v1/retrieval/capabilities")
def retrieval_capabilities():
    from tcm_platform.models import IndexBuild, KnowledgeRuntimeState
    from tcm_platform.outbound_policy import current_mode, version_source_ids
    with SessionLocal() as session:
        runtime = session.get(KnowledgeRuntimeState, 1)
        build = session.get(IndexBuild, runtime.active_index_build_id) if runtime else None
        strategy = build.configuration.get("strategy") if build else None
        reason = None
        if current_mode() != "CLOUD_ALLOWED":
            reason = "服务策略仍为仅本地，请启用云端模型外发。"
        elif not build or build.status != "READY" or build.vector_status != "READY":
            reason = "当前检索版本没有可用向量索引，请在知识库中按云端配置重新加入并启用版本。"
        else:
            sources = [session.get(SourceDocument, source_id) for source_id in
                       version_source_ids(session, build.knowledge_version_id)]
            if any(source.data_level != "PUBLIC" or not source.outbound_authorized
                   for source in sources):
                reason = "当前版本包含未允许外发的来源，请核对来源授权。"
        return {"cloud_ready": reason is None, "reason": reason,
                "mode": current_mode(), "strategy": strategy,
                "embedding_model": build.configuration.get("embedding_model") if build else None,
                "rerank_model": build.configuration.get("rerank_model") if build else None}


@app.get("/api/v1/retrieval/query", response_model=RetrievalSearchResponse)
def query_retrieval(
    query: str = Query(min_length=1, max_length=2_000),
    limit: int = Query(default=10, ge=1, le=100),
    allow_remote_query: bool = Query(default=False),
    mode: Literal["auto", "local"] = Query(default="auto"),
) -> RetrievalSearchResponse:
    try:
        execution = RetrievalExecution()
        embedder, reranker = None, None
        if mode == "local":
            execution.reasons.append("local_requested")
        elif not allow_remote_query:
            execution.reasons.append("remote_query_not_authorized")
        else:
            try:
                embedder, reranker = cloud_clients_from_environment()
            except ModelCredentialMissing:
                execution.degrade("model_not_configured")
            except ModelCredentialUnavailable:
                execution.degrade("credential_unavailable")
            except ValueError:
                execution.degrade("model_configuration_error")
        traces = search_published(query, embedder=embedder, reranker=reranker, limit=limit,
                                  query_outbound_authorized=allow_remote_query,
                                  allow_model_fallback=True, execution=execution)
        return RetrievalSearchResponse(
            query_text=query, normalized_query=unicodedata.normalize("NFKC", query).strip(),
            mode=execution.mode, reasons=execution.reasons, channels=execution.channels,
            results=[_public_retrieval_result(trace) for trace in traces],
        )
    except ValueError as exc:
        status = 503 if ("not configured" in str(exc)
                         or "no published knowledge version" in str(exc)) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        status = 429 if "rate limit" in str(exc) else 503
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@app.get("/api/v1/retrieval/search", response_model=list[RetrievalEvidenceResponse])
def search_retrieval(
    query: str = Query(min_length=1, max_length=2_000),
    limit: int = Query(default=10, ge=1, le=100),
    allow_remote_query: bool = Query(default=False),
    mode: Literal["auto", "local"] = Query(default="auto"),
) -> list[RetrievalEvidenceResponse]:
    """Keep the legacy array contract; new clients use /query for execution status."""
    return query_retrieval(query, limit, allow_remote_query, mode).results

