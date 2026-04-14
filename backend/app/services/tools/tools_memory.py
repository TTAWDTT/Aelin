from __future__ import annotations

from typing import Any

from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.tools.tool_helpers import _result_error, _result_ok, _safe_int


def _normalize_kinds(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def tool_memory_search(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    if callable(getattr(context, "cancel_checker", None)) and context.cancel_checker():
        return _result_error("memory_search_cancelled: request cancelled before memory search started")

    query = str(args.get("query") or "").strip()[:240]
    if not query:
        return _result_error("missing query: you must pass a non-empty 'query' field")

    memory_service = getattr(context, "memory_service", None)
    if memory_service is None:
        return _result_error("memory_search_unavailable: memory service is not available in this runtime")

    top_k = _safe_int(args.get("top_k"), 6, low=1, high=20)
    kinds = _normalize_kinds(args.get("kinds"))

    items = list(
        memory_service.search_memory(
            user_id=int(getattr(context, "user_id", 0) or 0),
            workspace=str(getattr(context, "workspace", "default") or "default"),
            query=query,
            top_k=top_k,
            kinds=kinds,
        )
        or []
    )

    if callable(getattr(context, "cancel_checker", None)) and context.cancel_checker():
        return _result_error("memory_search_cancelled: request cancelled while memory search was running")

    if not items:
        return _result_ok(
            items=[],
            total=0,
            query=query,
            kinds=kinds,
            no_new_info=True,
            summary="no matching long-term memory found",
        )

    return _result_ok(
        items=items,
        total=len(items),
        query=query,
        kinds=kinds,
        summary=f"found {len(items)} long-term memory hit(s)",
    )
