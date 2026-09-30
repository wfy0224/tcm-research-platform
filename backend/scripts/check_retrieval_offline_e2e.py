"""Real HTTP/browser and production transport checks in a Docker internal network.

Requires an isolated test container with no external network attachment. No real
credential is used. Index vectors are deterministic doubles, not model quality.
stdin supplies a bootstrap secret; a subsequent `finish` runs strict checks.
"""

import base64
import hashlib
import json
import os
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

DATABASE = "tcm_vib48_offline_" + uuid4().hex[:8] + "_test"
PORT = 18065
ORIGIN = "http://127.0.0.1:18066"


def main():
    if os.environ.get("TCM_OFFLINE_ACCEPTANCE") != "internal-network-v1":
        raise RuntimeError("requires dedicated Docker internal network")
    # Assert actual network isolation before installing even a dummy API token.
    with socket.socket() as probe:
        probe.settimeout(1)
        try:
            probe.connect(("1.1.1.1", 443))
        except OSError:
            pass
        else:
            raise RuntimeError("external routing exists; refuse offline acceptance")

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["TCM_DATABASE_URL"])
    if not url.database.startswith("tcm_") or not url.database.endswith("_test"):
        raise RuntimeError("refuse non-test source credentials")
    url = url.set(host="retrieval-db", port=5432, database=DATABASE)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        if connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": DATABASE}):
            raise RuntimeError("use a fresh isolated database; retain prior evidence")
        connection.exec_driver_sql(f"CREATE DATABASE {DATABASE}")
    admin.dispose()
    os.environ["TCM_DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["TCM_DATA_ROOT"] = "/tmp/tcm_vib48_offline_e2e_store"
    os.environ["TCM_PREVIEW_CORPUS"] = "none"
    os.environ["TCM_OUTBOUND_MODE"] = "CLOUD_ALLOWED"
    os.environ["TCM_ALLOW_ENV_API_KEYS"] = "1"
    for name in tuple(os.environ):
        if name.endswith("_API_KEY"):
            del os.environ[name]
    os.environ["SILICONFLOW_API_KEY"] = "offline-probe-not-a-real-credential"
    initial = json.loads(sys.stdin.readline())
    os.environ["TCM_BOOTSTRAP_SECRET"] = initial["secret"]
    os.environ["TCM_LOCAL_ALLOWED_ORIGINS"] = ORIGIN
    command.upgrade(Config("alembic.ini"), "head")

    import httpx
    import uvicorn
    from check_knowledge_api_live import _finish_source

    from tcm_platform import knowledge_worker
    from tcm_platform.audit import verify_chain
    from tcm_platform.cloud_models import cloud_clients_from_environment
    from tcm_platform.db import SessionLocal
    from tcm_platform.main import app
    from tcm_platform.model_errors import ModelUnavailableError
    from tcm_platform.models import (
        Evidence,
        EvidenceRevision,
        ModelInvocation,
        RetrievalBenchmarkRun,
        SourceDocument,
        TaskEvidenceRef,
    )
    from tcm_platform.research_service import (
        create_research_task,
        retrieve_for_task,
        save_research_plan,
        start_research_task,
    )
    from tcm_platform.retrieval_benchmark import create_golden_query, run_benchmark

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT,
                                          log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    checks = ["external_tcp_route_blocked"]
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("real HTTP server did not start")
        embedder, reranker = cloud_clients_from_environment()

        class IndexEmbedder:
            model_version = embedder.model_version
            endpoint = embedder.endpoint
            max_batch_size = 32
            is_remote = False

            def embed(self, texts):
                return [[1.0, 0.5] for _ in texts]

        class IndexReranker:
            model_version = reranker.model_version
            endpoint = reranker.endpoint

        def emit(value):
            print(json.dumps(value, ensure_ascii=False), flush=True)

        with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=120) as client:
            def request(method, path, **kwargs):
                response = client.request(method, path, **kwargs)
                if response.status_code >= 400:
                    raise RuntimeError(f"{method} {path}: HTTP {response.status_code} {response.text}")
                return response.json()

            assert request("GET", "/api/v1/system/health")["schema"] == "current"
            auth = request("POST", "/api/v1/local-session/bootstrap", headers={"Origin": ORIGIN},
                           json={"bootstrap_secret": initial["secret"]})
            headers = {"Origin": ORIGIN, "X-CSRF-Token": auth["csrf_token"]}
            fixtures = Path(__file__).resolve().parents[1] / "fixtures"
            manifest = json.loads((fixtures / "initial_corpus.json").read_text(encoding="utf-8"))
            source = manifest["sources"][0]
            content = (fixtures / source["file"]).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(content).hexdigest() == source["canonical_sha256"]
            first = next(p for p in content.decode().split("\n\n") if p.strip()).strip()
            metadata = {**source["source_metadata"], "title": "VIB-48 隔离断网验收原文",
                        "outbound_authorized": True,
                        "outbound_reason": "隔离无外网验收，仅测试工程引用；非专家审核"}
            imported = request("POST", "/api/v1/knowledge/sources/import",
                               headers={**headers, "Idempotency-Key": "vib48-offline-source"},
                               json={"metadata": metadata, "file_format": "txt",
                                     "content_base64": base64.b64encode(first.encode()).decode()})
            assert request("POST", "/api/v1/knowledge/sources/import",
                           headers={**headers, "Idempotency-Key": "vib48-offline-source"},
                           json={"metadata": metadata, "file_format": "txt",
                                 "content_base64": base64.b64encode(first.encode()).decode()}) == imported
            _finish_source(imported["source_id"])
            segments = request("GET", f"/api/v1/knowledge/sources/{imported['source_id']}/revisions/1/segments")
            segment = next(row for row in segments if row["segment_type"] == "PARAGRAPH")
            evidence = request("POST", "/api/v1/knowledge/drafts/evidence", headers=headers,
                               json={"segment_ids": [f"{segment['segment_id']}@1"], "strength": "DIRECT"})
            evidence_ref = f"{evidence['evidence_id']}@{evidence['revision_no']}"
            request("POST", f"/api/v1/knowledge/reviews/evidence_revision/{evidence_ref}",
                    headers=headers, json={"decision": "APPROVE", "note": "原文工程验收；非医学专家结论"})
            version = request("POST", "/api/v1/knowledge/versions", headers=headers)
            published = request("POST", f"/api/v1/knowledge/versions/{version['version_id']}/publish",
                                headers={**headers, "Idempotency-Key": "vib48-offline-publish"},
                                json={"embedding_model": embedder.model_version,
                                      "rerank_model": reranker.model_version,
                                      "embedding_endpoint": embedder.endpoint,
                                      "rerank_endpoint": reranker.endpoint})
            original_factory = knowledge_worker.cloud_clients_from_environment
            knowledge_worker.cloud_clients_from_environment = lambda: (IndexEmbedder(), IndexReranker())
            try:
                assert knowledge_worker.process_next_knowledge_publish() is not None
            finally:
                knowledge_worker.cloud_clients_from_environment = original_factory
            assert request("GET", f"/api/v1/jobs/{published['job_id']}")["status"] == "COMPLETED"
            assert request("GET", f"/api/v1/knowledge/versions/{version['version_id']}")["active"]
            checks.append("http_import_idempotency_parse_segment_review_publish_worker")
            query = "  太阳  "
            local = request("GET", "/api/v1/retrieval/query", params={"query": query})
            assert local["mode"] == "LOCAL" and local["query_text"] == query
            assert local["results"][0]["quote_text"] == first
            assert local["results"][0]["evidence_id"] == evidence["evidence_id"]
            assert local["results"][0]["segment_ids"] == [segment["segment_id"]]
            with SessionLocal() as session:
                assert session.scalar(select(func.count(ModelInvocation.id))) == 0
            checks.append("offline_local_simplified_query_original_quote_public_revision_no_model_call")
            remote = request("GET", "/api/v1/retrieval/query",
                             params={"query": query, "allow_remote_query": True})
            assert remote["mode"] == "DEGRADED" and remote["reasons"] == ["embedding_unavailable"]
            assert remote["results"] == local["results"] and "vector" not in remote["channels"]
            with SessionLocal() as session:
                calls = list(session.scalars(select(ModelInvocation)))
                assert len(calls) == 1 and calls[0].status == "FAILED"
                assert calls[0].error_class == "ModelUnavailableError"
                assert calls[0].transport_retry_count == 2
            checks.append("production_cloud_transport_failed_and_audited_local_fallback_identical")
            del os.environ["SILICONFLOW_API_KEY"]
            missing = request("GET", "/api/v1/retrieval/query",
                              params={"query": query, "allow_remote_query": True})
            assert missing["mode"] == "DEGRADED"
            assert missing["reasons"] in (["model_not_configured"], ["credential_unavailable"])
            assert missing["results"] == local["results"]
            os.environ["SILICONFLOW_API_KEY"] = "offline-probe-not-a-real-credential"
            checks.append("actual_linux_missing_credential_local_fallback")
            emit({"ready": True, "database": DATABASE, "port": PORT, "query": query,
                  "quote": first, "evidence_id": evidence["evidence_id"], "checks": checks,
                  "real_cloud_completions": 0, "index_vectors": "deterministic_double"})
            for line in sys.stdin:
                action = json.loads(line)["action"]
                if action != "finish":
                    raise RuntimeError("unknown acceptance control")
                with SessionLocal() as session:
                    source_id = session.scalar(select(SourceDocument.id).where(
                        SourceDocument.public_id == imported["source_id"]))
                    proof = session.scalar(select(EvidenceRevision.id).join(Evidence,
                        EvidenceRevision.evidence_id == Evidence.id).where(
                            Evidence.public_id == evidence["evidence_id"]))
                task = create_research_task(query, source_ids=[source_id])
                start_research_task(task, model_version="siliconflow/offline-acceptance",
                                    question_outbound_authorized=True)
                save_research_plan(task, {"subquestions": [query]})
                try:
                    retrieve_for_task(task, embedder=embedder, reranker=reranker)
                except ModelUnavailableError:
                    pass
                else:
                    raise RuntimeError("research silently degraded")
                with SessionLocal() as session:
                    assert not session.scalar(select(TaskEvidenceRef.id).where(TaskEvidenceRef.task_id == task))
                create_golden_query(query, {proof: "GOLD"}, source_ids=[source_id])
                try:
                    run_benchmark(embedder=embedder, reranker=reranker,
                                  query_outbound_authorized=True)
                except ModelUnavailableError:
                    pass
                else:
                    raise RuntimeError("benchmark silently degraded")
                with SessionLocal() as session:
                    assert session.scalar(select(func.count(RetrievalBenchmarkRun.id))) == 0
                    calls = list(session.scalars(select(ModelInvocation)))
                    assert calls and all(row.status == "FAILED" for row in calls)
                with SessionLocal() as session:
                    assert verify_chain(session)
                checks.extend(["research_and_benchmark_strict_failure_without_pool_or_metrics",
                               "audit_chain_verified"])
                emit({"passed": True, "checks": checks, "database": DATABASE,
                      "failed_transport_invocations": len(calls), "real_cloud_completions": 0,
                      "index_vectors": "deterministic_double"})
                break
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def forward():
    """Loopback-only host relay; the API container itself retains no outside route."""
    import select

    class Relay(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.create_connection(("retrieval-api", PORT), timeout=10) as upstream:
                while True:
                    readable, _, _ = select.select([self.request, upstream], [], [], 1)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        target = upstream if source is self.request else self.request
                        target.sendall(data)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("0.0.0.0", PORT), Relay) as server:
        server.serve_forever()


if __name__ == "__main__":
    if sys.argv[1:] == ["--forward"]:
        forward()
    else:
        main()
