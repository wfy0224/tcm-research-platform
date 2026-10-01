"""Run session regression checks on a new isolated database in the Linux runtime."""

import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

inherited = make_url(os.environ["TCM_DATABASE_URL"])
if not inherited.database.startswith("tcm_") or not inherited.database.endswith("_test"):
    raise RuntimeError("refusing non-test database credentials")
database = f"tcm_development_session_{uuid4().hex[:8]}_test"
admin = create_engine(inherited.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
admin.dispose()
os.environ["TCM_DATABASE_URL"] = inherited.set(database=database).render_as_string(
    hide_password=False)
os.environ["TCM_DATA_ROOT"] = f"/tmp/{database}_store"
os.environ["TCM_DEVELOPMENT_AUTO_SESSION"] = "false"
os.environ["TCM_OUTBOUND_MODE"] = "LOCAL_ONLY"
os.environ["TCM_LOCAL_ALLOWED_ORIGINS"] = "http://127.0.0.1:5173,http://127.0.0.1:8000"

import pytest
from alembic import command
from alembic.config import Config

backend = Path(__file__).resolve().parents[1]
config = Config(str(backend / "alembic.ini"))
config.set_main_option("script_location", str(backend / "migrations"))
command.upgrade(config, "head")
print(f"Isolated session checks: {database}", flush=True)
raise SystemExit(pytest.main([
    "-q", "-p", "no:cacheprovider",
    "tests/test_development_session.py", "tests/test_local_api_integration.py",
    "tests/test_research_capabilities.py", "tests/test_job_failure_reason.py",
]))
