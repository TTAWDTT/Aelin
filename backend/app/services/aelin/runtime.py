from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import crud
from app.models import User
from app.schemas import AgentConfigOut
from app.services.foundation.encryption import decrypt_optional
from app.services.foundation.llm import LLMService
from app.settings import settings


def default_config() -> AgentConfigOut:
    return AgentConfigOut(
        provider="rule_based",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        verify_ssl=bool(getattr(settings, "llm_verify_ssl", True)),
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
        verify_ssl=bool(getattr(config, "verify_ssl", True)),
        has_api_key=bool(api_key),
        web_search_proxy_url=str(config.web_search_proxy_url or ""),
    )


def resolve_llm_service(db: Session, user: User) -> tuple[LLMService, str]:
    return resolve_llm_service_for_user_id(db, int(user.id))


def resolve_llm_service_for_user_id(db: Session, user_id: int) -> tuple[LLMService, str]:
    config = config_out(db, int(user_id))
    provider = (config.provider or "rule_based").lower()
    if provider in {"rule_based", "rule-based", "builtin", "local"}:
        return LLMService(config, None), "rule_based"

    stored = crud.get_agent_config(db, user_id=int(user_id))
    api_key = decrypt_optional(stored.api_key if stored else None) if stored else None
    if not api_key or not (config.base_url or "").strip():
        return LLMService(config, None), "openai"
    return LLMService(config, api_key), "openai"


def normalize_workspace(raw: str) -> str:
    """
    Normalize a workspace identifier into a safe, slug-like token.

    The result is intentionally conservative so it can be used both as a
    logical workspace key and as part of a filesystem path, without risking
    directory traversal or accidental collisions caused by whitespace and
    separators.
    """
    import re

    clean = " ".join((raw or "").strip().split()).lower()
    if not clean:
        return "default"

    # Replace any character that is not a-z / 0-9 / '_' / '-' / CJK with '-'. This
    # also strips path separators like '/' and '\\', as well as dots, so a
    # value such as '../../etc/passwd' is normalized to a harmless slug while
    # still allowing human-friendly Chinese workspace names.
    slug = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "-", clean).strip("-")
    if not slug:
        return "default"
    return slug[:64]

