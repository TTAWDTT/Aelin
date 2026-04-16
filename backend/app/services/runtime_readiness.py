from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from app.runtime_paths import (
    app_data_root,
    backend_asset_root,
    backend_root,
    deepagents_skills_root,
    memory_root,
    output_root,
)
from app.settings import settings


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


def _probe_writable_dir(target: Path) -> dict[str, Any]:
    path = target.resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".aelin-readiness.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {
            "path": str(path),
            "exists": True,
            "writable": True,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "exists": path.exists(),
            "writable": False,
            "detail": str(exc)[:240],
        }


def _probe_readable_dir(target: Path) -> dict[str, Any]:
    path = target.resolve()
    return {
        "path": str(path),
        "exists": path.exists(),
        "readable": path.is_dir() and os.access(path, os.R_OK),
    }


def _probe_binary(name: str, configured_value: str) -> dict[str, Any]:
    configured = str(configured_value or "").strip()
    resolved = ""
    available = False
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            resolved = str(candidate.resolve()) if candidate.exists() else str(candidate)
            available = candidate.exists()
        else:
            resolved = shutil.which(configured) or ""
            available = bool(resolved)
    else:
        resolved = shutil.which(name) or ""
        available = bool(resolved)
    return {
        "configured": configured or name,
        "resolved": resolved,
        "available": available,
    }


def runtime_readiness_report() -> dict[str, Any]:
    media_dir = _resolve_setting_path(str(getattr(settings, "media_dir", "") or ""), base_dir=backend_root())
    attachment_storage_dir = _resolve_setting_path(
        str(getattr(settings, "aelin_attachment_storage_dir", "") or ""),
        base_dir=backend_root(),
    )
    google_workspace_config_dir = _resolve_setting_path(
        str(getattr(settings, "google_workspace_cli_config_dir", "") or ""),
        base_dir=backend_root(),
    )

    paths = {
        "backend_asset_root": _probe_readable_dir(backend_asset_root()),
        "skills_root": _probe_readable_dir(deepagents_skills_root()),
        "app_data_root": _probe_writable_dir(app_data_root()),
        "output_root": _probe_writable_dir(output_root()),
        "memory_root": _probe_writable_dir(memory_root()),
        "media_dir": _probe_writable_dir(media_dir),
        "attachment_storage_dir": _probe_writable_dir(attachment_storage_dir),
        "google_workspace_config_dir": _probe_writable_dir(google_workspace_config_dir),
    }

    optional_dependencies = {
        "google_workspace_cli": _probe_binary("gws", str(getattr(settings, "google_workspace_cli_bin", "") or "")),
        "soffice": _probe_binary("soffice", str(getattr(settings, "aelin_attachment_soffice_bin", "") or "")),
        "tesseract": _probe_binary("tesseract", str(getattr(settings, "aelin_attachment_tesseract_cmd", "") or "")),
    }

    path_ok = all(
        bool(item.get("readable", item.get("writable", False)))
        for item in paths.values()
    )
    return {
        "ok": path_ok,
        "paths": paths,
        "optional_dependencies": optional_dependencies,
    }
