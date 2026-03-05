from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AgentMemoryNote, User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinDeviceCapabilitiesResponse,
    AelinDeviceModeApplyRequest,
    AelinDeviceModeApplyResponse,
    AelinDeviceOptimizeResponse,
    AelinDeviceProcessActionRequest,
    AelinDeviceProcessActionResponse,
    AelinDeviceProcessResponse,
    AelinDeviceScreenCaptureRequest,
    AelinDeviceScreenCaptureResponse,
)
from app.services.device_center import (
    apply_device_mode as device_apply_mode,
    capture_device_screen as device_capture_screen,
    collect_device_process_items as device_collect_process_items,
    DeviceScreenCaptureError,
    device_capabilities as device_capabilities_info,
    device_is_windows as is_windows_runtime,
    get_process_name_by_pid_windows as device_process_name_by_pid,
    normalize_device_mode as normalize_mode_value,
    set_process_priority as device_set_process_priority,
)

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None


router = APIRouter(prefix="/aelin", tags=["aelin"])

_DEVICE_MODE_SOURCE = "device_mode_state"
_DEVICE_ALLOWED_PROCESS_ACTIONS = {"terminate", "set_low_priority", "set_high_priority"}


def _json_from_text(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_device_mode_state(db: Session, *, user_id: int) -> tuple[AgentMemoryNote | None, dict[str, Any]]:
    row = db.scalar(
        select(AgentMemoryNote)
        .where(AgentMemoryNote.user_id == user_id, AgentMemoryNote.source == _DEVICE_MODE_SOURCE)
        .order_by(AgentMemoryNote.updated_at.desc(), AgentMemoryNote.id.desc())
        .limit(1)
    )
    if row is None:
        return None, {}
    return row, _json_from_text(row.content or "{}")


def _save_device_mode_state(
    db: Session,
    *,
    user_id: int,
    existing: AgentMemoryNote | None,
    payload: dict[str, Any],
) -> AgentMemoryNote:
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    row = existing
    if row is None:
        row = AgentMemoryNote(
            user_id=user_id,
            kind="system",
            source=_DEVICE_MODE_SOURCE,
            content=content,
        )
        db.add(row)
        return row
    row.kind = "system"
    row.source = _DEVICE_MODE_SOURCE
    row.content = content
    db.add(row)
    return row


@router.post("/device/screen/capture", response_model=AelinDeviceScreenCaptureResponse)
def capture_device_screen(
    payload: AelinDeviceScreenCaptureRequest | None = None,
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    request = payload or AelinDeviceScreenCaptureRequest()
    try:
        result = device_capture_screen(
            display_id=request.display_id,
            max_edge=request.max_edge,
            image_format=request.image_format,
            quality=request.quality,
            mode=request.mode,
            selection_timeout_ms=request.selection_timeout_ms,
        )
    except DeviceScreenCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return AelinDeviceScreenCaptureResponse(
        data_url=str(result.get("data_url") or "").strip(),
        name=str(result.get("name") or "").strip()[:120],
        width=max(0, int(result.get("width") or 0)),
        height=max(0, int(result.get("height") or 0)),
        source_display=str(result.get("source_display") or "").strip()[:64],
        captured_at=str(result.get("captured_at") or datetime.now(timezone.utc).isoformat())[:64],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/device/processes", response_model=AelinDeviceProcessResponse)
def list_device_processes(
    sort_by: str = Query(default="cpu", min_length=1, max_length=16),
    limit: int = Query(default=40, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    sort_key = "memory" if str(sort_by or "").strip().lower() == "memory" else "cpu"
    items = device_collect_process_items(sort_by=sort_key, limit=limit)
    platform_name, _, notes = device_capabilities_info()
    filter_context = {
        "sort_by": sort_key,
        "requested_limit": str(int(limit or 40)),
        "runtime": platform_name,
        "psutil": "available" if psutil is not None else "missing",
    }
    empty_reason = ""
    if not items:
        empty_reason = (
            "no-process-data: psutil unavailable"
            if psutil is None
            else "no-process-data: process probe returned no rows"
        )
        if notes:
            filter_context["notes"] = "; ".join(notes[:2])
    return AelinDeviceProcessResponse(
        sort_by=sort_key,
        total=len(items),
        items=items,
        platform=platform_name,
        filter_context=filter_context,
        empty_reason=empty_reason,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/device/processes/{pid}/action", response_model=AelinDeviceProcessActionResponse)
def run_device_process_action(
    pid: int,
    payload: AelinDeviceProcessActionRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    action = str(payload.action or "").strip().lower()
    if action not in _DEVICE_ALLOWED_PROCESS_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_ACTION",
                "message": f"unsupported action: {action}",
                "allowed_actions": sorted(_DEVICE_ALLOWED_PROCESS_ACTIONS),
            },
        )

    proc_name = ""
    proc = None
    if psutil is not None:
        try:
            proc = psutil.Process(int(pid))
            proc_name = str(proc.name() or "").strip().lower()
        except Exception:
            proc = None
    if not proc_name and is_windows_runtime():
        proc_name = device_process_name_by_pid(int(pid))

    critical_names = {
        "system", "idle", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "svchost.exe",
        "csrss", "wininit", "services", "lsass", "svchost",
    }
    if action == "terminate" and proc_name in critical_names:
        return AelinDeviceProcessActionResponse(
            pid=int(pid),
            action=action,
            ok=False,
            detail=f"blocked critical process: {proc_name}",
            generated_at=datetime.now(timezone.utc),
        )

    if action == "terminate":
        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2.5)
                except Exception:
                    proc.kill()
                return AelinDeviceProcessActionResponse(
                    pid=int(pid),
                    action=action,
                    ok=True,
                    detail="process terminated",
                    generated_at=datetime.now(timezone.utc),
                )
            except Exception as exc:
                return AelinDeviceProcessActionResponse(
                    pid=int(pid),
                    action=action,
                    ok=False,
                    detail=str(exc),
                    generated_at=datetime.now(timezone.utc),
                )

        if is_windows_runtime():
            try:
                tk = subprocess.run(
                    ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    encoding="utf-8",
                    errors="ignore",
                )
                detail = (tk.stdout or tk.stderr or "").strip()
                return AelinDeviceProcessActionResponse(
                    pid=int(pid),
                    action=action,
                    ok=bool(tk.returncode == 0),
                    detail=detail or ("process terminated" if tk.returncode == 0 else "taskkill failed"),
                    generated_at=datetime.now(timezone.utc),
                )
            except Exception as exc:
                return AelinDeviceProcessActionResponse(
                    pid=int(pid),
                    action=action,
                    ok=False,
                    detail=str(exc),
                    generated_at=datetime.now(timezone.utc),
                )

        return AelinDeviceProcessActionResponse(
            pid=int(pid),
            action=action,
            ok=False,
            detail="process terminate unavailable on this runtime",
            generated_at=datetime.now(timezone.utc),
        )

    target = "high" if action == "set_high_priority" else "low"
    ok, detail = device_set_process_priority(int(pid), target)
    return AelinDeviceProcessActionResponse(
        pid=int(pid),
        action=action,
        ok=ok,
        detail=detail,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/device/processes/optimize", response_model=AelinDeviceOptimizeResponse)
def optimize_device_processes(
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    candidates = device_collect_process_items(sort_by="cpu", limit=40)
    steps: list[str] = []
    warnings: list[str] = []
    affected: list[int] = []
    for row in candidates:
        if row.anomaly_score < 1.6:
            continue
        if not row.safe_to_terminate:
            continue
        ok, detail = device_set_process_priority(int(row.pid), "low")
        if ok:
            affected.append(int(row.pid))
            steps.append(f"{row.name} (PID {row.pid}) -> low priority")
        else:
            warnings.append(f"{row.name} (PID {row.pid}) 调整失败: {detail}")
        if len(affected) >= 4:
            break
    if not steps:
        steps.append("没有可优化的高占用用户进程。")
    return AelinDeviceOptimizeResponse(
        optimized_count=len(affected),
        affected_pids=affected,
        steps=steps[:12],
        warnings=warnings[:12],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/device/capabilities", response_model=AelinDeviceCapabilitiesResponse)
def get_device_capabilities(
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    platform_name, capabilities, notes = device_capabilities_info()
    return AelinDeviceCapabilitiesResponse(
        platform=platform_name,
        capabilities=capabilities,
        notes=notes,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/device/mode", response_model=AelinDeviceModeApplyResponse)
def get_device_mode_state(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _, state = _load_device_mode_state(db, user_id=current_user.id)
    mode = normalize_mode_value(str(state.get("mode") or "normal"))
    status = str(state.get("status") or "applied").strip().lower() or "applied"
    summary = str(state.get("summary") or f"当前模式: {mode}").strip()
    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
    warnings = state.get("warnings") if isinstance(state.get("warnings"), list) else []
    return AelinDeviceModeApplyResponse(
        mode=mode,
        status=status,
        summary=summary,
        steps=[str(x) for x in steps][:12],
        warnings=[str(x) for x in warnings][:12],
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/device/mode/apply", response_model=AelinDeviceModeApplyResponse)
def apply_device_mode(
    payload: AelinDeviceModeApplyRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    requested_mode = str(payload.mode or "").strip().lower()
    mode, status, summary, steps, warnings = device_apply_mode(payload.mode)
    allowed_requested_modes = {"meeting", "focus", "sleep", "normal", "default"}
    if requested_mode and requested_mode not in allowed_requested_modes:
        status = "degraded"
        warnings = [*warnings, f"requested mode '{requested_mode}' is not supported on this runtime; fallback to '{mode}'"]
        summary = f"{mode} mode applied as fallback from '{requested_mode}'"

    existing, _ = _load_device_mode_state(db, user_id=current_user.id)
    state = {
        "mode": mode,
        "status": status,
        "summary": summary,
        "steps": steps[:12],
        "warnings": warnings[:12],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_device_mode_state(db, user_id=current_user.id, existing=existing, payload=state)
    db.commit()
    return AelinDeviceModeApplyResponse(
        mode=mode,
        status=status,
        summary=summary,
        steps=steps[:12],
        warnings=warnings[:12],
        generated_at=datetime.now(timezone.utc),
    )
