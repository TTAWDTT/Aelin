from __future__ import annotations

from typing import Any

from app.services.device.device_center import device_status_snapshot


BASE_DEEPAGENTS_TOOLS = [
    "device",
    "screen_get",
]

SUPPORTED_DEVICE_ACTIONS = [
    "status",
    "open_url",
    "open_aelin",
]


def supported_deepagents_tools(snapshot: dict[str, Any] | None = None) -> list[str]:
    state = snapshot or device_status_snapshot()
    capabilities = dict(state.get("capabilities") or {})
    tools = list(BASE_DEEPAGENTS_TOOLS)
    if bool(capabilities.get("desktop_execute_command")):
        tools.append("execute")
    return tools


def build_device_status_contract(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    state = snapshot or device_status_snapshot()
    return {
        "platform": str(state.get("platform") or "unknown"),
        "capabilities": dict(state.get("capabilities") or {}),
        "notes": list(state.get("notes") or []),
        "desktop_plugin_reachable": bool(state.get("desktop_plugin_reachable")),
        "desktop_plugin_configured": bool(state.get("desktop_plugin_configured")),
    }
