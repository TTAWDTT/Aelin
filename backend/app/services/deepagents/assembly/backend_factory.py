from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.state import StateBackend

from app.runtime_paths import backend_asset_root
from app.services.deepagents.delivery_paths import get_delivery_paths
from app.services.deepagents.managed_backend import ManagedCompositeBackend
from app.settings import settings


def _backend_root() -> Path:
    return backend_asset_root()


def build_agent_backend_factory(
    *,
    user_id: int,
    workspace: str,
    skills_root: Path,
    extra_dir: str,
    seed_files: dict[str, Any] | None = None,
) -> Callable[[Any], ManagedCompositeBackend]:
    delivery_paths = get_delivery_paths(workspace=workspace, user_id=user_id)
    routes: dict[str, Any] = {}

    routes["/workspace/"] = FilesystemBackend(
        root_dir=delivery_paths.workspace_dir,
        virtual_mode=True,
    )
    routes["/outputs/"] = FilesystemBackend(
        root_dir=delivery_paths.outputs_dir,
        virtual_mode=True,
    )

    if skills_root.is_dir():
        routes["/skills/aelin/"] = FilesystemBackend(
            root_dir=skills_root,
            virtual_mode=True,
        )

    extra_root = Path(extra_dir) if extra_dir else None
    if extra_root is not None and extra_root.is_dir():
        routes["/skills/external/"] = FilesystemBackend(
            root_dir=extra_root,
            virtual_mode=True,
        )

    raw_write_file_max_chars = getattr(settings, "deepagents_write_file_max_chars", 0)
    if raw_write_file_max_chars is None:
        write_file_max_chars = 0
    else:
        write_file_max_chars = int(raw_write_file_max_chars)

    def _build_state_backend(runtime: Any) -> Any:
        try:
            return StateBackend()
        except TypeError:
            return StateBackend(runtime)

    def _factory(runtime: Any) -> ManagedCompositeBackend:
        return ManagedCompositeBackend(
            default=_build_state_backend(runtime),
            routes=dict(routes),
            write_file_max_chars=write_file_max_chars,
            user_id=user_id,
            workspace=workspace,
            seed_files=dict(seed_files or {}),
        )

    return _factory
