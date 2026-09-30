import secrets
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from tcm_platform import main as main_module
from tcm_platform.api_contract import (
    Actor,
    ApiError,
    accepted_job_response,
    enqueue_actor_job,
    etag_for,
    require_if_match,
    required_idempotency_key,
    resolve_public_id,
)
from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.enums import ResourceClass
from tcm_platform.jobs import enqueue_job
from tcm_platform.main import app
from tcm_platform.models import LocalSession, TaskJob, utc_now

ORIGIN = "http://127.0.0.1:5173"


def _client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_retrieval_query_uses_local_path_without_remote_consent(monkeypatch):
    clients_created = []
    def clients():
        clients_created.append(True)
        return object(), object()
    monkeypatch.setattr(main_module, "cloud_clients_from_environment", clients)

    def fake_search(query, *, query_outbound_authorized, **kwargs):
        assert (kwargs["embedder"] is not None) == query_outbound_authorized
        return []

    monkeypatch.setattr(main_module, "search_published", fake_search)
    with _client() as client:
        local = client.get("/api/v1/retrieval/search", params={"query": "太阳病"})
        assert local.status_code == 200 and local.json() == []
        assert not clients_created
        allowed = client.get("/api/v1/retrieval/search", params={
            "query": "太阳病", "allow_remote_query": "true",
        })
        assert allowed.status_code == 200 and allowed.json() == []
        assert clients_created == [True]


def test_one_use_bootstrap_cookie_csrf_origin_and_revocation(monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))
    with _client() as client:
        invalid_origin = client.post("/api/v1/local-session/bootstrap",
                                     headers={"Origin": "http://evil.example"},
                                     json={"bootstrap_secret": secret})
        assert invalid_origin.status_code == 403
        assert invalid_origin.json()["code"] == "ORIGIN_DENIED"
        assert invalid_origin.json()["request_id"] == invalid_origin.headers["X-Request-ID"]

        invalid_shape = client.post("/api/v1/local-session/bootstrap",
                                    headers={"Origin": ORIGIN},
                                    json={"bootstrap_secret": secret, "role": "admin"})
        assert invalid_shape.status_code == 422
        assert invalid_shape.json()["code"] == "INVALID_REQUEST"

        bootstrap = client.post("/api/v1/local-session/bootstrap",
                                headers={"Origin": ORIGIN},
                                json={"bootstrap_secret": secret})
        assert bootstrap.status_code == 200
        cookie = bootstrap.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert bootstrap.headers["Cache-Control"] == "no-store"
        assert secret not in str(bootstrap.json())
        csrf = bootstrap.json()["csrf_token"]
        assert csrf and bootstrap.json()["session_id"].startswith("LS-")

        repeated = client.post("/api/v1/local-session/bootstrap",
                               headers={"Origin": ORIGIN},
                               json={"bootstrap_secret": secret})
        assert repeated.status_code == 401
        assert repeated.json()["code"] == "INVALID_BOOTSTRAP"

        shown = client.get("/api/v1/local-session")
        assert shown.status_code == 200
        assert shown.json()["csrf_token"] is None
        assert shown.json()["session_id"] == bootstrap.json()["session_id"]
        version = shown.headers["ETag"]
        with SessionLocal.begin() as session:
            job = enqueue_job(session, idempotency_key=f"api-test:{secrets.token_hex(12)}",
                              job_type="test.local.api", payload={"sample": True},
                              resource_class=ResourceClass.IO, actor_id="local-owner")
            job_public_id, job_internal_id = job.public_id, job.id
        job_response = client.get(f"/api/v1/jobs/{job_public_id}")
        assert job_response.status_code == 200
        assert job_response.json()["job_id"] == job_public_id
        assert str(job_internal_id) not in str(job_response.json())
        assert client.get(f"/api/v1/jobs/{job_internal_id}").status_code == 404

        no_csrf = client.delete("/api/v1/local-session",
                                headers={"Origin": ORIGIN, "If-Match": version})
        assert no_csrf.status_code == 403
        assert no_csrf.json()["code"] == "CSRF_REQUIRED"
        bad_origin = client.delete("/api/v1/local-session",
                                   headers={"Origin": "http://evil.example",
                                            "X-CSRF-Token": csrf, "If-Match": version})
        assert bad_origin.status_code == 403
        assert bad_origin.json()["code"] == "ORIGIN_DENIED"
        conflict = client.delete("/api/v1/local-session",
                                 headers={"Origin": ORIGIN, "X-CSRF-Token": csrf,
                                          "If-Match": '"stale"'})
        assert conflict.status_code == 412
        assert conflict.json()["code"] == "VERSION_CONFLICT"
        deleted = client.delete("/api/v1/local-session",
                                headers={"Origin": ORIGIN, "X-CSRF-Token": csrf,
                                         "If-Match": version})
        assert deleted.status_code == 204
        assert client.get("/api/v1/local-session").status_code == 401


def test_host_and_expired_session_are_rejected(monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))
    with TestClient(app, base_url="http://not-loopback.example") as outside:
        response = outside.get("/api/v1/system/health")
        assert response.status_code == 403
        assert response.json()["code"] == "LOOPBACK_REQUIRED"
    with _client() as client:
        bootstrap = client.post("/api/v1/local-session/bootstrap",
                                headers={"Origin": ORIGIN},
                                json={"bootstrap_secret": secret})
        assert bootstrap.status_code == 200
        session_id = bootstrap.json()["session_id"]
        with SessionLocal.begin() as session:
            row = session.scalar(select(LocalSession).where(LocalSession.public_id == session_id))
            row.expires_at = utc_now() - timedelta(seconds=1)
        expired = client.get("/api/v1/local-session")
        assert expired.status_code == 401
        assert expired.json()["code"] == "SESSION_REQUIRED"


def test_actor_job_public_reference_idempotency_and_preconditions():
    actor = Actor("local-owner", "LS-test", "token-hash", "csrf-hash",
                  frozenset({"jobs.read", "jobs.write"}), 1, utc_now() + timedelta(hours=1))
    denied = Actor("reader", "LS-reader", "token-hash", "csrf-hash",
                   frozenset({"jobs.read"}), 1, utc_now() + timedelta(hours=1))
    with SessionLocal.begin() as session:
        with pytest.raises(ApiError) as error:
            enqueue_actor_job(session, actor=denied, capability="jobs.write",
                              idempotency_key="command-1", job_type="test.api.contract",
                              payload={"value": 1}, resource_class=ResourceClass.IO)
        assert error.value.code == "CAPABILITY_DENIED"
        key = secrets.token_hex(12)
        job = enqueue_actor_job(session, actor=actor, capability="jobs.write",
                                idempotency_key=key,
                                job_type="test.api.contract", payload={"value": 1},
                                resource_class=ResourceClass.IO)
        repeated = enqueue_actor_job(session, actor=actor, capability="jobs.write",
                                     idempotency_key=key, job_type="test.api.contract",
                                     payload={"value": 1}, resource_class=ResourceClass.IO)
        assert repeated.id == job.id
        with pytest.raises(ApiError) as error:
            enqueue_actor_job(session, actor=actor, capability="jobs.write",
                              idempotency_key=key, job_type="test.api.contract",
                              payload={"value": 2}, resource_class=ResourceClass.IO)
        assert error.value.code == "IDEMPOTENCY_CONFLICT"
        assert job.public_id.startswith("JOB-")
        assert str(job.id) not in job.public_id
        public_id, internal_id = job.public_id, job.id

    with SessionLocal.begin() as session:
        assert resolve_public_id(session, "job", public_id, actor) == internal_id
        for kind, value in (("job", str(internal_id)), ("research_task", public_id)):
            with pytest.raises(ApiError) as error:
                resolve_public_id(session, kind, value, actor)
            assert error.value.code in {"RESOURCE_NOT_FOUND", "CAPABILITY_DENIED"}
        with pytest.raises(ApiError) as error:
            resolve_public_id(session, "job", public_id, Actor(
                "none", "LS-none", "token", "csrf", frozenset(), 1,
                utc_now() + timedelta(hours=1)))
        assert error.value.code == "CAPABILITY_DENIED"
        job = session.scalar(select(TaskJob).where(TaskJob.public_id == public_id))
        accepted = accepted_job_response(job)
        assert accepted.status_code == 202
        assert accepted.headers["Location"] == f"/api/v1/jobs/{public_id}"
        assert str(internal_id) not in accepted.body.decode()

    assert required_idempotency_key("valid:key_1") == "valid:key_1"
    with pytest.raises(ApiError, match="Idempotency-Key"):
        required_idempotency_key("bad key")
    tag = etag_for(public_id, 1)
    require_if_match(tag, public_id, 1)
    with pytest.raises(ApiError) as error:
        require_if_match(None, public_id, 1)
    assert error.value.status == 428
    with pytest.raises(ApiError) as error:
        require_if_match(tag, public_id, 2)
    assert error.value.status == 412
