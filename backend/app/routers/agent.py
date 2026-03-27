from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AgentConfigOut, AgentConfigUpdate, AgentTestResponse, ModelCatalogResponse
from app.services.aelin.runtime import (
    config_out as runtime_config_out,
    resolve_llm_service_for_user_id,
)
from app.services.foundation.model_catalog import get_model_catalog

router = APIRouter(prefix="/agent", tags=["agent"])

def _get_llm_service(db: Session, user: User):
    config = runtime_config_out(db, user.id)
    service, provider = resolve_llm_service_for_user_id(db, int(user.id))
    provider = (config.provider or "rule_based").lower()
    if provider in {"rule_based", "rule-based", "builtin", "local"}:
        return service, "rule_based"
    if not config.has_api_key:
        raise HTTPException(status_code=400, detail="请先在设置里配置 Agent API Key")
    if not (config.base_url or "").strip():
        raise HTTPException(status_code=400, detail="请先在设置里配置 Agent Base URL")
    return service, "openai"


@router.get("/catalog", response_model=ModelCatalogResponse)
def model_catalog(force_refresh: bool = Query(default=False)):
    return get_model_catalog(force_refresh=force_refresh)


@router.get("/config", response_model=AgentConfigOut)
def get_agent_config(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return runtime_config_out(db, current_user.id)


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
        verify_ssl=payload.verify_ssl,
        api_key=payload.api_key,
        web_search_proxy_url=payload.web_search_proxy_url,
    )
    _ = config
    return runtime_config_out(db, current_user.id)


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

