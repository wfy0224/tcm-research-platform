import pytest

from tcm_platform.publication_config import publication_configuration, validate_local_configuration


def test_local_configuration_contains_no_model_routes(monkeypatch):
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "LOCAL_ONLY")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "must-never-appear")
    config = publication_configuration()
    assert config["mode"] == "LOCAL_ONLY"
    assert config["configuration"]["strategy"] == "local-fts-exact-v1"
    assert "vector" not in config["channels"]
    assert "must-never-appear" not in str(config)
    validate_local_configuration(config["configuration"])
    with pytest.raises(ValueError, match="local publication"):
        validate_local_configuration({**config["configuration"], "embedding_model": "fake/model"})


def test_cloud_configuration_exposes_route_without_reading_credentials(monkeypatch):
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "CLOUD_ALLOWED")
    monkeypatch.setenv("TCM_PUBLICATION_STRATEGY", "hybrid-rrf-v1")
    monkeypatch.setenv("TCM_MODEL_PROVIDER", "siliconflow")
    monkeypatch.setenv("TCM_EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("TCM_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    config = publication_configuration()
    assert config["configuration"]["embedding_model"] == "siliconflow/BAAI/bge-m3"
    assert config["configuration"]["embedding_endpoint"] == "https://api.siliconflow.cn/v1/embeddings"


def test_cloud_generation_permission_does_not_require_vector_index(monkeypatch):
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "CLOUD_ALLOWED")
    monkeypatch.delenv("TCM_PUBLICATION_STRATEGY", raising=False)
    config = publication_configuration()
    assert config["mode"] == "CLOUD_ALLOWED"
    assert config["configuration"]["strategy"] == "local-fts-exact-v1"
    assert config["configuration"]["embedding_model"] is None
