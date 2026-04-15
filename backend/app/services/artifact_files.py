from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from app.settings import settings


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]


class LocalArtifactAccessError(RuntimeError):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(str(detail or "local_artifact_access_error"))
        self.status_code = max(400, int(status_code or 500))
        self.detail = str(detail or "local_artifact_access_error")[:220]


def _resolve_setting_path(raw_value: str, *, base_dir: Path) -> Path:
    text = str(raw_value or "").strip()
    if not text:
        return base_dir.resolve()
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    else:
        path = path.resolve()
    return path


def _allowed_artifact_roots() -> list[Path]:
    roots: list[Path] = [_REPO_ROOT.resolve()]
    for raw_value in (
        getattr(settings, "media_dir", ""),
        getattr(settings, "aelin_attachment_storage_dir", ""),
    ):
        resolved = _resolve_setting_path(str(raw_value or ""), base_dir=_BACKEND_DIR)
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_local_artifact_path(path_value: str) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise LocalArtifactAccessError(status_code=400, detail="missing_artifact_path")

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_REPO_ROOT / path).resolve()
    else:
        path = path.resolve()

    if not path.exists():
        raise LocalArtifactAccessError(status_code=404, detail="artifact_not_found")
    if not path.is_file():
        raise LocalArtifactAccessError(status_code=400, detail="artifact_path_is_not_file")

    if not any(_is_relative_to(path, root) for root in _allowed_artifact_roots()):
        raise LocalArtifactAccessError(status_code=403, detail="artifact_path_outside_allowed_roots")

    return path


def artifact_media_type(path: Path) -> str:
    media_type, _encoding = mimetypes.guess_type(str(path))
    return str(media_type or "application/octet-stream")


def _normalize_preview_kind(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {
        "markdown",
        "html",
        "svg",
        "json",
        "text",
        "image-data-url",
        "pdf-data-url",
        "unknown",
    }:
        return text
    return ""


def _infer_preview_kind(*, path: Path | None, mime_type: str) -> str:
    suffix = str(path.suffix if path is not None else "").strip().lower()
    mime = str(mime_type or "").strip().lower()
    if mime == "application/pdf" or suffix == ".pdf":
        return "pdf-data-url"
    if mime == "image/svg+xml" or suffix == ".svg":
        return "svg"
    if mime.startswith("image/"):
        return "image-data-url"
    if mime == "text/markdown" or suffix in {".md", ".markdown"}:
        return "markdown"
    if mime == "application/json" or suffix == ".json":
        return "json"
    if mime == "text/html" or suffix in {".html", ".htm"}:
        return "html"
    if mime.startswith("text/") or suffix in {
        ".txt",
        ".log",
        ".csv",
        ".tsv",
        ".xml",
        ".yaml",
        ".yml",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".css",
    }:
        return "text"
    return "unknown"


def _artifact_relative_path(path: Path) -> str:
    for root in _allowed_artifact_roots():
        if _is_relative_to(path, root):
            return path.relative_to(root).as_posix()
    return path.name


def _safe_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return max(0, parsed)


def _safe_iso_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    return text[:64]


def _stat_timestamp(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except Exception:
        return ""


def normalize_tool_artifact_payload(item: Any, *, inline_content_limit_chars: int = 16_000) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    raw_path = str(
        item.get("path")
        or item.get("abs_path")
        or item.get("file_path")
        or item.get("relative_path")
        or ""
    ).strip()
    raw_name = str(item.get("name") or "").strip()
    raw_relative_path = str(item.get("relative_path") or "").strip()
    raw_content = str(item.get("content") or "")
    raw_binary_base64 = str(item.get("binary_base64") or "").strip()
    raw_mime_type = str(item.get("mime_type") or item.get("mimeType") or "").strip()
    raw_preview_kind = _normalize_preview_kind(item.get("preview_kind") or item.get("previewKind"))
    raw_created_at = _safe_iso_timestamp(item.get("created_at") or item.get("createdAt"))
    raw_modified_at = _safe_iso_timestamp(item.get("modified_at") or item.get("modifiedAt"))

    resolved_local_path: Path | None = None
    if raw_path:
        try:
            resolved_local_path = resolve_local_artifact_path(raw_path)
        except LocalArtifactAccessError:
            resolved_local_path = None

    if resolved_local_path is not None:
        mime_type = raw_mime_type or artifact_media_type(resolved_local_path)
        preview_kind = raw_preview_kind or _infer_preview_kind(path=resolved_local_path, mime_type=mime_type)
        stat_size = _safe_positive_int(resolved_local_path.stat().st_size)
        return {
            "path": str(resolved_local_path),
            "relative_path": raw_relative_path or _artifact_relative_path(resolved_local_path),
            "name": raw_name or resolved_local_path.name,
            "mime_type": mime_type,
            "size_bytes": _safe_positive_int(item.get("size_bytes")) or stat_size,
            "preview_kind": preview_kind,
            "content": "",
            "created_at": raw_created_at,
            "modified_at": raw_modified_at or _stat_timestamp(resolved_local_path),
        }

    if not raw_path and not raw_name and not raw_content and not raw_binary_base64:
        return None

    fallback_path = raw_path or raw_name or "artifact"
    fallback_file = Path(fallback_path)
    mime_type = raw_mime_type or str(mimetypes.guess_type(fallback_path)[0] or "application/octet-stream")
    preview_kind = raw_preview_kind or _infer_preview_kind(path=fallback_file, mime_type=mime_type)
    payload: dict[str, Any] = {
        "path": fallback_path,
        "name": raw_name or fallback_file.name or "artifact",
        "mime_type": mime_type,
        "size_bytes": _safe_positive_int(item.get("size_bytes")),
        "preview_kind": preview_kind,
        "content": raw_content[: max(0, int(inline_content_limit_chars or 0))],
        "created_at": raw_created_at,
        "modified_at": raw_modified_at,
    }
    if raw_relative_path:
        payload["relative_path"] = raw_relative_path
    if raw_binary_base64 and len(raw_binary_base64) <= max(0, int(inline_content_limit_chars or 0)):
        payload["binary_base64"] = raw_binary_base64
    return payload


def normalize_tool_artifact_payloads(
    items: Any,
    *,
    inline_content_limit_chars: int = 16_000,
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        payload = normalize_tool_artifact_payload(
            item,
            inline_content_limit_chars=inline_content_limit_chars,
        )
        if payload is not None:
            normalized.append(payload)
    return normalized
