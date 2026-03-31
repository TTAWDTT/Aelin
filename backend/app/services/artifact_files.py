from __future__ import annotations

import mimetypes
from pathlib import Path

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
