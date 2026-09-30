"""Expose the configured generation route without making a paid model call."""

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from tcm_platform.api_contract import Actor
from tcm_platform.cloud_models import CloudResearchModel
from tcm_platform.local_auth import COOKIE_NAME, current_actor

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def _read_actor(request: Request) -> Actor:
    actor = current_actor(request.cookies.get(COOKIE_NAME))
    actor.require("research.read")
    return actor


@router.get("/capabilities")
def research_capabilities(actor: Annotated[Actor, Depends(_read_actor)]) -> dict:
    """Use the worker's configuration without reading a key or making a call.

    Credentials, availability, balance and model quality still require a
    separately authorized real research run.
    """
    if not os.getenv("TCM_RESEARCH_MODEL", "").strip():
        return {"models": [], "unavailable_reason":
                "服务尚未配置研究模型（TCM_RESEARCH_MODEL），请联系管理员完成配置。"}
    try:
        model = CloudResearchModel(
            provider=os.getenv("TCM_RESEARCH_PROVIDER", "siliconflow").lower(),
            model=os.getenv("TCM_RESEARCH_MODEL", ""), api_key="",
        )
        if len(model.model_version) > 200 or any(char.isspace() for char in model.model):
            raise ValueError("configured route cannot be submitted by the research API")
    except ValueError:
        reason = "研究模型配置无效，请联系管理员核对提供商和模型名称。"
    else:
        provider_name = {"siliconflow": "硅基流动", "deepseek": "DeepSeek"}[model.provider]
        return {"models": [{"model_version": model.model_version,
                             "label": f"{provider_name} · {model.model}"}],
                "unavailable_reason": None}
    return {"models": [], "unavailable_reason": reason}
