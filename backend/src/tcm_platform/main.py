from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tcm_platform.cloud_models import cloud_clients_from_environment
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import HealthState
from tcm_platform.retrieval import search_published

SCHEMA_REVISION = "0017_judge_report"


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: HealthState
    database: str
    schema_status: str = Field(alias="schema")
    blob_store: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="TCM Research Platform", version="0.1.0", lifespan=lifespan)


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
    return HealthResponse(state=state, database=database, schema=schema, blob_store=blob_store)


@app.get("/api/v1/retrieval/search")
def search_retrieval(
    query: str = Query(min_length=1, max_length=2_000),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict]:
    try:
        embedder, reranker = cloud_clients_from_environment()
        return search_published(query, embedder=embedder, reranker=reranker, limit=limit)
    except ValueError as exc:
        status = 503 if ("not configured" in str(exc)
                         or "no published knowledge version" in str(exc)) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

