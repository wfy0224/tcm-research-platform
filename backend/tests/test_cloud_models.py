from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from tcm_platform import cloud_models


def test_aliyun_cloud_clients_use_one_workspace_key(monkeypatch):
    monkeypatch.setenv("TCM_ALLOW_ENV_API_KEYS", "1")
    monkeypatch.setattr(cloud_models, "_credential", lambda provider: "unit-test-key")
    monkeypatch.setattr(cloud_models, "require_outbound", lambda operation, model: None)
    monkeypatch.setenv("TCM_MODEL_PROVIDER", "aliyun")
    monkeypatch.setenv("TCM_DASHSCOPE_WORKSPACE_ID", "test-workspace")
    monkeypatch.setenv("TCM_DASHSCOPE_REGION", "cn-beijing")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "unit-test-key")
    embedder, reranker = cloud_models.cloud_clients_from_environment()
    assert embedder.model_version == "aliyun/qwen3.7-text-embedding"
    assert reranker.model_version == "aliyun/qwen3.7-text-rerank"
    assert embedder.endpoint.endswith("/compatible-mode/v1/embeddings")
    assert reranker.endpoint.endswith("/api/v1/services/rerank/text-rerank/text-rerank")

    captured = []

    def fake_post(url, key, payload):
        captured.append((url, key, payload))
        if "embeddings" in url:
            return {"data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]}
        return {"output": {"results": [
            {"index": 1, "relevance_score": 0.8},
            {"index": 0, "relevance_score": 0.2},
        ]}}

    monkeypatch.setattr(cloud_models, "_post_json", fake_post)
    assert embedder.embed(["太阳", "阳明"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert reranker.rerank("太阳", ["太阳病", "阳明病"]) == [(1, 0.8), (0, 0.2)]
    assert all(key == "unit-test-key" for _, key, _ in captured)
    assert captured[1][2]["input"]["query"] == "太阳"


def test_siliconflow_models_and_endpoint_guard(monkeypatch):
    monkeypatch.setenv("TCM_ALLOW_ENV_API_KEYS", "1")
    monkeypatch.setattr(cloud_models, "_credential", lambda provider: "unit-test-key")
    monkeypatch.setenv("TCM_MODEL_PROVIDER", "siliconflow")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "unit-test-key")
    embedder, reranker = cloud_models.cloud_clients_from_environment()
    assert embedder.model_version == "siliconflow/BAAI/bge-m3"
    assert reranker.model_version == "siliconflow/BAAI/bge-reranker-v2-m3"
    with pytest.raises(ValueError, match="approved HTTPS"):
        cloud_models.CloudEmbedder(
            provider="siliconflow", model="BAAI/bge-m3",
            endpoint="https://api.siliconflow.cn.evil.example/v1/embeddings",
            api_key="unit-test-key",
        )
    with pytest.raises(ValueError, match="provider and operation"):
        cloud_models.CloudEmbedder(
            provider="siliconflow", model="BAAI/bge-m3",
            endpoint="https://api.deepseek.com/chat/completions",
            api_key="unit-test-key",
        )


def test_cloud_research_model_parses_json_without_leaking_key(monkeypatch):
    monkeypatch.setattr(cloud_models, "require_outbound", lambda operation, model: None)
    captured = []

    def fake_post(url, key, payload):
        captured.append((url, key, payload))
        return {"choices": [{"message": {"content": '{"subquestions":["脉象"]}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7}}

    monkeypatch.setattr(cloud_models, "_post_json", fake_post)
    model = cloud_models.CloudResearchModel(model="Qwen/Qwen3-8B", api_key="unit-test-key")
    assert model.complete_json("Return JSON", {"question": "太阳病"}) == {
        "subquestions": ["脉象"]
    }
    assert captured[0][0] == "https://api.siliconflow.cn/v1/chat/completions"
    assert captured[0][1] == "unit-test-key"
    assert captured[0][2]["response_format"] == {"type": "json_object"}
    assert captured[0][2]["enable_thinking"] is False
    assert model.complete_json_with_metadata("Return JSON", {"question": "太阳病"})[1] == {
        "prompt_tokens": 12, "completion_tokens": 7,
    }


def test_deepseek_research_route_uses_official_endpoint_and_frozen_model(monkeypatch):
    monkeypatch.setenv("TCM_ALLOW_ENV_API_KEYS", "1")
    monkeypatch.setattr(cloud_models, "_credential", lambda provider: "unit-test-deepseek-key")
    monkeypatch.setattr(cloud_models, "require_outbound", lambda operation, model: None)
    captured = []

    def fake_post(url, key, payload):
        captured.append((url, key, payload))
        return {"choices": [{"message": {"content": '{"claims":[]}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3}}

    monkeypatch.setattr(cloud_models, "_post_json", fake_post)
    monkeypatch.setenv("TCM_RESEARCH_PROVIDER", "deepseek")
    monkeypatch.setenv("TCM_RESEARCH_MODEL", "deepseek-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-test-deepseek-key")
    model = cloud_models.research_model_from_environment()
    assert model.model_version == "deepseek/deepseek-flash"
    assert model.complete_json("Return JSON", {"question": "太阳病"}) == {"claims": []}
    assert captured[0][0] == "https://api.deepseek.com/chat/completions"
    assert captured[0][1] == "unit-test-deepseek-key"
    assert captured[0][2]["thinking"] == {"type": "disabled"}
    assert cloud_models.research_model_for_version(
        "deepseek/deepseek-flash"
    ).model_version == model.model_version
    with pytest.raises(ValueError, match="approved HTTPS"):
        cloud_models._checked_endpoint("https://api.deepseek.com.evil.example/chat/completions")


def test_cloud_adapter_rejects_calls_without_outbound_scope(monkeypatch):
    monkeypatch.setenv("TCM_OUTBOUND_MODE", "CLOUD_ALLOWED")
    model = cloud_models.CloudResearchModel(model="Qwen/Qwen3-8B", api_key="unused")
    with pytest.raises(PermissionError, match="matching outbound authorization"):
        model.complete_json("prompt", {"question": "private text"})
    embedder = cloud_models.CloudEmbedder(
        provider="siliconflow", model="BAAI/bge-m3",
        endpoint="https://api.siliconflow.cn/v1/embeddings", api_key="unused",
    )
    with pytest.raises(PermissionError, match="matching outbound authorization"):
        embedder.embed(["private text"])
    reranker = cloud_models.CloudReranker(
        provider="siliconflow", model="BAAI/bge-reranker-v2-m3",
        endpoint="https://api.siliconflow.cn/v1/rerank", api_key="unused",
    )
    with pytest.raises(PermissionError, match="matching outbound authorization"):
        reranker.rerank("private query", ["private text"])


def test_oversized_request_is_rejected_before_network(monkeypatch):
    monkeypatch.setattr(cloud_models, "MAX_REQUEST_BYTES", 20)
    with pytest.raises(ValueError, match="size limit"):
        cloud_models._post_json("https://api.siliconflow.cn/v1/embeddings", "unused",
                                {"input": "x" * 100})


def test_keychain_is_required_unless_development_environment_switch_is_set(monkeypatch):
    monkeypatch.setattr(cloud_models, "read_model_key", lambda provider: None)
    monkeypatch.setenv("SILICONFLOW_API_KEY", "secret-for-test")
    monkeypatch.delenv("TCM_ALLOW_ENV_API_KEYS", raising=False)
    with pytest.raises(ValueError, match="OS keychain"):
        cloud_models._credential("siliconflow")
    monkeypatch.setenv("TCM_ALLOW_ENV_API_KEYS", "1")
    assert cloud_models._credential("siliconflow") == "secret-for-test"


def test_completion_format_retry_is_separate_and_usage_is_redacted(monkeypatch):
    monkeypatch.setattr(cloud_models, "require_outbound", lambda operation, model: None)
    responses = iter([
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": '{"claims":[]}'}}],
         "usage": {"total_tokens": 9, "private_note": "do not store"}},
    ])
    monkeypatch.setattr(cloud_models, "_post_json", lambda url, key, payload: next(responses))
    model = cloud_models.CloudResearchModel(model="Qwen/Qwen3-8B", api_key="unused")
    payload, usage = model.complete_json_with_metadata("prompt", {"question": "太阳病"})
    assert payload == {"claims": []}
    assert usage == {"total_tokens": 9, "format_retry_count": 1}


def test_transport_retry_and_circuit_are_bounded(monkeypatch):
    monkeypatch.setattr(cloud_models, "current_permit", lambda: SimpleNamespace(
        model_version="siliconflow/BAAI/bge-m3"))
    monkeypatch.setattr(cloud_models, "_record_start", lambda endpoint, digest: "test-call")
    monkeypatch.setattr(cloud_models, "_record_finish", lambda *args, **kwargs: None)
    monkeypatch.setattr(cloud_models, "_requests", {})
    monkeypatch.setattr(cloud_models, "_failures", {})
    monkeypatch.setattr(cloud_models, "_open_until", {})
    monkeypatch.setattr(cloud_models.time, "sleep", lambda delay: None)
    attempts = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, limit):
            return b'{"data":[]}'

    class Opener:
        def open(self, request, timeout):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise HTTPError(request.full_url, 429, "rate limit", {}, None)
            return Response()

    monkeypatch.setattr(cloud_models, "build_opener", lambda handler: Opener())
    endpoint = "https://api.siliconflow.cn/v1/embeddings"
    payload = {"model": "BAAI/bge-m3", "input": ["text"]}
    assert cloud_models._post_json(endpoint, "unit-test-key", payload) == {
        "data": []
    }
    assert attempts == 3

    class DownOpener:
        def open(self, request, timeout):
            raise URLError("private connection error")

    monkeypatch.setattr(cloud_models, "build_opener", lambda handler: DownOpener())
    for _ in range(3):
        with pytest.raises(RuntimeError, match="unreachable"):
            cloud_models._post_json(endpoint, "unit-test-key", payload)
    with pytest.raises(RuntimeError, match="circuit is open"):
        cloud_models._post_json(endpoint, "unit-test-key", payload)
