from __future__ import annotations

from typing import Any

from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.device.device_actions import execute_command_result


def tool_execute(_context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    return execute_command_result(args)
