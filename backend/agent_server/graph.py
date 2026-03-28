from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from langgraph_sdk.runtime import ServerRuntime

from app.db import create_session
from app.schemas import AgentConfigOut
from app.services.deepagents.deepagents_graph import build_chat_agent
from app.services.deepagents.run_context import DeepAgentsRunContext
from app.services.deepagents.runtime_resolver import (
    build_tool_call_limiter,
    resolve_deepagents_runtime,
)
from app.services.deepagents.tool_runtime import build_tool_runtime_context
from app.services.foundation.llm import LLMService
from app.settings import settings


_LOG = logging.getLogger(__name__)
_GRAPH_AGENT_CACHE_LOCK = threading.Lock()
_GRAPH_AGENT_CACHE: OrderedDict[str, "_CachedGraphEntry"] = OrderedDict()
_PLACEHOLDER_AGENT: Any | None = None
_GRAPH_BUILD_SIGNATURE = "deepagents-2026-03-28-timeout-and-skills-v2"


@dataclass
class _CachedGraphEntry:
    agent: Any
    last_accessed_at: float


def _coerce_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def _runtime_user_id(
    runtime: ServerRuntime[DeepAgentsRunContext],
    context: DeepAgentsRunContext | None,
) -> int:
    user = getattr(runtime, "user", None)
    candidates: list[Any] = []
    if user is not None:
        for key in ("user_id", "id"):
            try:
                if key in user:
                    candidates.append(user[key])
            except Exception:
                pass
            candidates.append(getattr(user, key, None))
        candidates.append(getattr(user, "identity", None))
    if context is not None:
        candidates.append(getattr(context, "user_id", None))
    for value in candidates:
        user_id = _coerce_positive_int(value)
        if user_id > 0:
            return user_id
    return 0


def _context_value(context: DeepAgentsRunContext | dict[str, Any] | None, key: str, default: Any) -> Any:
    if context is None:
        return default
    if isinstance(context, dict):
        return context.get(key, default)
    try:
        return getattr(context, key)
    except Exception:
        return default


def _placeholder_service() -> LLMService:
    return LLMService(
        AgentConfigOut(
            provider="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            temperature=0.2,
            verify_ssl=True,
            has_api_key=True,
            web_search_proxy_url="",
        ),
        "placeholder",
    )


def _graph_cache_size() -> int:
    try:
        return max(1, int(getattr(settings, "agent_server_graph_cache_size", 8) or 8))
    except Exception:
        return 8


def _graph_cache_ttl_seconds() -> float:
    try:
        return max(
            30.0,
            float(getattr(settings, "agent_server_graph_cache_ttl_seconds", 900.0) or 900.0),
        )
    except Exception:
        return 900.0


def _fingerprint_text(value: Any) -> str:
    text = str(value or "")
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _service_cache_payload(service: LLMService) -> dict[str, Any]:
    config = getattr(service, "config", None)
    return {
        "provider": getattr(config, "provider", ""),
        "base_url": LLMService._normalize_base_url(getattr(config, "base_url", "") or ""),
        "model": getattr(config, "model", ""),
        "temperature": float(getattr(config, "temperature", 0.0) or 0.0),
        "verify_ssl": bool(getattr(config, "verify_ssl", True)),
        "web_search_proxy_url": getattr(config, "web_search_proxy_url", "") or "",
        "api_key_hash": _fingerprint_text(getattr(service, "api_key", None)),
    }


def _runtime_cache_key(
    *,
    user_id: int,
    workspace: str,
    attachment_ids: list[int],
    service: LLMService,
    provider: str,
    memory_text: str,
    limiter: Any,
) -> str:
    payload = {
        "graph_build_signature": _GRAPH_BUILD_SIGNATURE,
        "user_id": int(user_id),
        "workspace": str(workspace or "default"),
        "attachment_ids": [int(value) for value in attachment_ids],
        "provider": str(provider or ""),
        "service": _service_cache_payload(service),
        "memory_sha1": _fingerprint_text(memory_text),
        "allow_write_tools": bool(getattr(limiter, "allow_write_tools", False)),
        "max_tool_calls": int(getattr(limiter, "max_tool_calls", 0) or 0),
        "max_write_calls": int(getattr(limiter, "max_write_calls", 0) or 0),
        "consecutive_failures_limit": int(
            getattr(limiter, "consecutive_failures_limit", 0) or 0
        ),
        "consecutive_no_progress_limit": int(
            getattr(limiter, "consecutive_no_progress_limit", 0) or 0
        ),
        "deepagents_run_timeout_seconds": float(
            getattr(settings, "deepagents_run_timeout_seconds", 75.0) or 75.0
        ),
        "deepagents_stream_idle_timeout_seconds": float(
            getattr(settings, "deepagents_stream_idle_timeout_seconds", 45.0) or 45.0
        ),
        "deepagents_tool_timeout_seconds": float(
            getattr(settings, "deepagents_tool_timeout_seconds", 25.0) or 25.0
        ),
        "deepagents_write_file_max_chars": int(
            getattr(settings, "deepagents_write_file_max_chars", 50000) or 50000
        ),
        "deepagents_extra_skills_dir": str(
            getattr(settings, "deepagents_extra_skills_dir", "") or ""
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _prune_graph_agent_cache(now: float) -> None:
    ttl_seconds = _graph_cache_ttl_seconds()
    expired_keys = [
        key
        for key, entry in _GRAPH_AGENT_CACHE.items()
        if now - float(entry.last_accessed_at) > ttl_seconds
    ]
    for key in expired_keys:
        _GRAPH_AGENT_CACHE.pop(key, None)
    while len(_GRAPH_AGENT_CACHE) > _graph_cache_size():
        _GRAPH_AGENT_CACHE.popitem(last=False)


def _get_cached_graph_agent(cache_key: str) -> Any | None:
    with _GRAPH_AGENT_CACHE_LOCK:
        now = time.monotonic()
        _prune_graph_agent_cache(now)
        entry = _GRAPH_AGENT_CACHE.get(cache_key)
        if entry is None:
            return None
        entry.last_accessed_at = now
        _GRAPH_AGENT_CACHE.move_to_end(cache_key)
        return entry.agent


def _store_cached_graph_agent(cache_key: str, agent: Any) -> Any:
    with _GRAPH_AGENT_CACHE_LOCK:
        now = time.monotonic()
        _GRAPH_AGENT_CACHE[cache_key] = _CachedGraphEntry(
            agent=agent,
            last_accessed_at=now,
        )
        _GRAPH_AGENT_CACHE.move_to_end(cache_key)
        _prune_graph_agent_cache(now)
    return agent


def _get_placeholder_agent() -> Any:
    global _PLACEHOLDER_AGENT
    with _GRAPH_AGENT_CACHE_LOCK:
        if _PLACEHOLDER_AGENT is None:
            _PLACEHOLDER_AGENT = _build_placeholder_agent()
        return _PLACEHOLDER_AGENT


def _reset_graph_agent_cache_for_tests() -> None:
    global _PLACEHOLDER_AGENT
    with _GRAPH_AGENT_CACHE_LOCK:
        _GRAPH_AGENT_CACHE.clear()
        _PLACEHOLDER_AGENT = None


def _build_placeholder_agent() -> Any:
    agent, _, _, _ = build_chat_agent(
        service=_placeholder_service(),
        provider="openai",
        context=build_tool_runtime_context(
            user_id=0,
            workspace="default",
        ),
        limiter=build_tool_call_limiter(allow_write_tools=False),
        memory_text="",
        context_schema=DeepAgentsRunContext,
    )
    return agent


def _build_runtime_agent(user_id: int, context: DeepAgentsRunContext | None) -> Any:
    db = create_session()
    try:
        workspace = _context_value(context, "workspace", "default")
        raw_attachment_ids = _context_value(context, "attachment_ids", [])
        _LOG.info(
            "agent_server_runtime_context user_id=%s workspace=%s attachment_ids=%s context_type=%s",
            user_id,
            workspace,
            raw_attachment_ids,
            type(context).__name__ if context is not None else "None",
        )
        resolved = resolve_deepagents_runtime(
            db,
            user_id=user_id,
            workspace=workspace,
            raw_attachment_ids=raw_attachment_ids,
            session_factory=create_session,
        )
        resolved_user_id = _coerce_positive_int(getattr(resolved, "user_id", None)) or int(user_id)
        resolved_workspace = str(getattr(resolved, "workspace", workspace) or workspace or "default")
        resolved_attachment_ids = list(getattr(resolved, "attachment_ids", raw_attachment_ids) or [])
        cache_key = _runtime_cache_key(
            user_id=resolved_user_id,
            workspace=resolved_workspace,
            attachment_ids=resolved_attachment_ids,
            service=resolved.service,
            provider=resolved.provider,
            memory_text=resolved.memory_text,
            limiter=resolved.limiter,
        )
        cached_agent = _get_cached_graph_agent(cache_key)
        if cached_agent is not None:
            _LOG.debug(
                "agent_server_graph_cache_hit user_id=%s workspace=%s attachment_ids=%s",
                resolved_user_id,
                resolved_workspace,
                resolved_attachment_ids,
            )
            return cached_agent
        agent, _, _, _ = build_chat_agent(
            service=resolved.service,
            provider=resolved.provider,
            context=resolved.tool_context,
            limiter=resolved.limiter,
            memory_text=resolved.memory_text,
            context_schema=DeepAgentsRunContext,
        )
        if agent is None:
            return None
        _LOG.debug(
            "agent_server_graph_cache_store user_id=%s workspace=%s attachment_ids=%s",
            resolved_user_id,
            resolved_workspace,
            resolved_attachment_ids,
        )
        return _store_cached_graph_agent(cache_key, agent)
    finally:
        db.close()


@asynccontextmanager
async def make_graph(runtime: ServerRuntime[DeepAgentsRunContext]):
    execution_runtime = runtime.execution_runtime
    context = execution_runtime.context if execution_runtime is not None else None
    if execution_runtime is None:
        yield await asyncio.to_thread(_get_placeholder_agent)
        return

    user_id = _runtime_user_id(runtime, context)
    if user_id <= 0:
        _LOG.warning("agent_server_factory_missing_user_id access_context=%s", runtime.access_context)
        yield await asyncio.to_thread(_get_placeholder_agent)
        return

    agent = await asyncio.to_thread(_build_runtime_agent, user_id, context)
    if agent is None:
        _LOG.warning("agent_server_factory_fallback_placeholder user_id=%s", user_id)
        yield await asyncio.to_thread(_get_placeholder_agent)
        return
    yield agent
