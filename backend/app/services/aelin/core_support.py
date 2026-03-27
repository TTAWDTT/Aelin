from __future__ import annotations

import threading
from typing import Any

from sqlalchemy.orm import Session
from app.services.memory.agent_memory import AgentMemoryService
from app.services.aelin.context_service import (
    build_context_bundle as _build_context_bundle_service,
    build_cached_base_context_bundle as _build_cached_base_context_bundle_service,
)
from app.services.aelin.runtime import normalize_workspace as _normalize_workspace
from app.services.web.web_search import WebSearchService
from app.settings import settings


_memory = AgentMemoryService()
_web_search = WebSearchService()
_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS = max(
    0.0,
    float(getattr(settings, "aelin_base_context_cache_ttl_seconds", 4.0) or 4.0),
)
_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES = max(
    0,
    int(getattr(settings, "aelin_base_context_cache_max_entries", 128) or 128),
)
_BASE_CONTEXT_CACHE_LOCK = threading.Lock()
_BASE_CONTEXT_CACHE: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}


def _scoped_web_search_service(proxy_url: str = "") -> WebSearchService:
    return WebSearchService(
        timeout_seconds=float(getattr(_web_search, "timeout_seconds", 10.0) or 10.0),
        max_parallel_providers=int(getattr(_web_search, "max_parallel_providers", 4) or 4),
        max_parallel_fetch=int(getattr(_web_search, "max_parallel_fetch", 4) or 4),
        enable_reader_fallback=bool(getattr(_web_search, "enable_reader_fallback", True)),
        enable_browser_fallback=bool(getattr(_web_search, "enable_browser_fallback", True)),
        proxy_url=str(proxy_url or "").strip(),
    )


def _build_context_bundle(db: Session, user_id: int, *, workspace: str, query: str) -> dict:
    workspace_norm = _normalize_workspace(workspace)
    return _build_context_bundle_service(
        db,
        user_id,
        workspace=workspace_norm,
        query=query,
        memory_service=_memory,
    )


def _build_cached_base_context_bundle(db: Session, user_id: int, *, workspace: str) -> dict[str, Any]:
    workspace_norm = _normalize_workspace(workspace)
    return _build_cached_base_context_bundle_service(
        db,
        user_id=user_id,
        workspace=workspace_norm,
        memory_service=_memory,
        ttl_seconds=_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS,
        max_entries=_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES,
        cache=_BASE_CONTEXT_CACHE,
        lock=_BASE_CONTEXT_CACHE_LOCK,
    )


def _get_agents_memory_text_for_chat(db: Session, user_id: int, *, workspace: str = "default") -> str:
    """
    Return the raw AGENTS.md text used by the DeepAgents agent loop.

    说明：
    - 这是 DeepAgents chat path 获取 `/memory/AGENTS.md` 文本的唯一入口；
      其他代码不得绕过本函数自行拼装 summary 或包装文件内容。
    - 实现上仅委托 `AgentMemoryService.get_agents_memory_text`，并且显式
      传入 workspace，这样 DeepAgents 始终看到与当前 workspace 一致的
      真实文件视图。
    """
    workspace_norm = _normalize_workspace(workspace)
    try:
        text = _memory.get_agents_memory_text(db, user_id, workspace=workspace_norm)
    except Exception:
        text = ""
    return str(text or "").strip()


__all__ = [
    "_scoped_web_search_service",
    "_build_context_bundle",
    "_build_cached_base_context_bundle",
    "_get_agents_memory_text_for_chat",
    "_memory",
    "_web_search",
]

