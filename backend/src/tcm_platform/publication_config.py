"""Public publication routes, read without loading any model credential."""

import os
import re

from tcm_platform.outbound_policy import current_mode

LOCAL_STRATEGY = "local-fts-exact-v1"


def is_local_configuration(configuration: dict) -> bool:
    return configuration.get("strategy") == LOCAL_STRATEGY


def validate_local_configuration(configuration: dict) -> None:
    if not is_local_configuration(configuration) or any(configuration.get(key) is not None for key in (
        "embedding_model", "rerank_model", "embedding_endpoint", "rerank_endpoint",
    )):
        raise ValueError("local publication must not configure a vector model or remote route")


def publication_configuration() -> dict:
    mode = current_mode()
    strategy = os.getenv("TCM_PUBLICATION_STRATEGY", LOCAL_STRATEGY)
    if strategy not in {LOCAL_STRATEGY, "hybrid-rrf-v1"}:
        raise ValueError("TCM_PUBLICATION_STRATEGY must be local-fts-exact-v1 or hybrid-rrf-v1")
    configuration = {"strategy": LOCAL_STRATEGY, "embedding_model": None, "rerank_model": None,
                     "embedding_endpoint": None, "rerank_endpoint": None}
    if strategy == "hybrid-rrf-v1":
        if mode != "CLOUD_ALLOWED":
            raise ValueError("hybrid publication requires CLOUD_ALLOWED outbound policy")
        provider = os.getenv("TCM_MODEL_PROVIDER", "siliconflow").lower()
        if provider == "siliconflow":
            configuration = {
                "strategy": "hybrid-rrf-v1",
                "embedding_model": "siliconflow/" + os.getenv("TCM_EMBEDDING_MODEL", "BAAI/bge-m3"),
                "rerank_model": "siliconflow/" + os.getenv("TCM_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
                "embedding_endpoint": "https://api.siliconflow.cn/v1/embeddings",
                "rerank_endpoint": "https://api.siliconflow.cn/v1/rerank",
            }
        elif provider == "aliyun":
            workspace = os.getenv("TCM_DASHSCOPE_WORKSPACE_ID", "")
            region = os.getenv("TCM_DASHSCOPE_REGION", "cn-beijing")
            if any(not re.fullmatch(r"[a-zA-Z0-9_-]+", value) for value in (workspace, region)):
                raise ValueError("DashScope workspace ID and region must be configured")
            host = f"https://{workspace}.{region}.maas.aliyuncs.com"
            configuration = {
                "strategy": "hybrid-rrf-v1",
                "embedding_model": "aliyun/" + os.getenv("TCM_EMBEDDING_MODEL", "qwen3.7-text-embedding"),
                "rerank_model": "aliyun/" + os.getenv("TCM_RERANK_MODEL", "qwen3.7-text-rerank"),
                "embedding_endpoint": f"{host}/compatible-mode/v1/embeddings",
                "rerank_endpoint": f"{host}/api/v1/services/rerank/text-rerank/text-rerank",
            }
        else:
            raise ValueError("TCM_MODEL_PROVIDER must be aliyun or siliconflow")
    return {"mode": mode, "configuration": configuration,
            "channels": ["exact", "fts", "structured", "relation"]
            + (["vector", "rerank"] if strategy == "hybrid-rrf-v1" else [])}
