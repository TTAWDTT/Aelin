from __future__ import annotations

import os
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent


def _resolve_env_path(*, env_name: str, default_path: Path, base_dir: Path) -> Path:
    raw_value = str(os.getenv(env_name, "") or "").strip()
    if not raw_value:
        return default_path.resolve()
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def backend_root() -> Path:
    return _BACKEND_ROOT.resolve()


def repo_root() -> Path:
    return _REPO_ROOT.resolve()


def backend_asset_root() -> Path:
    return _resolve_env_path(
        env_name="AELIN_BACKEND_ASSET_ROOT",
        default_path=backend_root(),
        base_dir=Path.cwd(),
    )


def app_data_root() -> Path:
    return _resolve_env_path(
        env_name="AELIN_APP_DATA_DIR",
        default_path=repo_root() / "data",
        base_dir=backend_root(),
    )


def output_root() -> Path:
    return _resolve_env_path(
        env_name="AELIN_OUTPUT_ROOT",
        default_path=repo_root() / "output",
        base_dir=backend_root(),
    )


def memory_root() -> Path:
    return _resolve_env_path(
        env_name="AELIN_MEMORY_ROOT",
        default_path=app_data_root() / "aelin_memory",
        base_dir=backend_root(),
    )


def deepagents_skills_root() -> Path:
    return (backend_asset_root() / "deepagents_skills").resolve()


def generated_posters_root() -> Path:
    return (output_root() / "generated-posters").resolve()

