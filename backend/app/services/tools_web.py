from __future__ import annotations

from typing import Any

from app.services.web_search import WebSearchResult


def tool_web_search(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Web search tool implementation extracted from AelinToolHub._tool_web_search.

    This helper delegates to the hub's configured WebSearchService instance and
    uses the shared result helpers on the hub module to keep behaviour identical
    to the inline implementation.
    """
    # Lazy import to avoid circular dependency at module import time.
    from app.services.aelin_tools import _safe_int, _result_items

    action = str(args.get("action") or "search_and_fetch").strip().lower()
    if action not in {"search", "search_and_fetch"}:
        from app.services.aelin_tools import _result_error

        # Keep the error short and explicit so DeepAgents can easily recover.
        return _result_error("unsupported action: expected 'search' or 'search_and_fetch'")

    query = str(args.get("query") or "").strip()[:400]
    if not query:
        from app.services.aelin_tools import _result_error

        # Explicitly tell the agent that query must be a non-empty string.
        return _result_error("missing query: you must pass a non-empty 'query' field")

    max_results = _safe_int(args.get("max_results"), 15, low=1, high=15)
    fetch_top_k = _safe_int(args.get("fetch_top_k"), 3, low=0, high=6)
    fetch_top_k = min(fetch_top_k, max_results)

    rows: list[WebSearchResult] = []
    if action == "search":
        rows = list(hub._web_search.search(query, max_results=max_results) or [])
    else:
        rows = list(
            hub._web_search.search_and_fetch(
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

    return _result_items(
        items,
        query=query,
        action=action,
        providers=sorted(providers),
        fetch_top_k=(fetch_top_k if action == "search_and_fetch" else 0),
    )
