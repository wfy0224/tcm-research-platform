"""Run demo regressions only in a newly created Linux test database."""
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

inherited = make_url(os.environ["TCM_DATABASE_URL"])
if not inherited.database.startswith("tcm_") or not inherited.database.endswith("_test"):
    raise RuntimeError("refusing non-test database credentials")
database = f"tcm_demo_repairs_{uuid4().hex[:8]}_test"
admin = create_engine(inherited.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
admin.dispose()
os.environ["TCM_DATABASE_URL"] = inherited.set(database=database).render_as_string(hide_password=False)
os.environ["TCM_DATA_ROOT"] = f"/tmp/{database}_store"
os.environ["TCM_OUTBOUND_MODE"] = "LOCAL_ONLY"

import pytest
from alembic import command
from alembic.config import Config

backend = Path(__file__).resolve().parents[1]
os.chdir(backend)
config = Config(str(backend / "alembic.ini"))
config.set_main_option("script_location", str(backend / "migrations"))
command.upgrade(config, "head")
print(f"Isolated demonstration regressions: {database}", flush=True)
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "-rs",
    "tests/test_demo_repairs.py", "tests/test_parsing.py", "tests/test_segmentation.py",
    "tests/test_segmentation_integration.py", "tests/test_knowledge_workflow_api.py",
    "tests/test_knowledge_integration.py", "tests/test_knowledge_extraction_integration.py",
    "tests/test_formula_extraction_integration.py",
]))
