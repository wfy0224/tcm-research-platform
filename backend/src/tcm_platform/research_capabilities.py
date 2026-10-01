"""Expose the configured generation route without making a paid model call."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from tcm_platform.api_contract import Actor
from tcm_platform.local_auth import COOKIE_NAME, current_actor
from tcm_platform.research_model_settings import model_choices, read_model_settings

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
    config = read_model_settings()
    if not config["models"]:
        return {"models": [], "unavailable_reason":
                "尚未添加研究模型，请打开“模型设置”添加。"}
    models = model_choices(config["models"])
    return {"models": models, "default_model": config["default_model"], "unavailable_reason": None if models else
            "研究模型配置无效，请联系管理员核对提供商和模型名称。"}
