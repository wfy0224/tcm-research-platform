"""Real HTTP API and explicitly driven fake-model Worker for VIB-63 browser checks.

Run only in the existing Linux test container. Reuse its PostgreSQL credentials,
but explicitly select tcm_vib60_test; never use the configured preview database.
The first stdin line supplies an ephemeral bootstrap secret and question prefix.
Subsequent JSON lines drive production Workers, without adding test HTTP routes.
"""

import argparse
import json
import os
import socket
import socketserver
import sys
import threading
from pathlib import Path
from uuid import UUID


def forward() -> None:
    """Expose the test API through a separate loopback-published Docker container."""
    import select

    class Relay(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.create_connection(("research-api", 18063), timeout=10) as upstream:
                upstream.settimeout(None)
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

    with Server(("0.0.0.0", 18063), Relay) as server:
        server.serve_forever()


def serve() -> None:
    from sqlalchemy.engine.url import make_url

    if os.environ.get("TCM_E2E_DATABASE") != "tcm_vib60_test":
        raise RuntimeError("explicit TCM_E2E_DATABASE=tcm_vib60_test is required")
    url = make_url(os.environ["TCM_DATABASE_URL"])
    if url.database not in {"tcm_vib54_test", "tcm_vib60_test"}:
        raise RuntimeError("refusing to reuse credentials from a non-test database")
    os.environ["TCM_DATABASE_URL"] = url.set(database="tcm_vib60_test").render_as_string(
        hide_password=False)
    os.environ["TCM_DATA_ROOT"] = "/tmp/tcm_vib63_browser_store"
    os.environ["TCM_PREVIEW_CORPUS"] = "none"
    os.environ["TCM_OUTBOUND_MODE"] = "LOCAL_ONLY"
    os.environ["TCM_ALLOW_ENV_API_KEYS"] = "0"
    for name in tuple(os.environ):
        if name.endswith("_API_KEY"):
            del os.environ[name]
    initial = json.loads(sys.stdin.readline())
    os.environ["TCM_BOOTSTRAP_SECRET"] = initial["secret"]
    os.environ["TCM_LOCAL_ALLOWED_ORIGINS"] = "http://127.0.0.1:18064"

    import uvicorn
    from sqlalchemy import select, text

    from tcm_platform import cloud_models, research_api
    from tcm_platform.db import SessionLocal
    from tcm_platform.knowledge_service import trace_evidence
    from tcm_platform.main import SCHEMA_REVISION, app
    from tcm_platform.models import (
        EmbeddingRecord,
        EvidenceRevision,
        IndexBuild,
        KnowledgeRuntimeState,
        KnowledgeVersionItem,
        ModelInvocation,
        ReportExport,
        ResearchTask,
        SourceDocument,
        SourceRevision,
        StructuredReport,
    )
    from tcm_platform.report_export import process_next_report_export
    from tcm_platform.research_worker import run_next_research_job
    from tcm_platform.stop_service import WorkflowConfig

    # Reuse the same deterministic fake responses as the backend integration tests.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_research_integration import DebateGenerator, FakeEmbedder, FakeReranker

    def deny_cloud(*_args, **_kwargs):
        raise RuntimeError("cloud models are disabled in the browser E2E harness")

    cloud_models.research_model_for_version = deny_cloud
    cloud_models.cloud_clients_from_environment = deny_cloud

    with SessionLocal() as session:
        if session.scalar(text("SELECT version_num FROM alembic_version")) != SCHEMA_REVISION:
            raise RuntimeError("test database migrations are not current")
        runtime = session.get(KnowledgeRuntimeState, 1)
        if runtime is None or runtime.active_index_build_id is None:
            raise RuntimeError("test database requires published fixture knowledge")
        build = session.get(IndexBuild, runtime.active_index_build_id)
        vector = session.scalar(select(EmbeddingRecord).where(
            EmbeddingRecord.index_build_id == build.id))
        item = session.scalar(select(KnowledgeVersionItem).join(
            EvidenceRevision, EvidenceRevision.id == KnowledgeVersionItem.evidence_revision_id
        ).join(SourceRevision, SourceRevision.id == EvidenceRevision.source_revision_id
        ).join(SourceDocument, SourceDocument.id == SourceRevision.source_id).where(
            KnowledgeVersionItem.knowledge_version_id == build.knowledge_version_id,
            KnowledgeVersionItem.evidence_revision_id.is_not(None)
        ).order_by(SourceDocument.created_at.desc(), SourceDocument.id.desc()))
        if vector is None or item is None:
            raise RuntimeError("published fixture knowledge has no indexed evidence")
        embedder = FakeEmbedder(build.configuration["embedding_model"], vector.dimensions)
        reranker = (FakeReranker(build.configuration["rerank_model"])
                    if build.configuration.get("rerank_model") else None)
        evidence_id = item.evidence_revision_id
    provenance = trace_evidence(evidence_id)
    with SessionLocal() as session:
        source = session.get(SourceDocument, UUID(provenance["source_id"]))
        source_ref, source_title = source.public_id, source.title
    question = initial["prefix"] + " " + provenance["quote_text"]

    original_start = research_api.start_research_task

    def start_with_review(task_id, **kwargs):
        # Freeze mandatory review at the normal service boundary, before any run.
        # Do not mutate a frozen context or manufacture persisted review records.
        kwargs["workflow_config"] = WorkflowConfig(mandatory_human_review=True)
        return original_start(task_id, **kwargs)

    research_api.start_research_task = start_with_review

    class BrowserGenerator(DebateGenerator):
        model_version = "siliconflow/test-cloud-structured-v1"

    def emit(value):
        print(json.dumps(value, ensure_ascii=False), flush=True)

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=18063,
                                          log_level="warning", access_log=False))

    def controls():
        try:
            for line in sys.stdin:
                command = json.loads(line)
                try:
                    with SessionLocal() as session:
                        task = session.scalar(select(ResearchTask).where(
                            ResearchTask.question == question))
                        if task is None:
                            raise RuntimeError("the browser has not created this run's task")
                        task_id = task.id
                    if command["action"] == "research":
                        job = run_next_research_job(
                            worker_id="vib63-browser", task_id=task_id,
                            model=BrowserGenerator(), embedder=embedder, reranker=reranker)
                        if job is None:
                            raise RuntimeError("no runnable job for the browser task")
                    elif command["action"] == "export":
                        with SessionLocal() as session:
                            export_id = session.scalar(select(ReportExport.id).join(
                                StructuredReport, ReportExport.report_id == StructuredReport.id
                            ).where(StructuredReport.task_id == task_id,
                                    ReportExport.file_format == command["format"]))
                        if export_id is None or process_next_report_export(
                                export_id=export_id, worker_id="vib63-browser-export") is None:
                            raise RuntimeError("no runnable export for the browser task")
                    else:
                        raise RuntimeError("unknown Worker command")
                    with SessionLocal() as session:
                        invocations = list(session.scalars(select(ModelInvocation).where(
                            ModelInvocation.task_id == task_id)))
                        if any(row.endpoint is not None
                               or row.model_version != BrowserGenerator.model_version
                               for row in invocations):
                            raise RuntimeError("unexpected real model route during E2E")
                        task = session.get(ResearchTask, task_id)
                        emit({"id": command["id"], "status": task.status,
                              "fake_invocations": len(invocations), "real_calls": 0})
                except Exception as exc:  # noqa: BLE001 - report failure to the parent runner.
                    emit({"id": command["id"], "error": str(exc)})
        finally:
            server.should_exit = True

    thread = threading.Thread(target=controls, daemon=True)
    thread.start()
    emit({"ready": True, "database": "tcm_vib60_test", "source_id": source_ref,
          "source_title": source_title, "question": question, "quote": provenance["quote_text"],
          "model_version": BrowserGenerator.model_version, "real_calls": 0})
    server.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forward", action="store_true")
    args = parser.parse_args()
    if args.forward:
        forward()
    else:
        serve()
