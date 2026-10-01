"""Run the real workspace API and Workers against a dedicated demonstration database.

Linux test runtime only. Development sessions connect automatically without a code.
No model doubles, automatic knowledge approval, or preloaded business data are used.
"""

import argparse
import json
import os
import re
import select
import socket
import socketserver
import sys
import threading
from pathlib import Path

PORT = 18068
ORIGIN = "http://127.0.0.1:18067"
UPSTREAM_HOST = "workspace-api"


def forward():
    class Relay(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.create_connection((UPSTREAM_HOST, PORT), timeout=10) as upstream:
                upstream.settimeout(None)
                while True:
                    readable, _, _ = select.select([self.request, upstream], [], [], 1)
                    for source in readable:
                        value = source.recv(65536)
                        if not value:
                            return
                        (upstream if source is self.request else self.request).sendall(value)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("0.0.0.0", PORT), Relay) as server:
        server.serve_forever()


def serve(database: str):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    if not re.fullmatch(r"tcm_vib62_[a-z0-9_]+_test", database):
        raise RuntimeError("only a dedicated tcm_vib62_*_test database is allowed")
    inherited = make_url(os.environ["TCM_DATABASE_URL"])
    if not inherited.database.startswith("tcm_") or not inherited.database.endswith("_test"):
        raise RuntimeError("refusing credentials from a business or preview database")
    admin = create_engine(inherited.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}):
                connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
    finally:
        admin.dispose()
    os.environ["TCM_DATABASE_URL"] = inherited.set(database=database).render_as_string(hide_password=False)
    os.environ["TCM_DATA_ROOT"] = f"/tmp/{database}_store"
    os.environ["TCM_PREVIEW_CORPUS"] = "none"
    os.environ.setdefault("TCM_OUTBOUND_MODE", "LOCAL_ONLY")
    os.environ["TCM_LOCAL_ALLOWED_ORIGINS"] = ORIGIN
    os.environ["TCM_DEVELOPMENT_AUTO_SESSION"] = "true"
    Path(os.environ["TCM_DATA_ROOT"]).mkdir(parents=True, exist_ok=True)

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "head")

    import uvicorn

    from tcm_platform.knowledge_worker import process_next_knowledge_publish
    from tcm_platform.main import app
    from tcm_platform.report_export import process_next_report_export
    from tcm_platform.research_worker import run_next_research_job
    from tcm_platform.segment_service import process_next_segment
    from tcm_platform.source_import import process_next_import

    stop = threading.Event()
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT,
                                          log_level="warning", access_log=False))

    def workers():
        while not stop.is_set():
            for worker in (process_next_import, process_next_segment,
                           process_next_knowledge_publish, process_next_report_export):
                try:
                    worker(worker_id="workspace-demo")
                except Exception as exc:  # noqa: BLE001 - do not expose raw errors or secrets.
                    print(json.dumps({"worker": worker.__name__, "error_class": type(exc).__name__}),
                          file=sys.stderr, flush=True)
            if os.environ.get("TCM_RESEARCH_MODEL"):
                try:
                    run_next_research_job(worker_id="workspace-demo-research", embedder=None)
                except Exception as exc:  # noqa: BLE001 - no fake completion after failure.
                    print(json.dumps({"worker": "research", "error_class": type(exc).__name__}),
                          file=sys.stderr, flush=True)
            stop.wait(0.5)

    def controls():
        try:
            for line in sys.stdin:
                if json.loads(line).get("stop"):
                    break
        finally:
            stop.set()
            server.should_exit = True

    threading.Thread(target=workers, daemon=True).start()
    threading.Thread(target=controls, daemon=True).start()
    print(json.dumps({"ready": True, "database": database, "model_doubles": False,
                      "outbound_mode": os.environ["TCM_OUTBOUND_MODE"]}), flush=True)
    try:
        server.run()
    finally:
        stop.set()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forward", action="store_true")
    parser.add_argument("--database", default="tcm_vib62_workspace_test")
    parser.add_argument("--port", type=int, default=18068)
    parser.add_argument("--origin", default="http://127.0.0.1:18067")
    parser.add_argument("--upstream-host", default="workspace-api")
    arguments = parser.parse_args()
    PORT, ORIGIN, UPSTREAM_HOST = arguments.port, arguments.origin, arguments.upstream_host
    forward() if arguments.forward else serve(arguments.database)
