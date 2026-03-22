from __future__ import annotations

from typing import Any, TYPE_CHECKING

from app.services.tools.tool_helpers import _result_error, _result_ok, _safe_int

if TYPE_CHECKING:
    from app.services.aelin.tool_hub import AelinToolHub


def tool_attachment_search(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
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
        attachment_ids = list(getattr(hub, "_available_attachment_ids", []) or [])
    if not attachment_ids:
        return _result_error("missing attachment_ids")

    top_k = _safe_int(args.get("top_k"), 5, low=1, high=20)
    mode = str(args.get("mode") or "keyword").strip().lower()
    if mode not in {"keyword", "hybrid"}:
        mode = "keyword"

    service = getattr(hub, "_attachments", None)
    result = service.search(  # type: ignore[call-arg]
        getattr(hub, "db", None),
        user_id=int(getattr(hub, "user_id", 0) or 0),
        workspace=str(getattr(hub, "workspace", "default") or "default"),
        query=query,
        attachment_ids=attachment_ids,
        top_k=top_k,
        mode=mode,
    )
    if not bool(result.get("ok")):
        return _result_error(str(result.get("error") or "attachment_search_failed"))

    return _result_ok(
        query=query,
        mode=mode,
        attachment_ids=list(result.get("attachment_ids") or []),
        total=int(result.get("total") or 0),
        content=str(result.get("content") or "")[:8000],
        hits=list(result.get("hits") or []),
    )

