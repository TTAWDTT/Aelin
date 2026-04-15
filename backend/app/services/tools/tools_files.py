from __future__ import annotations

from collections import OrderedDict
import threading
import time
from typing import Any

from langgraph.runtime import get_runtime
from langchain_core.runnables.config import ensure_config
from sqlalchemy import select

from app.models import AttachmentDocument
from app.services.deepagents.run_context import DeepAgentsRunContext
from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.foundation.service_utils import normalize_positive_ints
from app.services.tools.tool_helpers import _result_error, _result_ok, _safe_int
from app.settings import settings


_ATTACHMENT_SCOPE_CACHE_LOCK = threading.Lock()
_ATTACHMENT_SCOPE_CACHE: OrderedDict[tuple[int, str, str, int], tuple[float, list[int]]] = OrderedDict()


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


def _attachment_scope_cache_ttl_seconds() -> float:
    try:
        return max(
            0.0,
            float(getattr(settings, "deepagents_attachment_scope_cache_ttl_seconds", 8.0) or 0.0),
        )
    except Exception:
        return 8.0


def _attachment_scope_cache_max_entries() -> int:
    try:
        return max(
            8,
            int(getattr(settings, "deepagents_attachment_scope_cache_max_entries", 64) or 64),
        )
    except Exception:
        return 64


def _attachment_scope_cache_key(
    context: ToolRuntimeContext,
    *,
    user_id: int,
    workspace: str,
    thread_id: str,
) -> tuple[int, str, str, int]:
    return (
        int(user_id),
        str(workspace or "default"),
        str(thread_id or ""),
        id(context.session_factory),
    )


def _cached_attachment_scope_ids(
    context: ToolRuntimeContext,
    *,
    user_id: int,
    workspace: str,
    thread_id: str,
) -> list[int] | None:
    ttl_seconds = _attachment_scope_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return None
    key = _attachment_scope_cache_key(
        context,
        user_id=user_id,
        workspace=workspace,
        thread_id=thread_id,
    )
    with _ATTACHMENT_SCOPE_CACHE_LOCK:
        cached = _ATTACHMENT_SCOPE_CACHE.get(key)
        if cached is None:
            return None
        cached_at, ids = cached
        if (time.monotonic() - float(cached_at)) > ttl_seconds:
            _ATTACHMENT_SCOPE_CACHE.pop(key, None)
            return None
        _ATTACHMENT_SCOPE_CACHE.move_to_end(key)
        return list(ids)


def _remember_attachment_scope_ids(
    context: ToolRuntimeContext,
    *,
    user_id: int,
    workspace: str,
    thread_id: str,
    ids: list[int],
) -> list[int]:
    stored = normalize_positive_ints(ids, cap=20)
    if not stored:
        return []
    key = _attachment_scope_cache_key(
        context,
        user_id=user_id,
        workspace=workspace,
        thread_id=thread_id,
    )
    with _ATTACHMENT_SCOPE_CACHE_LOCK:
        _ATTACHMENT_SCOPE_CACHE[key] = (time.monotonic(), list(stored))
        _ATTACHMENT_SCOPE_CACHE.move_to_end(key)
        while len(_ATTACHMENT_SCOPE_CACHE) > _attachment_scope_cache_max_entries():
            _ATTACHMENT_SCOPE_CACHE.popitem(last=False)
    return list(stored)


def clear_attachment_scope_cache_for_tests() -> None:
    with _ATTACHMENT_SCOPE_CACHE_LOCK:
        _ATTACHMENT_SCOPE_CACHE.clear()


def _fallback_attachment_ids_from_storage(context: ToolRuntimeContext) -> list[int]:
    session_factory = context.session_factory
    if not callable(session_factory):
        return []

    user_id = _scoped_user_id_from_runtime(context)
    workspace = _scoped_workspace_from_runtime(context)
    thread_id = _scoped_thread_id_from_runtime()
    cached_ids = _cached_attachment_scope_ids(
        context,
        user_id=user_id,
        workspace=workspace,
        thread_id=thread_id,
    )
    if cached_ids is not None:
        return cached_ids
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
                return _remember_attachment_scope_ids(
                    context,
                    user_id=user_id,
                    workspace=workspace,
                    thread_id=thread_id,
                    ids=scoped_ids,
                )
        workspace_ids = _fetch_ids(limit=8)
        if workspace_ids:
            return _remember_attachment_scope_ids(
                context,
                user_id=user_id,
                workspace=workspace,
                thread_id=thread_id,
                ids=workspace_ids,
            )
        return []
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

