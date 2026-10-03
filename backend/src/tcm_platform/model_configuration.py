"""Database-backed model configuration shared by API and workers."""
import json
import os

from sqlalchemy.dialects.postgresql import insert

from tcm_platform.config import settings
from tcm_platform.db import session_scope
from tcm_platform.models import ModelConfiguration


def legacy_configuration() -> dict:
    path = settings.data_root / "research-model-settings.json"
    if path.exists():
        research = json.loads(path.read_text(encoding="utf-8"))
    else:
        routes = json.loads(os.getenv("TCM_RESEARCH_MODELS", "[]"))
        if not routes and os.getenv("TCM_RESEARCH_MODEL"):
            routes = [f'{os.getenv("TCM_RESEARCH_PROVIDER", "siliconflow")}/{os.environ["TCM_RESEARCH_MODEL"]}']
        research = {"models": routes, "default_model": ""}
    provider = os.getenv("TCM_MODEL_PROVIDER", "siliconflow")
    from tcm_platform.model_credentials import read_model_key
    keys = {}
    for name, env in {"deepseek": "DEEPSEEK_API_KEY", "siliconflow": "SILICONFLOW_API_KEY",
                      "aliyun": "DASHSCOPE_API_KEY"}.items():
        try:
            key = read_model_key(name)
        except (OSError, RuntimeError):
            key = None
        keys[name] = key or (os.getenv(env, "") if os.getenv("TCM_ALLOW_ENV_API_KEYS") == "1" else "")
    return {**research, "retrieval_provider": provider,
            "embedding_model": os.getenv("TCM_EMBEDDING_MODEL", "qwen3.7-text-embedding" if provider == "aliyun" else "BAAI/bge-m3"),
            "rerank_model": os.getenv("TCM_RERANK_MODEL", "qwen3.7-text-rerank" if provider == "aliyun" else "BAAI/bge-reranker-v2-m3"),
            "workspace_id": os.getenv("TCM_DASHSCOPE_WORKSPACE_ID", ""),
            "region": os.getenv("TCM_DASHSCOPE_REGION", "cn-beijing"),
            "api_keys": keys}


def read_configuration() -> dict:
    with session_scope() as session:
        row = session.get(ModelConfiguration, 1)
        if row is None:
            session.execute(insert(ModelConfiguration).values(id=1, payload=legacy_configuration())
                            .on_conflict_do_nothing(index_elements=["id"]))
            row = session.get(ModelConfiguration, 1)
        return dict(row.payload)


def save_configuration(payload: dict) -> None:
    read_configuration()
    with session_scope() as session:
        row = session.get(ModelConfiguration, 1, with_for_update=True)
        current = dict(row.payload)
        keys = dict(current.get("api_keys", {}))
        changes = dict(payload)
        for provider, key in changes.pop("api_keys", {}).items():
            if key:
                keys[provider] = key
        current.update(changes)
        current["api_keys"] = keys
        row.payload = current
