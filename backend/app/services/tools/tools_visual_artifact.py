from __future__ import annotations

from typing import Any

from app.services.deepagents.tool_runtime import ToolRuntimeContext
from app.services.tools.tool_helpers import _result_error
from app.services.visual_artifacts import render_poster_artifact


def tool_render_poster_artifact(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    brief = " ".join(str(args.get("brief") or "").split()).strip()
    if not brief:
        return _result_error("render_poster_artifact requires a non-empty brief")

    preferred_format = str(args.get("preferred_format") or "auto").strip().lower() or "auto"
    filename_stem = str(args.get("filename_stem") or "").strip() or None
    try:
        result = render_poster_artifact(
            brief=brief,
            workspace=str(getattr(context, "workspace", "default") or "default"),
            preferred_format=preferred_format,
            filename_stem=filename_stem,
        )
    except Exception as exc:  # noqa: BLE001
        return _result_error(f"render_poster_artifact_failed:{str(exc)[:140]}")

    return {
        "ok": True,
        "summary": result.summary,
        "title": result.title,
        "format": result.format,
        "file_paths": list(result.file_paths),
        "artifact_count": len(result.artifacts),
        "artifacts": [
            {
                "path": artifact.path,
                "relative_path": artifact.relative_path,
                "name": artifact.name,
                "mime_type": artifact.mime_type,
                "size_bytes": artifact.size_bytes,
                "preview_kind": artifact.preview_kind,
                "content": artifact.content,
                "created_at": artifact.created_at,
                "modified_at": artifact.modified_at,
            }
            for artifact in result.artifacts
        ],
    }
