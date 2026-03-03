from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import crud
from app.models import User
from app.schemas import AgentConfigOut
from app.services.encryption import decrypt_optional
from app.services.llm import LLMService


def default_config() -> AgentConfigOut:
    return AgentConfigOut(
        provider="rule_based",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        has_api_key=False,
        web_search_proxy_url="",
    )


def config_out(db: Session, user_id: int) -> AgentConfigOut:
    config = crud.get_agent_config(db, user_id=user_id)
    if config is None:
        return default_config()

    api_key = decrypt_optional(config.api_key)
    return AgentConfigOut(
        provider=(config.provider or "rule_based").lower(),
        base_url=config.base_url or "https://api.openai.com/v1",
        model=config.model or "gpt-4o-mini",
        temperature=float(config.temperature or 0.2),
        has_api_key=bool(api_key),
        web_search_proxy_url=str(config.web_search_proxy_url or ""),
    )


def resolve_llm_service(db: Session, user: User) -> tuple[LLMService, str]:
    config = config_out(db, user.id)
    provider = (config.provider or "rule_based").lower()
    if provider in {"rule_based", "rule-based", "builtin", "local"}:
        return LLMService(config, None), "rule_based"

    stored = crud.get_agent_config(db, user_id=user.id)
    api_key = decrypt_optional(stored.api_key if stored else None) if stored else None
    if not api_key or not (config.base_url or "").strip():
        return LLMService(config, None), "openai"
    return LLMService(config, api_key), "openai"


def normalize_workspace(raw: str) -> str:
    clean = " ".join((raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


def json_from_text(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
