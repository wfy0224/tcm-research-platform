import pytest

from tcm_platform import cloud_models


def test_aliyun_cloud_clients_use_one_workspace_key(monkeypatch):
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


def test_cloud_research_model_parses_json_without_leaking_key(monkeypatch):
    captured = []

    def fake_post(url, key, payload):
        captured.append((url, key, payload))
        return {"choices": [{"message": {"content": '{"subquestions":["脉象"]}'}}]}

    monkeypatch.setattr(cloud_models, "_post_json", fake_post)
    model = cloud_models.CloudResearchModel(model="Qwen/Qwen3-8B", api_key="unit-test-key")
    assert model.complete_json("Return JSON", {"question": "太阳病"}) == {
        "subquestions": ["脉象"]
    }
    assert captured[0][0] == "https://api.siliconflow.cn/v1/chat/completions"
    assert captured[0][1] == "unit-test-key"
    assert captured[0][2]["response_format"] == {"type": "json_object"}
    assert captured[0][2]["enable_thinking"] is False
