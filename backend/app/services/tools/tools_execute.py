from __future__ import annotations

from typing import Any

from app.services.deepagents.delivery_paths import get_delivery_paths, resolve_virtual_or_local_path
from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.device.device_actions import execute_command_result


def tool_execute(_context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = dict(args or {})
    delivery_paths = get_delivery_paths(
        workspace=str(getattr(_context, "workspace", "default") or "default"),
        user_id=int(getattr(_context, "user_id", 0) or 0),
    )

    raw_cwd = str(payload.get("cwd") or "").strip()
    if not raw_cwd:
        payload["cwd"] = str(delivery_paths.workspace_dir)
    elif raw_cwd in {
        delivery_paths.workspace_virtual_path,
        delivery_paths.outputs_virtual_path,
    } or raw_cwd.startswith(f"{delivery_paths.workspace_virtual_path}/") or raw_cwd.startswith(f"{delivery_paths.outputs_virtual_path}/"):
        resolved_cwd = resolve_virtual_or_local_path(
            raw_cwd,
            delivery_paths,
            allow_workspace=True,
            allow_outputs=True,
        )
        resolved_cwd.mkdir(parents=True, exist_ok=True)
        payload["cwd"] = str(resolved_cwd)

    return execute_command_result(payload)
