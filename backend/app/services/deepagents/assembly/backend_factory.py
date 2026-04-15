from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    from deepagents.backends.filesystem import FilesystemBackend
    from deepagents.backends.state import StateBackend
except Exception:  # pragma: no cover - fallback for test environments without deepagents
    class _FallbackDownloadResponse:
        def __init__(self, *, content: bytes | None = None) -> None:
            self.content = content

    class StateBackend:
        def __init__(self, runtime: Any) -> None:
            self.runtime = runtime

        def _files(self) -> dict[str, dict[str, Any]]:
            state = getattr(self.runtime, "state", None)
            if not isinstance(state, dict):
                state = {}
                setattr(self.runtime, "state", state)
            files = state.get("files")
            if not isinstance(files, dict):
                files = {}
                state["files"] = files
            return files

        def write(self, file_path: str, content: str) -> Any:
            from app.services.deepagents.managed_backend import WriteResult

            text = str(content or "")
            lines = text.splitlines() or ([text] if text else [])
            self._files()[str(file_path)] = {
                "content": lines,
                "created_at": "",
                "modified_at": "",
            }
            return WriteResult(path=str(file_path), error=None)

        async def awrite(self, file_path: str, content: str) -> Any:
            return self.write(file_path, content)

        def download_files(self, paths: list[str]) -> list[Any]:
            files = self._files()
            responses: list[_FallbackDownloadResponse] = []
            for path in list(paths or []):
                entry = files.get(str(path)) or {}
                content = entry.get("content")
                if isinstance(content, list):
                    text = "\n".join(str(line) for line in content)
                else:
                    text = str(content or "")
                responses.append(_FallbackDownloadResponse(content=text.encode("utf-8")))
            return responses

        def ls_info(self, path: str) -> list[dict[str, Any]]:
            prefix = str(path or "")
            return [
                {"path": file_path, "is_dir": False}
                for file_path in sorted(self._files().keys())
                if file_path.startswith(prefix)
            ]

    class FilesystemBackend:
        def __init__(self, *, root_dir: Path, virtual_mode: bool = True) -> None:
            self.root_dir = Path(root_dir)
            self.virtual_mode = bool(virtual_mode)
            self._route_prefix = "/"

        def set_route_prefix(self, prefix: str) -> None:
            self._route_prefix = str(prefix or "/")

        def _relative_path(self, path: str) -> Path:
            normalized = str(path or "")
            prefix = str(self._route_prefix or "/")
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
            normalized = normalized.lstrip("/").replace("\\", "/")
            return self.root_dir / normalized

        def write(self, file_path: str, content: str) -> Any:
            from app.services.deepagents.managed_backend import WriteResult

            target = self._relative_path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content or ""), encoding="utf-8")
            return WriteResult(path=str(file_path), error=None)

        async def awrite(self, file_path: str, content: str) -> Any:
            return self.write(file_path, content)

        def download_files(self, paths: list[str]) -> list[Any]:
            responses: list[_FallbackDownloadResponse] = []
            for path in list(paths or []):
                target = self._relative_path(path)
                data = target.read_bytes() if target.is_file() else None
                responses.append(_FallbackDownloadResponse(content=data))
            return responses

        def ls_info(self, path: str) -> list[dict[str, Any]]:
            target = self._relative_path(path)
            base = target if target.is_dir() else target.parent
            if not base.exists():
                return []
            entries: list[dict[str, Any]] = []
            for child in sorted(base.iterdir(), key=lambda item: item.name):
                relative = child.relative_to(self.root_dir).as_posix()
                virtual_path = f"{self._route_prefix.rstrip('/')}/{relative}"
                if child.is_dir():
                    virtual_path = f"{virtual_path.rstrip('/')}/"
                entries.append({"path": virtual_path, "is_dir": child.is_dir()})
            return entries

from app.services.deepagents.delivery_paths import get_delivery_paths
from app.services.deepagents.managed_backend import ManagedCompositeBackend
from app.settings import settings


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent.parent.parent


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
