from __future__ import annotations

from datetime import datetime, timezone
import logging
import queue
import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import create_session, get_session
from app.models import User
from app.routers.aelin import _dispatch_aelin_chat, _normalize_search_mode
from app.routers.aelin_text_helpers import _now_ms, _sse_event
from app.routers.auth import get_current_user
from app.schemas import (
    AelinBrowserConfirmRequest,
    AelinBrowserConfirmResponse,
    AelinChatRequest,
    AelinChatResponse,
)
from app.services.browser_automation import browser_automation_service


router = APIRouter(prefix="/aelin", tags=["aelin"])
_LOG = logging.getLogger(__name__)


def _preview(text: str, *, limit: int = 180) -> str:
    raw = " ".join(str(text or "").split())
    if len(raw) <= limit:
        return raw
    return f"{raw[: max(0, limit - 1)]}…"


def _is_cdp_restart_error(error: str) -> bool:
    clean = str(error or "").strip().lower()
    if not clean:
        return False
    # unwrap wrapped transport-style errors like "cdp_unavailable:cdp_launch_timeout"
    normalized = clean
    if normalized.startswith("cdp_unavailable:"):
        normalized = normalized.split(":", 1)[1].strip()
    return clean in {
        "browser_restart_required_for_cdp",
        "browser_restart_confirmation_required",
        "browser_restart_failed_for_cdp",
        "cdp_conflict_process_still_running",
        "cdp_launch_timeout",
    } or normalized in {
        "browser_restart_required_for_cdp",
        "browser_restart_confirmation_required",
        "browser_restart_failed_for_cdp",
        "cdp_conflict_process_still_running",
        "cdp_launch_timeout",
    } or "cdp_requires_browser_restart" in clean or "cdp_requires_browser_restart" in normalized


def _build_browser_restart_meta(restart_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = restart_meta if isinstance(restart_meta, dict) else {}
    return {
        "attempted": True,
        "ok": bool(meta.get("ok")),
        "error": str(meta.get("error") or "")[:180],
        "probe_reason": str(meta.get("probe_reason") or "")[:160],
        "probe_listener_count": int(meta.get("probe_listener_count") or 0),
        "probe_listener_pids": list(meta.get("probe_listener_pids") or []),
        "terminated_pids": list(meta.get("terminated_pids") or []),
        "killed_pids": list(meta.get("killed_pids") or []),
        "failed_pids": list(meta.get("failed_pids") or []),
        "remaining_pids": list(meta.get("remaining_pids") or []),
    }


@router.post("/chat", response_model=AelinChatResponse)
def aelin_chat(
    payload: AelinChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return _dispatch_aelin_chat(payload, db, current_user)


@router.post("/chat/stream")
def aelin_chat_stream(
    payload: AelinChatRequest,
    current_user: User = Depends(get_current_user),
):
    def _event_iter():
        req_id = uuid4().hex[:10]
        started = _now_ms()
        heartbeat_count = 0
        event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        done_token = "__done__"

        def _push(event: str, data: dict[str, Any]) -> None:
            _LOG.info(
                "aelin_stream event req=%s uid=%s event=%s keys=%s",
                req_id,
                int(current_user.id),
                str(event),
                ",".join(sorted([str(k) for k in list((data or {}).keys())[:8] if str(k)])) or "-",
            )
            event_queue.put((event, data))

        def _worker() -> None:
            local_db = create_session()
            try:
                _LOG.info(
                    "aelin_stream worker_start req=%s uid=%s workspace=%s query=%s",
                    req_id,
                    int(current_user.id),
                    str(payload.workspace or "default")[:64],
                    _preview(str(payload.query or "")),
                )
                user = local_db.get(User, int(current_user.id)) or current_user
                result = _dispatch_aelin_chat(payload, local_db, user, event_cb=_push)
                _LOG.info(
                    "aelin_stream worker_final req=%s uid=%s answer_len=%s actions=%s traces=%s",
                    req_id,
                    int(current_user.id),
                    len(str(result.answer or "")),
                    len(list(result.actions or [])),
                    len(list(result.tool_trace or [])),
                )
                _push("final", {"result": result.model_dump()})
            except Exception as e:
                _LOG.exception(
                    "aelin_stream worker_error req=%s uid=%s error=%s",
                    req_id,
                    int(current_user.id),
                    str(e)[:220],
                )
                _push("error", {"message": str(e)[:500] or "stream error"})
            finally:
                try:
                    local_db.close()
                except Exception:
                    pass
                _push("done", {"ts": _now_ms(), "status": done_token})
                _LOG.info(
                    "aelin_stream worker_done req=%s uid=%s duration_ms=%s",
                    req_id,
                    int(current_user.id),
                    max(0, _now_ms() - started),
                )

        _push(
            "start",
            {
                "ts": _now_ms(),
                "req_id": req_id,
                "query": payload.query.strip()[:180],
                "workspace": payload.workspace,
                "search_mode": _normalize_search_mode(getattr(payload, "search_mode", "auto")),
            },
        )
        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()

        heartbeat_interval_s = 5.0
        try:
            while True:
                try:
                    event, data = event_queue.get(timeout=heartbeat_interval_s)
                except queue.Empty:
                    # Emit a real SSE event so proxies/clients don't treat this as idle.
                    heartbeat_count += 1
                    yield _sse_event("ping", {"ts": _now_ms(), "req_id": req_id, "hb": heartbeat_count})
                    if (not worker.is_alive()) and event_queue.empty():
                        yield _sse_event("done", {"ts": _now_ms(), "status": done_token})
                        break
                    continue

                yield _sse_event(event, data)
                if event == "done":
                    break
        except BaseException as exc:
            _LOG.warning(
                "aelin_stream interrupted req=%s uid=%s type=%s msg=%s",
                req_id,
                int(current_user.id),
                type(exc).__name__,
                str(exc)[:180],
            )
            raise
        finally:
            _LOG.info(
                "aelin_stream closed req=%s uid=%s duration_ms=%s heartbeats=%s",
                req_id,
                int(current_user.id),
                max(0, _now_ms() - started),
                heartbeat_count,
            )

    return StreamingResponse(
        _event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/agent/browser/confirm", response_model=AelinBrowserConfirmResponse)
def confirm_browser_action(
    payload: AelinBrowserConfirmRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    workspace = str(payload.workspace or "default").strip()[:64] or "default"
    next_call = payload.next_call if isinstance(payload.next_call, dict) else {}
    tool_name = str(next_call.get("tool") or "").strip().lower()
    if tool_name not in {"browser_use", "browser_state_get"}:
        raise HTTPException(status_code=400, detail="unsupported_next_call_tool")

    action = str(next_call.get("action") or payload.action or "").strip().lower()
    if tool_name == "browser_use" and action not in {"navigate", "click", "type", "scroll", "wait"}:
        raise HTTPException(status_code=400, detail="invalid_next_call_action")
    if tool_name == "browser_state_get" and action not in {"", "state_get"}:
        raise HTTPException(status_code=400, detail="invalid_next_call_action")

    raw_args = next_call.get("args")
    args = raw_args if isinstance(raw_args, dict) else {}
    clean_args: dict[str, Any]
    scope = "cdp"
    if tool_name == "browser_use":
        allowed_keys = {
            "url",
            "target",
            "selector",
            "text",
            "value",
            "strategy",
            "role",
            "press_enter",
            "direction",
            "amount",
            "wait_ms",
            "timeout_ms",
            "scope",
            "confirm",
        }
        clean_args = {str(k): v for k, v in args.items() if str(k) in allowed_keys}
        clean_args["confirm"] = True
        scope = str(clean_args.get("scope") or "cdp").strip().lower()
        if scope not in {"auto", "cdp", "external"}:
            scope = "cdp"
        if action != "navigate" and scope == "external":
            scope = "cdp"
        clean_args["scope"] = scope
        result = browser_automation_service.use(
            user_id=int(current_user.id),
            workspace=workspace,
            action=action,
            args=clean_args,
            scope=scope,
        )
    else:
        allowed_keys = {
            "scope",
            "include_dom",
            "include_a11y",
            "max_targets",
            "max_items",
            "pid",
        }
        clean_args = {str(k): v for k, v in args.items() if str(k) in allowed_keys}
        scope = str(clean_args.get("scope") or "cdp").strip().lower()
        if scope not in {"auto", "cdp", "external", "system", "all"}:
            scope = "cdp"
        clean_args["scope"] = "cdp" if scope != "system" else scope
        scope = str(clean_args.get("scope") or "cdp")
        result = browser_automation_service.state_get(
            user_id=int(current_user.id),
            workspace=workspace,
            scope=scope,
            include_dom=bool(clean_args.get("include_dom", False)),
            include_a11y=bool(clean_args.get("include_a11y", False)),
            max_targets=int(clean_args.get("max_targets") or 30),
            max_items=int(clean_args.get("max_items") or 20),
            pid=int(clean_args.get("pid") or 0),
        )

    restart_meta: dict[str, Any] | None = None
    pre_restart_meta = result.get("restart") if isinstance(result.get("restart"), dict) else None
    if (not bool(result.get("ok"))) and _is_cdp_restart_error(str(result.get("error") or "")):
        restart_meta = browser_automation_service.force_restart_to_cdp(timeout_seconds=24.0)
        if bool(restart_meta.get("ok")):
            if tool_name == "browser_use":
                retry = browser_automation_service.use(
                    user_id=int(current_user.id),
                    workspace=workspace,
                    action=action,
                    args=clean_args,
                    scope="cdp",
                )
            else:
                retry = browser_automation_service.state_get(
                    user_id=int(current_user.id),
                    workspace=workspace,
                    scope="cdp",
                    include_dom=bool(clean_args.get("include_dom", False)),
                    include_a11y=bool(clean_args.get("include_a11y", False)),
                    max_targets=int(clean_args.get("max_targets") or 30),
                    max_items=int(clean_args.get("max_items") or 20),
                    pid=int(clean_args.get("pid") or 0),
                )
            if isinstance(retry, dict):
                result = dict(retry)
            else:
                result = {"ok": False, "error": "browser_confirm_retry_invalid_payload"}
        result = dict(result if isinstance(result, dict) else {})
        result["restart"] = _build_browser_restart_meta(restart_meta)
    _LOG.info(
        "aelin_browser_confirm uid=%s workspace=%s action=%s scope=%s ok=%s error=%s restart=%s pre_restart=%s restart_error=%s remaining_pids=%s",
        int(current_user.id),
        workspace,
        action,
        scope,
        bool(result.get("ok")),
        str(result.get("error") or "")[:160],
        "1" if restart_meta is not None else "0",
        "1" if pre_restart_meta is not None else "0",
        str((restart_meta or pre_restart_meta or {}).get("error") or "")[:160],
        len(list((restart_meta or pre_restart_meta or {}).get("remaining_pids") or [])),
    )
    ok = bool(result.get("ok"))
    continued = False
    continuation_error = ""
    followup_result: dict[str, Any] = {}
    resume_query = str(payload.resume_query or "").strip()
    resume_request = payload.resume_request if isinstance(payload.resume_request, dict) else {}
    if ok and bool(payload.continue_after_confirm):
        try:
            if resume_request:
                followup_request_payload = dict(resume_request)
                followup_request_payload["workspace"] = workspace
                followup_request_payload["use_memory"] = bool(followup_request_payload.get("use_memory", True))
                if not str(followup_request_payload.get("query") or "").strip():
                    followup_request_payload["query"] = resume_query or "我已确认，请继续完成刚才的浏览器任务并直接给我结果。"
                followup_request = AelinChatRequest(**followup_request_payload)
            else:
                if not resume_query:
                    resume_query = "我已确认，请继续完成刚才的浏览器任务并直接给我结果。"
                followup_request = AelinChatRequest(
                    query=resume_query[:500],
                    workspace=workspace,
                    use_memory=True,
                    history=[],
                    images=[],
                )
            followup = _dispatch_aelin_chat(
                followup_request,
                db,
                current_user,
                event_cb=None,
            )
            followup_result = followup.model_dump() if followup is not None else {}
            continued = True
        except Exception as exc:
            continuation_error = str(exc)[:200]
            _LOG.warning(
                "aelin_browser_confirm continuation_failed uid=%s workspace=%s error=%s",
                int(current_user.id),
                workspace,
                continuation_error,
            )
    if ok:
        message = "已确认并执行浏览器步骤。"
        if continued:
            message = "已确认并继续执行任务。"
        elif continuation_error:
            message = f"已确认并执行浏览器步骤，但自动继续失败：{continuation_error}"
    else:
        message = f"确认后执行失败：{str(result.get('error') or 'unknown')[:160]}"
    return AelinBrowserConfirmResponse(
        ok=ok,
        message=message,
        requires_followup=ok,
        tool_result=result if isinstance(result, dict) else {},
        continued=continued,
        continuation_error=continuation_error,
        followup_result=followup_result,
        generated_at=datetime.now(timezone.utc),
    )
