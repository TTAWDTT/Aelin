from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AgentConfigOut, AgentConfigUpdate, AgentTestResponse, ModelCatalogResponse
from app.services.foundation.encryption import decrypt_optional
from app.services.foundation.llm import LLMService
from app.services.foundation.model_catalog import get_model_catalog

router = APIRouter(prefix="/agent", tags=["agent"])

def _default_config() -> AgentConfigOut:
    return AgentConfigOut(
        provider="rule_based",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        has_api_key=False,
        web_search_proxy_url="",
    )


def _config_out(db: Session, user_id: int) -> AgentConfigOut:
    config = crud.get_agent_config(db, user_id=user_id)
    if config is None:
        return _default_config()

    api_key = decrypt_optional(config.api_key)
    return AgentConfigOut(
        provider=(config.provider or "rule_based").lower(),
        base_url=config.base_url or "https://api.openai.com/v1",
        model=config.model or "gpt-4o-mini",
        temperature=float(config.temperature or 0.2),
        has_api_key=bool(api_key),
        web_search_proxy_url=str(config.web_search_proxy_url or ""),
    )


def _get_llm_service(db: Session, user: User) -> tuple[LLMService, str]:
    config = _config_out(db, user.id)
    provider = (config.provider or "rule_based").lower()

    if provider in {"rule_based", "rule-based", "builtin", "local"}:
        return LLMService(config, None), "rule_based"

    stored = crud.get_agent_config(db, user_id=user.id)
    api_key = decrypt_optional(stored.api_key if stored else None) if stored else None

    if not api_key:
        raise HTTPException(status_code=400, detail="请先在设置里配置 Agent API Key")
    if not (config.base_url or "").strip():
        raise HTTPException(status_code=400, detail="请先在设置里配置 Agent Base URL")

    return LLMService(config, api_key), "openai"


@router.get("/catalog", response_model=ModelCatalogResponse)
def model_catalog(force_refresh: bool = Query(default=False)):
    return get_model_catalog(force_refresh=force_refresh)


@router.get("/config", response_model=AgentConfigOut)
def get_agent_config(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return _config_out(db, current_user.id)


@router.patch("/config", response_model=AgentConfigOut)
def update_agent_config(
    payload: AgentConfigUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    provider = None
    if payload.provider is not None:
        provider = payload.provider.strip().lower()
        if not provider:
            raise HTTPException(status_code=400, detail="provider 不能为空")
    config = crud.upsert_agent_config(
        db,
        user_id=current_user.id,
        provider=provider,
        base_url=payload.base_url,
        model=payload.model,
        temperature=payload.temperature,
        api_key=payload.api_key,
        web_search_proxy_url=payload.web_search_proxy_url,
    )
    api_key = decrypt_optional(config.api_key)
    return AgentConfigOut(
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        temperature=float(config.temperature),
        has_api_key=bool(api_key),
        web_search_proxy_url=str(config.web_search_proxy_url or ""),
    )


@router.post("/test", response_model=AgentTestResponse)
def test_agent(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    if provider == "rule_based":
        return AgentTestResponse(ok=True, provider="rule_based", message="内置规则引擎已就绪")

    try:
        out = service._chat(
            messages=[
                {"role": "system", "content": "你是一个健康检查器。只回复 OK。"},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=30,
            stream=False,
        )
        return AgentTestResponse(ok=True, provider=service.config.provider, message=str(out) or "OK")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

