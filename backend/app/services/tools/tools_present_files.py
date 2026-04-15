from __future__ import annotations

from typing import Any

from app.services.artifact_files import normalize_tool_artifact_payloads
from app.services.deepagents.delivery_paths import get_delivery_paths, resolve_virtual_or_local_path
from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.tools.tool_helpers import _result_error


def tool_present_files(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    raw_filepaths = args.get("filepaths")
    if not isinstance(raw_filepaths, list) or not raw_filepaths:
        return _result_error("present_files requires a non-empty filepaths list")

    paths = get_delivery_paths(
        workspace=str(getattr(context, "workspace", "default") or "default"),
        user_id=int(getattr(context, "user_id", 0) or 0),
    )

    resolved_files: list[str] = []
    for raw_value in raw_filepaths:
        try:
            resolved = resolve_virtual_or_local_path(
                str(raw_value or ""),
                paths,
                default_root="outputs",
                allow_workspace=False,
                allow_outputs=True,
            )
        except ValueError as exc:
            return _result_error(f"present_files_invalid_path:{str(exc)[:140]}")

        if not resolved.exists():
            return _result_error(f"present_files_missing_file:{resolved}")
        if not resolved.is_file():
            return _result_error(f"present_files_not_a_file:{resolved}")
        resolved_files.append(str(resolved))

    artifacts = normalize_tool_artifact_payloads(
        [{"path": file_path} for file_path in resolved_files]
    )
    if not artifacts:
        return _result_error("present_files_no_previewable_files")

    return {
        "ok": True,
        "summary": f"presented {len(artifacts)} file(s)",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "file_paths": resolved_files,
    }
