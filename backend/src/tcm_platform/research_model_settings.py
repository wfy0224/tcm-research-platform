"""Manage database-backed models without exposing provider secrets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from tcm_platform.api_contract import Actor, ApiError
from tcm_platform.cloud_models import CloudResearchModel
from tcm_platform.local_auth import COOKIE_NAME, current_actor, require_csrf

router = APIRouter(prefix="/api/v1/research", tags=["research"])
PROVIDERS = {"deepseek": "DeepSeek 官方", "siliconflow": "硅基流动"}


class ModelSettingsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    models: list[str] = Field(max_length=100)
    default_model: str = Field(default="", max_length=200)
    api_keys: dict[str, str] = Field(default_factory=dict)
    retrieval_provider: str = Field(default="siliconflow", pattern="^(siliconflow|aliyun)$")
    embedding_model: str = Field(default="BAAI/bge-m3", min_length=1, max_length=200)
    rerank_model: str = Field(default="BAAI/bge-reranker-v2-m3", min_length=1, max_length=200)
    workspace_id: str = Field(default="", max_length=200)
    region: str = Field(default="cn-beijing", min_length=1, max_length=100)


def read_model_settings() -> dict:
    from tcm_platform.model_configuration import read_configuration
    return read_configuration()


def model_choices(routes: list) -> list[dict]:
    choices = []
    seen = set()
    for route in routes:
        try:
            if not isinstance(route, str) or len(route) > 200 or any(char.isspace() for char in route):
                continue
            provider, separator, name = route.partition("/")
            if not separator:
                continue
            model = CloudResearchModel(provider=provider, model=name, api_key="")
        except ValueError:
            continue
        if model.model_version in seen:
            continue
        seen.add(model.model_version)
        choices.append({"model_version": model.model_version,
                        "label": f"{PROVIDERS[model.provider]} · {model.model}"})
    return choices


def _actor(request: Request) -> Actor:
    actor = current_actor(request.cookies.get(COOKIE_NAME))
    actor.require("research.read")
    return actor


def _response() -> dict:
    payload = read_model_settings()
    return {"models": model_choices(payload["models"]), "default_model": payload["default_model"],
            **{key: payload[key] for key in ("retrieval_provider", "embedding_model", "rerank_model", "workspace_id", "region")},
            "providers": [{"id": provider, "label": label,
                           "credential_configured": bool(payload.get("api_keys", {}).get(provider))}
                          for provider, label in {**PROVIDERS, "aliyun": "阿里云"}.items()]}

@router.get("/model-settings")
def get_model_settings(actor: Annotated[Actor, Depends(_actor)]) -> dict:
    return _response()


@router.post("/model-settings")
def save_model_settings(payload: ModelSettingsRequest, request: Request,
                        actor: Annotated[Actor, Depends(_actor)]) -> dict:
    actor.require("research.write")
    require_csrf(actor, request.headers.get("X-CSRF-Token"))
    if any(provider not in {"deepseek", "siliconflow", "aliyun"} or len(key) > 4096 or any(c.isspace() for c in key) for provider, key in payload.api_keys.items()):
        raise ApiError("INVALID_REQUEST", status=400, category="validation", detail="API 密钥格式无效。")
    choices = model_choices(payload.models)
    if len(choices) != len(payload.models) or (payload.default_model and
            payload.default_model not in {choice["model_version"] for choice in choices}):
        raise ApiError("INVALID_REQUEST", status=400, category="validation",
                       detail="请使用支持的提供商和模型名称，默认模型须在列表中，不能重复添加。")
    from tcm_platform.model_configuration import save_configuration
    save_configuration(payload.model_dump(exclude_unset=True))
    return _response()
