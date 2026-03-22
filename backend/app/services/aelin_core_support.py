from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import (
    AelinCitation,
    AelinMemoryLayers,
    AelinMemoryLayerItem,
)
from app.services.agent_memory import AgentMemoryService
from app.services.aelin_context_service import (
    build_context_bundle as _build_context_bundle_service,
    build_cached_base_context_bundle as _build_cached_base_context_bundle_service,
)
from app.services.aelin_runtime import normalize_workspace as _normalize_workspace
from app.services.file_memory_bridge import file_memory_bridge
from app.services.summarizer import RuleBasedSummarizer
from app.services.web_search import WebSearchResult, WebSearchService
from app.settings import settings


_memory = AgentMemoryService()
_summarizer = RuleBasedSummarizer()
_web_search = WebSearchService()
_file_memory = file_memory_bridge

_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS = max(
    0.0,
    float(getattr(settings, "aelin_base_context_cache_ttl_seconds", 4.0) or 4.0),
)
_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES = max(
    0,
    int(getattr(settings, "aelin_base_context_cache_max_entries", 128) or 128),
)


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
    # NOTE: the cache itself is owned by aelin_core; this helper only forwards
    # the call to the context service with normalized parameters.
    from app.services.aelin_core import (  # circular import safe at runtime
        _base_context_cache,
        _base_context_cache_lock,
    )

    return _build_cached_base_context_bundle_service(
        db,
        user_id=user_id,
        workspace=workspace_norm,
        memory_service=_memory,
        ttl_seconds=_AELIN_BASE_CONTEXT_CACHE_TTL_SECONDS,
        max_entries=_AELIN_BASE_CONTEXT_CACHE_MAX_ENTRIES,
        cache=_base_context_cache,
        lock=_base_context_cache_lock,
    )


def _empty_memory_snapshot() -> dict[str, Any]:
    return {
        "active_items": [],
        "matched_items": [],
        "active_count": 0,
        "matched_count": 0,
        "matched_file_items": [],
    }


def _build_cached_memory_snapshot(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    query: str,
    include_file_memory: bool,
) -> dict[str, Any]:
    # The old follow-up subsystem is gone; only file-memory retrieval remains,
    # and that is now handled directly by DeepAgents tools. For compatibility
    # this returns an empty snapshot.
    _ = (db, user_id, workspace, query, include_file_memory)
    return _empty_memory_snapshot()


def _to_citations(raw_focus_items: list[dict], max_items: int) -> list[AelinCitation]:
    items: list[AelinCitation] = []
    for row in raw_focus_items[: max(1, min(20, max_items))]:
        try:
            items.append(
                AelinCitation(
                    message_id=int(row.get("message_id") or 0),
                    source=str(row.get("source") or "unknown"),
                    source_label=str(row.get("source_label") or row.get("source") or "unknown"),
                    sender=str(row.get("sender") or ""),
                    sender_avatar_url=(
                        str(row.get("sender_avatar_url") or "").strip() or None
                    ),
                    title=str(row.get("title") or ""),
                    received_at=str(row.get("received_at") or ""),
                    score=float(row.get("score") or 0.0),
                )
            )
        except Exception:
            continue
    return items


def _get_memory_summary_for_chat(db: Session, user_id: int, *, workspace: str = "default") -> str:
    """
    Build the concise memory summary string used by the DeepAgents agent loop.

    说明：
    - 这是 DeepAgents chat path 获取 memory_summary 的唯一入口；其他
      代码不得绕过本函数自行拼装 summary，避免出现多套不一致的记忆视图。
    - 实现上仅委托 `AgentMemoryService.build_system_memory_prompt`，这样
      DeepAgents 始终看到与 `/memory/AGENTS.md` 一致的文件视图，而不会
      回落到任何 legacy DB 字段。
    """
    try:
        summary = _memory.build_system_memory_prompt(db, user_id, query="")
    except Exception:
        # In DeepAgents 模式下，记忆完全依赖 `/memory/AGENTS.md` 虚拟文件；当构建失败时，
        # 不再回退到任何 DB 记忆字段，直接返回空串由上层兜底。
        summary = ""
    return str(summary or "").strip()


__all__ = [
    "_scoped_web_search_service",
    "_build_context_bundle",
    "_build_cached_base_context_bundle",
    "_empty_memory_snapshot",
    "_build_cached_memory_snapshot",
    "_to_citations",
    "_get_memory_summary_for_chat",
    "_file_memory",
    "_memory",
    "_web_search",
]
