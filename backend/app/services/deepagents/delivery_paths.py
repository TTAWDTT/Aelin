from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKSPACE_VIRTUAL_PATH = "/workspace"
_OUTPUTS_VIRTUAL_PATH = "/outputs"


def _workspace_slug(raw_workspace: str) -> str:
    text = " ".join(str(raw_workspace or "").strip().split()).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:64] or "default"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class DeepAgentsDeliveryPaths:
    root_dir: Path
    workspace_dir: Path
    outputs_dir: Path
    workspace_virtual_path: str = _WORKSPACE_VIRTUAL_PATH
    outputs_virtual_path: str = _OUTPUTS_VIRTUAL_PATH


def get_delivery_paths(*, workspace: str, user_id: int | None = None, create: bool = True) -> DeepAgentsDeliveryPaths:
    safe_user_id = max(0, int(user_id or 0))
    safe_workspace = _workspace_slug(workspace)
    root_dir = (_REPO_ROOT / "output" / "deepagents" / f"user-{safe_user_id}" / safe_workspace).resolve()
    workspace_dir = (root_dir / "workspace").resolve()
    outputs_dir = (root_dir / "outputs").resolve()
    if create:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)
    return DeepAgentsDeliveryPaths(
        root_dir=root_dir,
        workspace_dir=workspace_dir,
        outputs_dir=outputs_dir,
    )


def resolve_virtual_or_local_path(
    path_value: str,
    paths: DeepAgentsDeliveryPaths,
    *,
    default_root: str | None = None,
    allow_workspace: bool = True,
    allow_outputs: bool = True,
) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise ValueError("missing_path")

    allowed_roots: list[Path] = []
    if allow_workspace:
        allowed_roots.append(paths.workspace_dir)
    if allow_outputs:
        allowed_roots.append(paths.outputs_dir)

    if raw == paths.workspace_virtual_path or raw.startswith(f"{paths.workspace_virtual_path}/"):
        if not allow_workspace:
            raise ValueError("workspace_path_not_allowed")
        suffix = raw[len(paths.workspace_virtual_path) :].lstrip("/\\")
        return (paths.workspace_dir / suffix).resolve()

    if raw == paths.outputs_virtual_path or raw.startswith(f"{paths.outputs_virtual_path}/"):
        if not allow_outputs:
            raise ValueError("outputs_path_not_allowed")
        suffix = raw[len(paths.outputs_virtual_path) :].lstrip("/\\")
        return (paths.outputs_dir / suffix).resolve()

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        if default_root == "workspace":
            resolved = (paths.workspace_dir / candidate).resolve()
        elif default_root == "outputs":
            resolved = (paths.outputs_dir / candidate).resolve()
        else:
            raise ValueError("relative_path_requires_default_root")

    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise ValueError("path_outside_delivery_roots")
    return resolved
