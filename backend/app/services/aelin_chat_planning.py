from __future__ import annotations

"""
Thin compatibility wrapper for chat planning helpers.

All heavy planning logic now lives in ``aelin_chat_planning_impl``.  This module
only re-exports the small public surface that routers and tests rely on, so that
existing imports like ``app.services.aelin_chat_planning._plan_tool_usage`` keep
working while the implementation can evolve in a separate file.
"""

from app.services.aelin_chat_planning_impl import (  # noqa: F401
    _build_intent_contract,
    _plan_tool_usage,
    _critic_tool_plan,
    _build_web_query_pack,
    _build_retry_web_queries,
    _extract_search_subject,
    _decompose_web_context_boundaries,
    _normalize_search_mode,
    _is_time_sensitive_query,
    _is_sports_result_query,
)

__all__ = [
    "_build_intent_contract",
    "_plan_tool_usage",
    "_critic_tool_plan",
    "_build_web_query_pack",
    "_build_retry_web_queries",
    "_extract_search_subject",
    "_decompose_web_context_boundaries",
    "_normalize_search_mode",
    "_is_time_sensitive_query",
    "_is_sports_result_query",
]

