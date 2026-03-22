from __future__ import annotations

from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

from app.services.device_center import (
    activate_desktop_module,
    capture_device_screen as device_capture_screen,
    DesktopPluginActionError,
    DeviceScreenCaptureError,
    device_status_snapshot,
    open_desktop_external_url,
)
from app.services.tool_helpers import _result_error, _result_ok, _safe_int

if TYPE_CHECKING:
    from app.services.aelin_tools import AelinToolHub


def tool_screen_get(_hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    display_id = str(args.get("display_id") or "").strip()[:64]
    max_edge = _safe_int(args.get("max_edge"), 1280, low=640, high=4096)
    fmt = "png" if str(args.get("format") or "").strip().lower() == "png" else "jpeg"
    quality = _safe_int(args.get("quality"), 72, low=35, high=95)
    try:
        shot = device_capture_screen(
            display_id=display_id,
            max_edge=max_edge,
            image_format=fmt,
            quality=quality,
        )
    except DeviceScreenCaptureError as exc:
        return _result_error(f"screen_get_failed:{exc.detail}")
    except Exception as exc:
        return _result_error(f"screen_get_failed:{str(exc)[:160]}")

    return _result_ok(
        data_url=str(shot.get("data_url") or ""),
        name=str(shot.get("name") or "")[:120],
        width=max(0, int(shot.get("width") or 0)),
        height=max(0, int(shot.get("height") or 0)),
        source_display=str(shot.get("source_display") or "")[:64],
        captured_at=str(shot.get("captured_at") or "")[:64],
    )


def tool_device(_hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    def _is_http_url(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        parsed = urlparse(text)
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)

    action = str(args.get("action") or "").strip().lower()
    if action == "status":
        snapshot = device_status_snapshot()
        return _result_ok(
            platform=str(snapshot.get("platform") or "unknown"),
            capabilities=dict(snapshot.get("capabilities") or {}),
            notes=list(snapshot.get("notes") or []),
            desktop_plugin_reachable=bool(snapshot.get("desktop_plugin_reachable")),
            desktop_plugin_configured=bool(snapshot.get("desktop_plugin_configured")),
            summary=(
                f"platform={str(snapshot.get('platform') or 'unknown')}; "
                f"plugin_reachable={1 if bool(snapshot.get('desktop_plugin_reachable')) else 0}"
            ),
        )
    if action == "open_url":
        url = str(args.get("url") or "").strip()
        if not url:
            return _result_error("missing url")
        if not _is_http_url(url):
            return _result_error("invalid_url_scheme")
        try:
            result = open_desktop_external_url(url)
        except DesktopPluginActionError as exc:
            return _result_error(f"desktop_open_url_failed:{exc.detail}")
        except Exception as exc:
            return _result_error(f"desktop_open_url_failed:{str(exc)[:160]}")
        return _result_ok(
            url=str(result.get("url") or url),
            opened=bool(result.get("opened")),
            detail=str(result.get("detail") or ""),
            summary=f"已尝试打开链接: {str(result.get('url') or url)[:220]}",
        )
    if action == "open_aelin":
        route = str(args.get("route") or "/").strip() or "/"
        try:
            result = activate_desktop_module(route)
        except DesktopPluginActionError as exc:
            return _result_error(f"desktop_open_aelin_failed:{exc.detail}")
        except Exception as exc:
            return _result_error(f"desktop_open_aelin_failed:{str(exc)[:160]}")
        return _result_ok(
            route=str(result.get("route") or route),
            opened=bool(result.get("opened")),
            detail=str(result.get("detail") or ""),
            summary=f"Aelin 已切换到 {str(result.get('route') or route)[:120]}",
        )
    # Help DeepAgents understand exactly which actions are valid so it can
    # correct bad calls instead of repeating them.
    return _result_error(
        "unsupported device action: allowed actions are 'status', 'open_url', 'open_aelin'"
    )
