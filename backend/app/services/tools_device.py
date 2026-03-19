from __future__ import annotations

from typing import Any


def tool_screen_get(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Screen capture tool implementation extracted from
    AelinToolHub._tool_screen_get.

    Behaviour is kept identical and shared helpers are reused via lazy imports.
    """

    from app.services.aelin_tools import (
        _result_error,
        _result_ok,
        _safe_int,
        DeviceScreenCaptureError,
        device_capture_screen,
    )

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


def tool_device(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Unified device tool implementation extracted from AelinToolHub._tool_device.

    This keeps the public behaviour identical while continuing to dispatch to
    the hub's internal helpers so that existing tests which monkeypatch
    `_tool_device_status` / `_tool_desktop_open_url` / `_tool_desktop_open_aelin`
    remain valid.
    """

    from app.services.aelin_tools import _result_error

    action = str(args.get("action") or "").strip().lower()
    if action == "status":
        return hub._tool_device_status(args)
    if action == "open_url":
        return hub._tool_desktop_open_url(args)
    if action == "open_aelin":
        return hub._tool_desktop_open_aelin(args)
    return _result_error("unsupported device action")

