"""Development connection removes code entry while retaining real session checks."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.main import app
from tcm_platform.models import LocalSession, utc_now

ORIGIN = "http://127.0.0.1:5173"
PATH = "/api/v1/local-session/development"


def test_development_connection_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "development_auto_session", False)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        config = client.get("/api/v1/local-session/config")
        assert config.json() == {"development_auto_session": False}
        assert config.headers["Cache-Control"] == "no-store"
        denied = client.post(PATH, headers={"Origin": ORIGIN})
        assert denied.status_code == 404
        assert denied.json()["code"] == "DEVELOPMENT_SESSION_DISABLED"
        assert "set-cookie" not in denied.headers
        assert client.get("/api/v1/local-session").status_code == 401


def test_development_connection_without_secret_keeps_origin_and_csrf(monkeypatch):
    monkeypatch.setattr(settings, "development_auto_session", True)
    monkeypatch.setattr(settings, "bootstrap_secret", None)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/v1/local-session/config").json()["development_auto_session"]
        for origin in (None, "http://evil.example"):
            headers = {"Origin": origin} if origin else {}
            denied = client.post(PATH, headers=headers)
            assert denied.status_code == 403
            assert denied.json()["code"] == "ORIGIN_DENIED"
        connected = client.post(PATH, headers={"Origin": ORIGIN})
        assert connected.status_code == 200
        assert connected.headers["Cache-Control"] == "no-store"
        assert "HttpOnly" in connected.headers["set-cookie"]
        assert "SameSite=strict" in connected.headers["set-cookie"]
        token = connected.json()["csrf_token"]
        shown = client.get("/api/v1/local-session")
        assert shown.status_code == 200
        assert shown.json()["csrf_token"] is None
        assert "knowledge.write" in shown.json()["capabilities"]
        assert "research.write" in shown.json()["capabilities"]
        assert client.get("/api/v1/knowledge/sources").status_code == 200
        # Another tab can obtain CSRF without replacing the shared Cookie or first tab's CSRF.
        second = client.post(PATH, headers={"Origin": ORIGIN})
        assert second.json()["session_id"] == connected.json()["session_id"]
        assert second.json()["csrf_token"] == token
        headers = {"Origin": ORIGIN, "If-Match": shown.headers["ETag"]}
        assert client.delete("/api/v1/local-session", headers=headers).status_code == 403
        headers["X-CSRF-Token"] = "wrong-token"
        assert client.delete("/api/v1/local-session", headers=headers).status_code == 403
        headers["X-CSRF-Token"] = token
        assert client.delete("/api/v1/local-session", headers=headers).status_code == 204
        assert client.get("/api/v1/local-session").status_code == 401
        renewed = client.post(PATH, headers={"Origin": ORIGIN})
        assert renewed.status_code == 200
        assert renewed.json()["session_id"] != connected.json()["session_id"]


def test_development_connection_renews_expired_session(monkeypatch):
    monkeypatch.setattr(settings, "development_auto_session", True)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        connected = client.post(PATH, headers={"Origin": ORIGIN})
        with SessionLocal.begin() as session:
            row = session.scalar(select(LocalSession).where(
                LocalSession.public_id == connected.json()["session_id"]))
            row.expires_at = utc_now() - timedelta(seconds=1)
        assert client.get("/api/v1/local-session").status_code == 401
        renewed = client.post(PATH, headers={"Origin": ORIGIN})
        assert renewed.status_code == 200
        assert renewed.json()["session_id"] != connected.json()["session_id"]


def test_development_connection_still_requires_loopback(monkeypatch):
    monkeypatch.setattr(settings, "development_auto_session", True)
    with TestClient(app, base_url="http://outside.example") as client:
        denied = client.post(PATH, headers={"Origin": ORIGIN})
        assert denied.status_code == 403
        assert denied.json()["code"] == "LOOPBACK_REQUIRED"
