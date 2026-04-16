from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

from app.services.foundation.llm import LLMService
from app.settings import settings


@dataclass
class _CachedGraphEntry:
    agent: Any
    last_accessed_at: float


_GRAPH_AGENT_CACHE_LOCK = threading.Lock()
_GRAPH_AGENT_CACHE: OrderedDict[str, _CachedGraphEntry] = OrderedDict()
_PLACEHOLDER_AGENT: Any | None = None
_GRAPH_BUILD_SIGNATURE = "deepagents-2026-03-30-execute-preserve-v3"


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
        "deepagents_run_budget_seconds": float(
            getattr(settings, "deepagents_run_budget_seconds", 900.0) or 900.0
        ),
        "deepagents_run_timeout_seconds": float(
            getattr(settings, "deepagents_run_timeout_seconds", 180.0) or 180.0
        ),
        "deepagents_stream_idle_timeout_seconds": float(
            getattr(settings, "deepagents_stream_idle_timeout_seconds", 180.0) or 180.0
        ),
        "deepagents_tool_timeout_seconds": float(
            getattr(settings, "deepagents_tool_timeout_seconds", 30.0) or 30.0
        ),
        "deepagents_tool_timeout_seconds_fast": float(
            getattr(settings, "deepagents_tool_timeout_seconds_fast", 30.0) or 30.0
        ),
        "deepagents_tool_timeout_seconds_io": float(
            getattr(settings, "deepagents_tool_timeout_seconds_io", 90.0) or 90.0
        ),
        "deepagents_tool_timeout_seconds_execute": float(
            getattr(settings, "deepagents_tool_timeout_seconds_execute", 180.0) or 180.0
        ),
        "deepagents_write_file_max_chars": int(
            getattr(settings, "deepagents_write_file_max_chars", 50000) or 50000
        ),
        "desktop_plugin_execute_enabled": bool(
            getattr(settings, "desktop_plugin_execute_enabled", False)
        ),
        "desktop_plugin_execute_timeout_seconds": float(
            getattr(settings, "desktop_plugin_execute_timeout_seconds", 20.0) or 20.0
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


def get_placeholder_agent(builder: Callable[[], Any]) -> Any:
    global _PLACEHOLDER_AGENT
    with _GRAPH_AGENT_CACHE_LOCK:
        if _PLACEHOLDER_AGENT is None:
            _PLACEHOLDER_AGENT = builder()
        return _PLACEHOLDER_AGENT


def reset_graph_agent_cache_for_tests() -> None:
    global _PLACEHOLDER_AGENT
    with _GRAPH_AGENT_CACHE_LOCK:
        _GRAPH_AGENT_CACHE.clear()
        _PLACEHOLDER_AGENT = None


_get_placeholder_agent = get_placeholder_agent
_reset_graph_agent_cache_for_tests = reset_graph_agent_cache_for_tests
