from __future__ import annotations

from typing import Any

from app.services.device import device_actions
from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.tools.tool_helpers import _result_error


def tool_screen_get(_context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    result = device_actions.screen_get_result(args)
    if result.get("ok"):
        return result
    return _result_error(str(result.get("error") or "screen_get_failed"))


def tool_device(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    _ = context
    result = device_actions.run_device_action(args)
    if result.get("ok"):
        return result
    return _result_error(str(result.get("error") or "device_action_failed"))

