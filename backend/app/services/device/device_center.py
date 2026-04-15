from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.artifact_files import normalize_tool_artifact_payloads
from app.settings import settings

REGION_CAPTURE_TIMEOUT_BUFFER_S = 8.0  # buffer for Snipping Tool UI + clipboard polling latency


class DeviceScreenCaptureError(RuntimeError):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(str(detail or "device_screen_capture_error"))
        self.status_code = max(400, int(status_code or 500))
        self.detail = str(detail or "device_screen_capture_error")[:220]


class DesktopPluginActionError(RuntimeError):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(str(detail or "desktop_plugin_action_error"))
        self.status_code = max(400, int(status_code or 500))
        self.detail = str(detail or "desktop_plugin_action_error")[:220]


def _desktop_plugin_config() -> dict[str, Any]:
    return {
        "base_url": str(getattr(settings, "desktop_plugin_base_url", "") or "").strip().rstrip("/"),
        "timeout_seconds": max(2.0, float(getattr(settings, "desktop_plugin_timeout_seconds", 12.0) or 12.0)),
        "headers": (
            {"x-aelin-token": str(getattr(settings, "desktop_plugin_token", "") or "").strip()}
            if str(getattr(settings, "desktop_plugin_token", "") or "").strip()
            else {}
        ),
    }


def _desktop_plugin_error_detail(resp: httpx.Response) -> str:
    text = ""
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        text = str(payload.get("detail") or payload.get("message") or "").strip()
    if not text:
        text = str(resp.text or "").strip()
    if not text:
        text = f"status={resp.status_code}"
    return text[:180]


def _desktop_plugin_client(*, timeout: float) -> httpx.Client:
    # Local plugin calls must bypass system proxies/VPN env vars.
    return httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)


def _desktop_plugin_post(path: str, payload: dict[str, Any], *, timeout_s: float | None = None) -> dict[str, Any]:
    cfg = _desktop_plugin_config()
    base_url = str(cfg["base_url"] or "")
    if not base_url:
        raise DesktopPluginActionError(status_code=503, detail="desktop_plugin_unconfigured")
    url = f"{base_url}{path}"
    timeout_value = max(2.0, float(timeout_s if timeout_s is not None else cfg["timeout_seconds"]))
    try:
        with _desktop_plugin_client(timeout=timeout_value) as client:
            resp = client.post(url, json=payload, headers=dict(cfg["headers"] or {}))
    except Exception as exc:
        raise DesktopPluginActionError(
            status_code=503,
            detail=f"desktop_plugin_unreachable: {str(exc)[:180]}",
        ) from exc

    if int(resp.status_code) >= 400:
        raise DesktopPluginActionError(
            status_code=502,
            detail=f"desktop_plugin_action_failed: {_desktop_plugin_error_detail(resp)}",
        )
    try:
        raw = resp.json()
    except Exception as exc:
        raise DesktopPluginActionError(status_code=502, detail="desktop_plugin_invalid_json") from exc
    if not isinstance(raw, dict):
        raise DesktopPluginActionError(status_code=502, detail="desktop_plugin_invalid_payload")
    return raw


def desktop_plugin_health() -> bool:
    cfg = _desktop_plugin_config()
    base_url = str(cfg["base_url"] or "")
    if not base_url:
        return False
    try:
        with _desktop_plugin_client(timeout=min(5.0, float(cfg["timeout_seconds"]))) as client:
            resp = client.get(f"{base_url}/healthz", headers=dict(cfg["headers"] or {}))
    except Exception:
        return False
    return int(resp.status_code) < 400


def capture_device_screen(
    *,
    display_id: str = "",
    max_edge: int = 1280,
    image_format: str = "jpeg",
    quality: int = 72,
    mode: str = "fullscreen",
    selection_timeout_ms: int = 45_000,
) -> dict[str, Any]:
    timeout_s = float(_desktop_plugin_config()["timeout_seconds"])
    mode_clean = str(mode or "fullscreen").strip().lower()
    if mode_clean not in {"fullscreen", "region"}:
        mode_clean = "fullscreen"
    selection_timeout_clean = max(5_000, min(180_000, int(selection_timeout_ms or 45_000)))
    if mode_clean == "region":
        timeout_s = max(timeout_s, (selection_timeout_clean / 1000.0) + REGION_CAPTURE_TIMEOUT_BUFFER_S)
    payload: dict[str, Any] = {
        "max_edge": max(640, min(4096, int(max_edge or 1280))),
        "format": "png" if str(image_format or "").strip().lower() == "png" else "jpeg",
        "mode": mode_clean,
        "exclude_aelin_windows": mode_clean == "fullscreen",
    }
    if mode_clean == "region":
        payload["selection_timeout_ms"] = selection_timeout_clean
    if payload["format"] == "jpeg":
        payload["quality"] = max(35, min(95, int(quality or 72)))
    display_clean = str(display_id or "").strip()[:64]
    if display_clean:
        payload["display_id"] = display_clean

    try:
        raw = _desktop_plugin_post("/v1/device/screen/capture", payload, timeout_s=timeout_s)
    except DesktopPluginActionError as exc:
        raise DeviceScreenCaptureError(status_code=exc.status_code, detail=exc.detail) from exc

    data_url = str(raw.get("data_url") or "").strip()
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise DeviceScreenCaptureError(status_code=502, detail="desktop_plugin_invalid_image_payload")
    max_data_len = max(
        200_000,
        int(getattr(settings, "desktop_plugin_capture_max_data_url_length", 3_000_000) or 3_000_000),
    )
    if len(data_url) > max_data_len:
        raise DeviceScreenCaptureError(
            status_code=502,
            detail=f"desktop_plugin_image_too_large: {len(data_url)}",
        )

    try:
        width = max(0, int(raw.get("width") or 0))
    except Exception:
        width = 0
    try:
        height = max(0, int(raw.get("height") or 0))
    except Exception:
        height = 0

    return {
        "data_url": data_url,
        "name": str(raw.get("name") or "").strip()[:120],
        "width": width,
        "height": height,
        "source_display": str(raw.get("source_display") or "").strip()[:64],
        "captured_at": str(raw.get("captured_at") or datetime.now(timezone.utc).isoformat())[:64],
        "saved_path": str(raw.get("saved_path") or "").strip()[:1024],
    }


def open_desktop_external_url(url: str) -> dict[str, Any]:
    url_clean = str(url or "").strip()
    if not url_clean:
        raise DesktopPluginActionError(status_code=400, detail="missing_url")
    raw = _desktop_plugin_post("/v1/desktop/url/open", {"url": url_clean})
    return _normalize_plugin_action_result(raw, primary_value=str(raw.get("url") or url_clean)[:2000], primary_key="url")


def open_desktop_local_path(path_value: str) -> dict[str, Any]:
    path_clean = str(path_value or "").strip()
    if not path_clean:
        raise DesktopPluginActionError(status_code=400, detail="missing_path")
    raw = _desktop_plugin_post("/v1/desktop/path/open", {"path": path_clean})
    return _normalize_plugin_action_result(
        raw,
        primary_value=str(raw.get("path") or path_clean)[:2000],
        primary_key="path",
    )


def activate_desktop_module(route: str = "/") -> dict[str, Any]:
    route_clean = str(route or "/").strip() or "/"
    raw = _desktop_plugin_post("/v1/desktop/app/activate", {"route": route_clean})
    return _normalize_plugin_action_result(raw, primary_value=str(raw.get("route") or route_clean)[:120], primary_key="route")


def _truncate_output(value: Any, limit: int) -> str:
    text = str(value or "")
    max_chars = max(256, int(limit or 0))
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n...[truncated {omitted} chars]"


def execute_desktop_command(
    *,
    command: str,
    shell: str = "",
    cwd: str = "",
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "desktop_plugin_execute_enabled", False)):
        raise DesktopPluginActionError(status_code=403, detail="desktop_execute_disabled")

    command_clean = str(command or "").strip()
    if not command_clean:
        raise DesktopPluginActionError(status_code=400, detail="missing_command")

    timeout_default_ms = int(
        max(1.0, float(getattr(settings, "desktop_plugin_execute_timeout_seconds", 20.0) or 20.0))
        * 1000
    )
    timeout_clean = max(1_000, min(120_000, int(timeout_ms or timeout_default_ms)))
    output_limit = int(getattr(settings, "desktop_plugin_execute_max_output_chars", 12_000) or 12_000)
    payload: dict[str, Any] = {
        "command": command_clean,
        "timeout_ms": timeout_clean,
    }
    shell_clean = str(shell or "").strip().lower()
    if shell_clean:
        payload["shell"] = shell_clean
    cwd_clean = str(cwd or "").strip()
    if cwd_clean:
        payload["cwd"] = cwd_clean

    raw = _desktop_plugin_post(
        "/v1/desktop/command/execute",
        payload,
        timeout_s=max(
            float(_desktop_plugin_config()["timeout_seconds"]),
            (timeout_clean / 1000.0) + 3.0,
        ),
    )

    try:
        exit_code_raw = raw.get("exit_code")
        exit_code = None if exit_code_raw is None else int(exit_code_raw)
    except Exception:
        exit_code = None

    timed_out = bool(raw.get("timed_out"))
    stdout = _truncate_output(raw.get("stdout"), output_limit)
    stderr = _truncate_output(raw.get("stderr"), output_limit)
    summary = str(raw.get("summary") or "").strip()[:200]
    resolved_cwd = str(raw.get("cwd") or cwd_clean)[:1024]
    resolved_shell = str(raw.get("shell") or shell_clean)[:32]
    artifacts = raw.get("artifacts")
    normalized_artifacts = normalize_tool_artifact_payloads(artifacts)

    result = {
        "command": command_clean,
        "shell": resolved_shell,
        "cwd": resolved_cwd,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "summary": summary or (
            f"command exited with code {exit_code}"
            if exit_code is not None
            else ("command timed out" if timed_out else "command finished")
        ),
    }
    if normalized_artifacts:
        result["artifacts"] = normalized_artifacts
        result["artifact_count"] = len(normalized_artifacts)
    return result


def _normalize_plugin_action_result(raw: dict[str, Any], *, primary_value: str, primary_key: str) -> dict[str, Any]:
    return {
        primary_key: primary_value,
        "opened": bool(raw.get("opened", raw.get("activated", True))),
        "detail": str(raw.get("detail") or "ok")[:200],
    }


def device_status_snapshot() -> dict[str, Any]:
    platform_name = platform.system().strip().lower() or "unknown"
    cfg = _desktop_plugin_config()
    desktop_plugin_configured = bool(cfg["base_url"])
    capabilities = {
        "desktop_plugin_configured": desktop_plugin_configured,
        "desktop_open_url": desktop_plugin_configured,
        "desktop_activate_module": desktop_plugin_configured,
        "desktop_execute_command": (
            desktop_plugin_configured
            and bool(getattr(settings, "desktop_plugin_execute_enabled", False))
        ),
    }
    notes: list[str] = []
    if not desktop_plugin_configured:
        notes.append("desktop plugin unconfigured: open_url / activate_module unavailable")
    elif not bool(getattr(settings, "desktop_plugin_execute_enabled", False)):
        notes.append("desktop command execution disabled")
    return {
        "platform": platform_name,
        "capabilities": capabilities,
        "notes": notes,
        "desktop_plugin_configured": desktop_plugin_configured,
        "desktop_plugin_reachable": desktop_plugin_health(),
    }
