"""Offline checks: configuration responses and runtime routes never call models."""
from unittest.mock import patch

from tcm_platform import cloud_models, research_model_settings
from tcm_platform.model_configuration import legacy_configuration


def configuration():
    return {"models": ["deepseek/deepseek-flash"], "default_model": "deepseek/deepseek-flash",
            "api_keys": {"deepseek": "test-secret"}, "retrieval_provider": "siliconflow",
            "embedding_model": "BAAI/bge-m3", "rerank_model": "BAAI/bge-reranker-v2-m3",
            "workspace_id": "", "region": "cn-beijing"}


def test_response_never_exposes_credentials():
    with patch.object(research_model_settings, "read_model_settings", return_value=configuration()):
        response = research_model_settings._response()
    assert "test-secret" not in str(response)
    assert "api_keys" not in response
    assert response["providers"][0]["credential_configured"] is True


def test_runtime_uses_database_credential_and_default():
    with patch("tcm_platform.model_configuration.read_configuration", return_value=configuration()):
        model = cloud_models.research_model_from_environment()
    assert model.model_version == "deepseek/deepseek-flash"
    assert model.api_key == "test-secret"


def test_legacy_environment_keys_require_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr("tcm_platform.model_configuration.settings.data_root", tmp_path)
    monkeypatch.delenv("TCM_ALLOW_ENV_API_KEYS", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "do-not-import")
    with patch("tcm_platform.model_credentials.read_model_key", return_value=None):
        assert legacy_configuration()["api_keys"]["deepseek"] == ""
        monkeypatch.setenv("TCM_ALLOW_ENV_API_KEYS", "1")
        assert legacy_configuration()["api_keys"]["deepseek"] == "do-not-import"
