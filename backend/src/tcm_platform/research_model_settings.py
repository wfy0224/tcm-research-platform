"""Local, durable model choices. This catalog contains no credentials."""

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from tcm_platform.api_contract import Actor, ApiError
from tcm_platform.cloud_models import CloudResearchModel
from tcm_platform.config import settings
from tcm_platform.local_auth import COOKIE_NAME, current_actor, require_csrf

router = APIRouter(prefix="/api/v1/research", tags=["research"])
_lock = RLock()
PROVIDERS = {"deepseek": "DeepSeek 官方", "siliconflow": "硅基流动"}


class ModelSettingsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    models: list[str] = Field(max_length=100)
    default_model: str = Field(default="", max_length=200)


def _path() -> Path:
    return settings.data_root / "research-model-settings.json"


def read_model_settings() -> dict:
    with _lock:
        if _path().exists():
            try:
                payload = json.loads(_path().read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("invalid settings")
                return ModelSettingsRequest.model_validate(payload).model_dump()
            except (OSError, ValueError) as exc:
                raise ApiError("MODEL_SETTINGS_UNAVAILABLE", status=503, category="configuration",
                               detail="模型设置读取失败，请检查本地配置文件。") from exc
        catalog = os.getenv("TCM_RESEARCH_MODELS")
        if catalog is not None:
            try:
                routes = json.loads(catalog)
                if not isinstance(routes, list) or len(routes) > 100:
                    raise ValueError("invalid catalog")
            except ValueError:
                routes = []
        elif os.getenv("TCM_RESEARCH_MODEL", "").strip():
            routes = [f'{os.getenv("TCM_RESEARCH_PROVIDER", "siliconflow").lower()}/{os.getenv("TCM_RESEARCH_MODEL")}']
        else:
            routes = []
        return {"models": routes, "default_model": ""}


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
            "providers": [{"id": provider, "label": label,
                           "credential_configured": bool(os.getenv(
                               "DEEPSEEK_API_KEY" if provider == "deepseek" else "SILICONFLOW_API_KEY"))}
                          for provider, label in PROVIDERS.items()]}


@router.get("/model-settings")
def get_model_settings(actor: Annotated[Actor, Depends(_actor)]) -> dict:
    return _response()


@router.post("/model-settings")
def save_model_settings(payload: ModelSettingsRequest, request: Request,
                        actor: Annotated[Actor, Depends(_actor)]) -> dict:
    actor.require("research.write")
    require_csrf(actor, request.headers.get("X-CSRF-Token"))
    choices = model_choices(payload.models)
    if len(choices) != len(payload.models) or (payload.default_model and
            payload.default_model not in {choice["model_version"] for choice in choices}):
        raise ApiError("INVALID_REQUEST", status=400, category="validation",
                       detail="请使用支持的提供商和模型名称，默认模型须在列表中，不能重复添加。")
    with _lock:
        temporary = None
        try:
            _path().parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=_path().parent,
                                             prefix="model-settings-", delete=False) as handle:
                temporary = handle.name
                json.dump(payload.model_dump(), handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, _path())
        except OSError as exc:
            raise ApiError("MODEL_SETTINGS_UNAVAILABLE", status=503, category="configuration",
                           detail="模型设置保存失败，请稍后重试。") from exc
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink(missing_ok=True)
    return _response()
