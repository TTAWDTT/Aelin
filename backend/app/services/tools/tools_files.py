from __future__ import annotations

from typing import Any

from langgraph.runtime import get_runtime
from langchain_core.runnables.config import ensure_config
from sqlalchemy import select

from app.models import AttachmentDocument
from app.services.deepagents.run_context import DeepAgentsRunContext
from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.foundation.service_utils import normalize_positive_ints
from app.services.tools.tool_helpers import _result_error, _result_ok, _safe_int


def _runtime_configurable() -> dict[str, Any]:
    try:
        config = ensure_config()
    except Exception:
        return {}
    configurable = config.get("configurable") or {}
    return configurable if isinstance(configurable, dict) else {}


def _scoped_attachment_ids_from_run_context() -> list[int]:
    try:
        runtime = get_runtime(DeepAgentsRunContext)
    except Exception:
        return []
    context = getattr(runtime, "context", None)
    if context is None:
        return []
    if isinstance(context, dict):
        raw_ids = context.get("attachment_ids")
    else:
        raw_ids = getattr(context, "attachment_ids", None)
    return normalize_positive_ints(raw_ids, cap=20)


def _scoped_attachment_ids_from_runtime() -> list[int]:
    return normalize_positive_ints(_runtime_configurable().get("attachment_ids"), cap=20)


def _scoped_thread_id_from_runtime() -> str:
    return str(_runtime_configurable().get("thread_id") or "").strip()[:128]


def _scoped_user_id_from_runtime(context: ToolRuntimeContext) -> int:
    configurable = _runtime_configurable()
    for key in ("langgraph_auth_user_id", "user_id"):
        try:
            parsed = int(configurable.get(key) or 0)
        except Exception:
            parsed = 0
        if parsed > 0:
            return parsed
    return int(context.user_id or 0)


def _scoped_workspace_from_runtime(context: ToolRuntimeContext) -> str:
    workspace = str(_runtime_configurable().get("workspace") or "").strip()
    if workspace:
        return workspace[:64]
    return str(context.workspace or "default").strip() or "default"


def _fallback_attachment_ids_from_storage(context: ToolRuntimeContext) -> list[int]:
    session_factory = context.session_factory
    if not callable(session_factory):
        return []

    user_id = _scoped_user_id_from_runtime(context)
    workspace = _scoped_workspace_from_runtime(context)
    thread_id = _scoped_thread_id_from_runtime()
    db = session_factory()
    try:
        def _fetch_ids(*, session_id: str | None = None, limit: int = 8) -> list[int]:
            stmt = (
                select(AttachmentDocument.id)
                .where(
                    AttachmentDocument.user_id == int(user_id),
                    AttachmentDocument.workspace == workspace,
                    AttachmentDocument.parse_status == "ready",
                )
                .order_by(AttachmentDocument.created_at.desc(), AttachmentDocument.id.desc())
                .limit(limit)
            )
            if session_id:
                stmt = stmt.where(AttachmentDocument.session_id == session_id)
            rows = db.scalars(stmt).all()
            return normalize_positive_ints(list(rows), cap=20)

        if thread_id:
            scoped_ids = _fetch_ids(session_id=thread_id, limit=20)
            if scoped_ids:
                return scoped_ids
        return _fetch_ids(limit=8)
    finally:
        db.close()


def tool_attachment_search(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
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
        attachment_ids = _scoped_attachment_ids_from_run_context()
    if not attachment_ids:
        attachment_ids = _scoped_attachment_ids_from_runtime()
    if not attachment_ids:
        attachment_ids = _fallback_attachment_ids_from_storage(context)
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
    session_factory = context.session_factory
    if not callable(session_factory):
        return _result_error("attachment_search_failed: session_factory unavailable")
    db = session_factory()
    try:
        result = service.search(  # type: ignore[call-arg]
            db,
            user_id=int(context.user_id or 0),
            workspace=str(context.workspace or "default"),
            query=query,
            attachment_ids=attachment_ids,
            top_k=top_k,
            mode=mode,
        )
    finally:
        db.close()
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

