"""Safe, actionable job failures must never reflect exception text into the API."""

import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from tcm_platform.config import settings
from tcm_platform.db import SessionLocal
from tcm_platform.main import _job_failure_reason, app
from tcm_platform.models import TaskJob

SECRET = "sk-test-DO-NOT-EXPOSE-92741"
PRIVATE_URL = "https://private.invalid/request?token=confidential"


@pytest.mark.parametrize(("error", "action"), [
    ("ModelCredentialUnavailable", "联系管理员"),
    ("API_KEY is absent", "联系管理员"),
    ("remote model outbound is disabled", "外发授权"),
    ("source is not authorized", "外发授权"),
    ("ModelResponseError: invalid evidence protocol", "格式或引用校验"),
    ("JSON decode failed", "格式或引用校验"),
    ("TIMEOUT contacting provider", "按任务重试策略"),
    ("HTTP 503 service unavailable", "按任务重试策略"),
    ("knowledge version is not ready", "完成发布"),
    ("target index is incomplete", "完成发布"),
    ("unexpected internal exception", "核对来源、审核与模型配置"),
    ("ValueError: report narrative did not pass independent review after three drafts", "综合回答三稿"),
])
@pytest.mark.parametrize("status", ["FAILED", "RETRY_WAIT"])
def test_classifies_failure_without_exposing_exception(error, action, status):
    raw_error = f"{error}; private_details={SECRET}"
    reason = _job_failure_reason(TaskJob(status=status, last_error=raw_error))
    assert reason is not None and action in reason
    assert error not in reason and SECRET not in reason and PRIVATE_URL not in reason
    assert "Bearer" not in reason and "debug_url" not in reason


def test_raw_headers_urls_and_secret_values_are_never_reflected():
    reason = _job_failure_reason(TaskJob(status="FAILED", last_error=(
        f"provider failed: Authorization: Bearer {SECRET}; endpoint={PRIVATE_URL}; "
        'raw_body={"patient":"confidential"}')))
    assert reason is not None
    assert SECRET not in reason and PRIVATE_URL not in reason
    assert "Authorization" not in reason and "confidential" not in reason


@pytest.mark.parametrize("status", ["PENDING", "LEASED", "RUNNING", "COMPLETED", "CANCELLED"])
def test_nonfailure_status_never_exposes_stale_last_error(status):
    assert _job_failure_reason(TaskJob(status=status, last_error=f"timeout {SECRET}")) is None


@pytest.mark.parametrize("status", ["FAILED", "RETRY_WAIT"])
@pytest.mark.parametrize("last_error", [None, ""])
def test_no_failure_reason_without_an_error(status, last_error):
    assert _job_failure_reason(TaskJob(status=status, last_error=last_error)) is None


def test_job_http_projection_does_not_leak_stored_error(monkeypatch):
    with SessionLocal() as session:
        database = session.scalar(text("SELECT current_database()"))
        assert database.startswith("tcm_") and database.endswith("_test"), database
    bootstrap_secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(bootstrap_secret))
    with SessionLocal.begin() as session:
        job = TaskJob(idempotency_key=f"safe-reason:{secrets.token_hex(16)}",
                      job_type="knowledge.publish", resource_class="CPU", status="RETRY_WAIT",
                      attempts=1, max_attempts=3,
                      last_error=f"Connection timeout {SECRET} {PRIVATE_URL}",
                      payload={"private_details": SECRET})
        session.add(job)
        session.flush()
        public_id = job.public_id
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get(f"/api/v1/jobs/{public_id}").status_code == 401
        bootstrap = client.post("/api/v1/local-session/bootstrap",
                                headers={"Origin": "http://127.0.0.1:5173"},
                                json={"bootstrap_secret": bootstrap_secret})
        assert bootstrap.status_code == 200
        response = client.get(f"/api/v1/jobs/{public_id}")
        assert response.status_code == 200, response.text
        assert "按任务重试策略" in response.json()["failure_reason"]
        assert SECRET not in response.text and PRIVATE_URL not in response.text
        assert "last_error" not in response.json() and "payload" not in response.json()
        with SessionLocal.begin() as session:
            job = session.scalar(text("SELECT id FROM runtime.task_job WHERE public_id=:id"),
                                 {"id": public_id})
            session.get(TaskJob, job).status = "COMPLETED"
        completed = client.get(f"/api/v1/jobs/{public_id}")
        assert completed.status_code == 200
        assert completed.json()["failure_reason"] is None
        assert SECRET not in completed.text and PRIVATE_URL not in completed.text
