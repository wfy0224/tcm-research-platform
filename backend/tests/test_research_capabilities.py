"""Capability discovery must not read secrets or send a model request."""

import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tcm_platform import cloud_models
from tcm_platform.config import settings
from tcm_platform.main import app

ORIGIN = "http://127.0.0.1:5173"
PATH = "/api/v1/research/capabilities"


@pytest.fixture
def capability_client(monkeypatch):
    secret = secrets.token_urlsafe(32)
    monkeypatch.setattr(settings, "bootstrap_secret", SecretStr(secret))

    def forbidden(*args, **kwargs):
        pytest.fail("capability discovery must not read credentials or call a model")

    monkeypatch.setattr(cloud_models, "_credential", forbidden)
    monkeypatch.setattr(cloud_models, "read_model_key", forbidden)
    monkeypatch.setattr(cloud_models, "_post_json", forbidden)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        issued = client.post("/api/v1/local-session/bootstrap",
                             headers={"Origin": ORIGIN},
                             json={"bootstrap_secret": secret})
        assert issued.status_code == 200, issued.text
        shown = client.get("/api/v1/local-session")
        assert shown.status_code == 200, shown.text
        yield client, {"Origin": ORIGIN,
                       "X-CSRF-Token": issued.json()["csrf_token"],
                       "If-Match": shown.headers["ETag"]}


def test_capability_discovery_requires_local_session():
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.get(PATH)
        assert response.status_code == 401


@pytest.mark.parametrize("model", [None, "", "   "])
def test_missing_model_reports_actionable_configuration_reason(
    capability_client, monkeypatch, model,
):
    if model is None:
        monkeypatch.delenv("TCM_RESEARCH_MODEL", raising=False)
    else:
        monkeypatch.setenv("TCM_RESEARCH_MODEL", model)
    client, _ = capability_client
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["models"] == []
    assert "模型设置" in response.json()["unavailable_reason"]


@pytest.mark.parametrize("provider,model", [
    ("unknown", "model"), ("deepseek", "unsupported-model"),
    ("siliconflow", " model "), ("siliconflow", "a" * 200),
])
def test_invalid_route_is_not_offered(capability_client, monkeypatch, provider, model):
    monkeypatch.setenv("TCM_RESEARCH_PROVIDER", provider)
    monkeypatch.setenv("TCM_RESEARCH_MODEL", model)
    client, _ = capability_client
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["models"] == []
    assert "配置无效" in response.json()["unavailable_reason"]


@pytest.mark.parametrize("provider,model", [
    ("siliconflow", "Qwen/Qwen3-8B"), ("deepseek", "deepseek-flash"),
])
def test_configured_route_is_offered_without_credentials_or_outbound(
    capability_client, monkeypatch, provider, model,
):
    monkeypatch.setenv("TCM_RESEARCH_PROVIDER", provider)
    monkeypatch.setenv("TCM_RESEARCH_MODEL", model)
    client, _ = capability_client
    response = client.get(PATH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["unavailable_reason"] is None
    assert len(payload["models"]) == 1
    assert payload["models"][0]["model_version"] == f"{provider}/{model}"
    assert set(payload["models"][0]) == {"model_version", "label"}


def test_revoked_session_cannot_discover_models(capability_client):
    client, headers = capability_client
    revoked = client.delete("/api/v1/local-session", headers=headers)
    assert revoked.status_code == 204, revoked.text
    assert client.get(PATH).status_code == 401
