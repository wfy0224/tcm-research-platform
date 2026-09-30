"""The HTTP health contract must recognize the actual migrated schema head."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text

from tcm_platform.db import SessionLocal
from tcm_platform.main import app


def test_health_recognizes_latest_migrated_schema():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test")
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == head
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
    assert response.json()["schema"] == "current"
