from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.services.device.device_center import (
    activate_desktop_module,
    capture_device_screen,
    execute_desktop_command,
    DesktopPluginActionError,
    DeviceScreenCaptureError,
    open_desktop_external_url,
)
from app.services.device.device_contract import build_device_status_contract


def _safe_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:  # noqa: BLE001
        out = default
    return max(low, min(high, out))


def is_http_url(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def device_status_result() -> dict[str, Any]:
    snapshot = build_device_status_contract()
    return {
        "ok": True,
        "platform": str(snapshot.get("platform") or "unknown"),
        "capabilities": dict(snapshot.get("capabilities") or {}),
        "notes": list(snapshot.get("notes") or []),
        "desktop_plugin_reachable": bool(snapshot.get("desktop_plugin_reachable")),
        "desktop_plugin_configured": bool(snapshot.get("desktop_plugin_configured")),
        "summary": (
            f"platform={str(snapshot.get('platform') or 'unknown')}; "
            f"plugin_reachable={1 if bool(snapshot.get('desktop_plugin_reachable')) else 0}"
        ),
    }


def open_url_result(url: str) -> dict[str, Any]:
    clean_url = str(url or "").strip()
    if not clean_url:
        return {"ok": False, "error": "missing url"}
    if not is_http_url(clean_url):
        return {"ok": False, "error": "invalid_url_scheme"}
    try:
        result = open_desktop_external_url(clean_url)
    except DesktopPluginActionError as exc:
        return {"ok": False, "error": f"desktop_open_url_failed:{exc.detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"desktop_open_url_failed:{str(exc)[:160]}"}
    return {
        "ok": True,
        "url": str(result.get("url") or clean_url),
        "opened": bool(result.get("opened")),
        "detail": str(result.get("detail") or ""),
        "summary": f"已尝试打开链接: {str(result.get('url') or clean_url)[:220]}",
    }


def open_aelin_result(route: str = "/") -> dict[str, Any]:
    clean_route = str(route or "/").strip() or "/"
    try:
        result = activate_desktop_module(clean_route)
    except DesktopPluginActionError as exc:
        return {"ok": False, "error": f"desktop_open_aelin_failed:{exc.detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"desktop_open_aelin_failed:{str(exc)[:160]}"}
    return {
        "ok": True,
        "route": str(result.get("route") or clean_route),
        "opened": bool(result.get("opened")),
        "detail": str(result.get("detail") or ""),
        "summary": f"Aelin 已切换到 {str(result.get('route') or clean_route)[:120]}",
    }


def screen_get_result(args: dict[str, Any]) -> dict[str, Any]:
    display_id = str(args.get("display_id") or "").strip()[:64]
    max_edge = _safe_int(args.get("max_edge"), 1280, low=640, high=4096)
    fmt = "png" if str(args.get("format") or "").strip().lower() == "png" else "jpeg"
    quality = _safe_int(args.get("quality"), 72, low=35, high=95)
    try:
        shot = capture_device_screen(
            display_id=display_id,
            max_edge=max_edge,
            image_format=fmt,
            quality=quality,
        )
    except DeviceScreenCaptureError as exc:
        return {"ok": False, "error": f"screen_get_failed:{exc.detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"screen_get_failed:{str(exc)[:160]}"}

    return {
        "ok": True,
        "data_url": str(shot.get("data_url") or ""),
        "name": str(shot.get("name") or "")[:120],
        "width": max(0, int(shot.get("width") or 0)),
        "height": max(0, int(shot.get("height") or 0)),
        "source_display": str(shot.get("source_display") or "")[:64],
        "captured_at": str(shot.get("captured_at") or "")[:64],
    }


def execute_command_result(args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if not command:
        return {"ok": False, "error": "missing_command"}

    cwd = str(args.get("cwd") or "").strip()
    try:
        timeout_ms = int(args.get("timeout_ms") or 0)
    except Exception:
        timeout_ms = 0

    try:
        result = execute_desktop_command(
            command=command,
            cwd=cwd,
            timeout_ms=timeout_ms or None,
        )
    except DesktopPluginActionError as exc:
        return {"ok": False, "error": exc.detail}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"desktop_execute_failed:{str(exc)[:160]}"}

    exit_code = result.get("exit_code")
    timed_out = bool(result.get("timed_out"))
    summary = str(result.get("summary") or "").strip()
    ok = not timed_out and int(exit_code if exit_code is not None else 0) == 0
    payload = {
        "ok": ok,
        "command": str(result.get("command") or command),
        "cwd": str(result.get("cwd") or cwd),
        "exit_code": exit_code,
        "stdout": str(result.get("stdout") or ""),
        "stderr": str(result.get("stderr") or ""),
        "timed_out": timed_out,
        "summary": summary or (
            "command succeeded"
            if ok
            else ("command timed out" if timed_out else f"command failed with exit code {exit_code}")
        ),
    }
    artifacts = result.get("artifacts")
    if isinstance(artifacts, list):
        payload["artifacts"] = [item for item in artifacts if isinstance(item, dict)]
        payload["artifact_count"] = len(payload["artifacts"])
    if timed_out:
        payload["error"] = "command_timed_out"
    elif not ok and exit_code is not None:
        payload["error"] = f"command_exit_{exit_code}"
    return payload


def run_device_action(args: dict[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "").strip().lower()
    if action == "status":
        return device_status_result()
    if action == "open_url":
        return open_url_result(str(args.get("url") or ""))
    if action == "open_aelin":
        return open_aelin_result(str(args.get("route") or "/"))
    return {
        "ok": False,
        "error": "unsupported device action: allowed actions are 'status', 'open_url', 'open_aelin'",
    }
