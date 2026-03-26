from __future__ import annotations

from typing import Any

from app.services.tools.tool_helpers import _result_error, _result_items, _result_ok, _safe_int
from app.services.web.web_search import WebSearchResult
from app.services.deepagents.tool_runtime import ToolRuntimeContext


def tool_web_search(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "search_and_fetch").strip().lower()
    if action not in {"search", "search_and_fetch"}:
        # Keep the error short and explicit so DeepAgents can easily recover.
        return _result_error("unsupported action: expected 'search' or 'search_and_fetch'")

    query = str(args.get("query") or "").strip()[:400]
    if not query:
        # Explicitly tell the agent that query must be a non-empty string.
        return _result_error("missing query: you must pass a non-empty 'query' field")

    max_results = _safe_int(args.get("max_results"), 15, low=1, high=15)
    fetch_top_k = _safe_int(args.get("fetch_top_k"), 3, low=0, high=6)
    if action == "search_and_fetch" and fetch_top_k <= 0:
        return _result_error(
            "invalid search_and_fetch call: use action='search' when fetch_top_k is 0, or provide fetch_top_k>=1 when page fetching is needed"
        )
    fetch_top_k = min(fetch_top_k, max_results)

    rows: list[WebSearchResult] = []
    if action == "search":
        rows = list(context.web_search_service.search(query, max_results=max_results) or [])
    else:
        rows = list(
            context.web_search_service.search_and_fetch(
                query,
                max_results=max_results,
                fetch_top_k=fetch_top_k,
            )
            or []
        )

    providers: set[str] = set()
    items: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:max_results], start=1):
        title = str(getattr(row, "title", "") or "").strip()
        url = str(getattr(row, "url", "") or "").strip()
        snippet = str(getattr(row, "snippet", "") or "").strip()
        provider = str(getattr(row, "provider", "") or "").strip() or "unknown"
        source = str(getattr(row, "source", "") or "").strip() or "web"
        fetched_excerpt = str(getattr(row, "fetched_excerpt", "") or "").strip()
        fetch_mode = str(getattr(row, "fetch_mode", "") or "").strip() or "none"
        rank = _safe_int(getattr(row, "rank", idx), idx, low=1, high=9999)
        providers.add(provider)
        items.append(
            {
                "title": title[:220],
                "url": url[:600],
                "snippet": snippet[:320],
                "provider": provider[:32],
                "source": source[:24],
                "fetch_mode": fetch_mode[:24],
                "rank": rank,
                "fetched_excerpt": fetched_excerpt[:1200],
            }
        )

    if not items:
        return _result_ok(
            items=[],
            total=0,
            query=query,
            action=action,
            providers=[],
            fetch_top_k=(fetch_top_k if action == "search_and_fetch" else 0),
            no_new_info=True,
            summary="no web results found",
        )

    return _result_items(
        items,
        query=query,
        action=action,
        providers=sorted(providers),
        fetch_top_k=(fetch_top_k if action == "search_and_fetch" else 0),
        summary=f"found {len(items)} web result(s)",
    )

