"""Opt-in real-model VIB-60 smoke test against a disposable local database.

Requires --execute. Keep this out of automated pytest: it makes real cloud calls.
"""

import argparse
import base64
import os
import secrets
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.engine.url import make_url

from tcm_platform.cloud_models import cloud_clients_from_environment
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.knowledge_worker import process_next_knowledge_publish
from tcm_platform.main import app
from tcm_platform.models import (
    ImportJob,
    ModelInvocation,
    SourceDocument,
    SourceRevision,
    TextSegmentRevision,
)
from tcm_platform.segment_service import process_next_segment
from tcm_platform.source_import import process_next_import
from tcm_platform.storage import ContentAddressedStore

DATABASE_NAME = "tcm_vib60_live_test"
ORIGIN = "http://127.0.0.1:5173"


def _check_environment() -> tuple[str, str]:
    if make_url(settings.database_url).database != DATABASE_NAME:
        raise RuntimeError(f"refusing to run outside the disposable {DATABASE_NAME} database")
    if os.environ.get("TCM_OUTBOUND_MODE") != "CLOUD_ALLOWED":
        raise RuntimeError("TCM_OUTBOUND_MODE must be CLOUD_ALLOWED")
    if os.environ.get("TCM_ALLOW_ENV_API_KEYS") != "1":
        raise RuntimeError("isolated-container environment key access must be enabled")
    if os.environ.get("TCM_MODEL_PROVIDER", "siliconflow").lower() != "siliconflow":
        raise RuntimeError("this smoke test is scoped to the existing SiliconFlow preview route")
    if not str(settings.data_root).startswith("/tmp/tcm_vib60_live_store"):
        raise RuntimeError("TCM_DATA_ROOT must point to the dedicated temporary store")
    if not os.environ.get("SILICONFLOW_API_KEY"):
        raise RuntimeError("SILICONFLOW_API_KEY is unavailable inside this process")
    embedder, reranker = cloud_clients_from_environment()
    return embedder.model_version, reranker.model_version


def _request(client: TestClient, method: str, path: str, **kwargs) -> dict:
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path}: HTTP {response.status_code} {response.text}")
    return response.json()


def _finish_source(source_public_id: str) -> None:
    with SessionLocal() as session:
        source_id = session.scalar(select(SourceDocument.id).where(
            SourceDocument.public_id == source_public_id))
        revision = session.scalar(select(SourceRevision).where(
            SourceRevision.source_id == source_id, SourceRevision.revision_no == 1))
        import_job = session.scalar(select(ImportJob).where(
            ImportJob.source_revision_id == revision.id))
        import_job_id = import_job.id
        status = import_job.status
    store = ContentAddressedStore(settings.data_root)
    if status == "REGISTERED":
        parsed = process_next_import(store=store)
        if parsed is None or parsed.import_job_id != import_job_id or parsed.status != "PARSED":
            raise RuntimeError("source parse job did not complete")
        status = "PARSED"
    if status == "PARSED":
        segmented = process_next_segment(store=store)
        if (segmented is None or segmented.import_job_id != import_job_id
                or segmented.status != "SEGMENTED"):
            raise RuntimeError("source segmentation job did not complete")
    with SessionLocal() as session:
        finished = session.get(ImportJob, import_job_id)
        if finished.status != "SEGMENTED":
            raise RuntimeError(f"source import stopped at {finished.status}")
        if session.scalar(select(func.count(TextSegmentRevision.id)).where(
            TextSegmentRevision.source_revision_id == revision.id)) == 0:
            raise RuntimeError("source segmentation produced no text")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="allow real model calls")
    args = parser.parse_args()
    embedding_model, rerank_model = _check_environment()
    if not args.execute:
        print({"ready": True, "database": DATABASE_NAME,
               "embedding_model": embedding_model, "rerank_model": rerank_model,
               "real_calls": 0})
        return

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "shanghanlun_taiyang_upper.txt"
    source_text = next(line for line in fixture.read_text(encoding="utf-8").splitlines()
                       if line.strip())
    secret = secrets.token_urlsafe(32)
    settings.bootstrap_secret = SecretStr(secret)
    embedder, reranker = cloud_clients_from_environment()
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        bootstrap = _request(client, "POST", "/api/v1/local-session/bootstrap",
                             headers={"Origin": ORIGIN}, json={"bootstrap_secret": secret})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": bootstrap["csrf_token"]}
        imported = _request(client, "POST", "/api/v1/knowledge/sources/import",
                            headers={**headers, "Idempotency-Key": "vib60-live-source-v1"},
                            json={"metadata": {
                                "source_type": "CLASSIC", "title": "傷寒論 VIB-60 API 冒烟片段",
                                "author": "張仲景", "edition": "維基文庫宋本修訂 2607901",
                                "copyright_status": "PUBLIC_DOMAIN", "data_level": "PUBLIC",
                                "outbound_authorized": True,
                                "outbound_reason": "公版原文，仅用于本次隔离模型联调",
                            }, "file_format": "txt",
                                "content_base64": base64.b64encode(source_text.encode()).decode()})
        source_id = imported["source_id"]
        _finish_source(source_id)
        segments = _request(client, "GET",
                            f"/api/v1/knowledge/sources/{source_id}/revisions/1/segments")
        segment = next(row for row in segments if row["segment_type"] == "PARAGRAPH")
        evidence = _request(client, "POST", "/api/v1/knowledge/drafts/evidence",
                            headers=headers,
                            json={"segment_ids": [f"{segment['segment_id']}@1"],
                                  "strength": "DIRECT"})
        evidence_ref = f"{evidence['evidence_id']}@{evidence['revision_no']}"
        _request(client, "POST", f"/api/v1/knowledge/reviews/evidence_revision/{evidence_ref}",
                 headers=headers, json={"decision": "APPROVE", "note": "公版原文工程联调；非专家审核"})
        version = _request(client, "POST", "/api/v1/knowledge/versions", headers=headers)
        publish = _request(client, "POST",
                           f"/api/v1/knowledge/versions/{version['version_id']}/publish",
                           headers={**headers, "Idempotency-Key": "vib60-live-publish-v1"},
                           json={"embedding_model": embedder.model_version,
                                 "rerank_model": reranker.model_version,
                                 "embedding_endpoint": embedder.endpoint,
                                 "rerank_endpoint": reranker.endpoint})
        if process_next_knowledge_publish() is None:
            raise RuntimeError("publish job was not acquired")
        job = _request(client, "GET", f"/api/v1/jobs/{publish['job_id']}")
        if job["status"] != "COMPLETED":
            raise RuntimeError(f"real-model publish job stopped at {job['status']}")
        published = _request(client, "GET",
                             f"/api/v1/knowledge/versions/{version['version_id']}")
        if not published["active"] or published["index_builds"][0]["status"] != "READY":
            raise RuntimeError("published knowledge/index pair is not active and ready")
        results = _request(client, "GET", "/api/v1/retrieval/search",
                           params={"query": "太陽之為病", "allow_remote_query": "true",
                                   "limit": 3})
        if not results or results[0]["evidence_id"] != evidence["evidence_id"]:
            raise RuntimeError("real-model retrieval did not resolve the expected evidence")
        with SessionLocal() as session:
            calls = list(session.scalars(select(ModelInvocation)))
            if len(calls) < 3 or any(row.status != "COMPLETED" for row in calls):
                raise RuntimeError("real-model invocation audit is incomplete")
        print({"ready": True, "source_id": source_id, "evidence_id": evidence["evidence_id"],
               "version_id": version["version_id"], "job_status": job["status"],
               "model_invocations": len(calls), "top_result": results[0]["evidence_id"]})


if __name__ == "__main__":
    main()
