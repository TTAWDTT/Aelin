from __future__ import annotations

from typing import Any

from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.tools.tool_helpers import _result_error, _result_ok, _safe_int


def tool_attachment_search(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.aelin.utils import normalize_positive_ints

    query = str(args.get("query") or "").strip()[:500]
    if not query:
        return _result_error("missing query")

    raw_ids = args.get("attachment_ids")
    attachment_ids: list[int] = normalize_positive_ints(
        raw_ids if isinstance(raw_ids, list) else [],
        cap=20,
    )
    if not attachment_ids:
        attachment_ids = list(context.available_attachment_ids or [])
    if not attachment_ids:
        return _result_error("missing attachment_ids")
    allowed_ids = set(int(item) for item in list(context.available_attachment_ids or []))
    if allowed_ids:
        invalid_ids = [item for item in attachment_ids if item not in allowed_ids]
        if invalid_ids:
            return _result_error(
                f"invalid attachment_ids: these ids are not available in this run: {invalid_ids[:6]}"
            )

    top_k = _safe_int(args.get("top_k"), 5, low=1, high=20)
    mode = str(args.get("mode") or "keyword").strip().lower()
    if mode not in {"keyword", "hybrid"}:
        mode = "keyword"

    service = context.attachment_service
    result = service.search(  # type: ignore[call-arg]
        context.db,
        user_id=int(context.user_id or 0),
        workspace=str(context.workspace or "default"),
        query=query,
        attachment_ids=attachment_ids,
        top_k=top_k,
        mode=mode,
    )
    if not bool(result.get("ok")):
        return _result_error(str(result.get("error") or "attachment_search_failed"))

    total = int(result.get("total") or 0)
    content = str(result.get("content") or "")[:8000]
    hits = list(result.get("hits") or [])
    if total <= 0 or (not content and not hits):
        return _result_ok(
            query=query,
            mode=mode,
            attachment_ids=list(result.get("attachment_ids") or []),
            total=0,
            content="",
            hits=[],
            no_new_info=True,
            summary="no matching attachment evidence found",
        )

    return _result_ok(
        query=query,
        mode=mode,
        attachment_ids=list(result.get("attachment_ids") or []),
        total=total,
        content=content,
        hits=hits,
        summary=f"found {total} attachment hit(s)",
    )

