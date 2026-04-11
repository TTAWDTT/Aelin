from __future__ import annotations

import logging
from typing import Any

try:
    from deepagents.backends.composite import CompositeBackend
    from deepagents.backends.protocol import WriteResult
except Exception:  # pragma: no cover - fallback for test environments without deepagents
    from dataclasses import dataclass

    @dataclass
    class WriteResult:
        path: str | None = None
        error: str | None = None

    class CompositeBackend:
        def __init__(self, *, default, routes) -> None:  # noqa: ANN001
            self.default = default
            self.routes = dict(routes or {})
            for prefix, backend in self.routes.items():
                if hasattr(backend, "set_route_prefix"):
                    try:
                        backend.set_route_prefix(prefix)
                    except Exception:
                        pass

        def _resolve_backend(self, file_path: str):  # noqa: ANN001
            normalized_path = str(file_path or "")
            matched_prefix = ""
            matched_backend = self.default
            for prefix, backend in self.routes.items():
                if normalized_path.startswith(prefix) and len(prefix) > len(matched_prefix):
                    matched_prefix = prefix
                    matched_backend = backend
            return matched_backend

        def write(self, file_path: str, content: str) -> WriteResult:
            backend = self._resolve_backend(file_path)
            return backend.write(file_path, content)

        async def awrite(self, file_path: str, content: str) -> WriteResult:
            backend = self._resolve_backend(file_path)
            if hasattr(backend, "awrite"):
                return await backend.awrite(file_path, content)
            return backend.write(file_path, content)

        def download_files(self, paths: list[str]) -> list[Any]:
            responses: list[Any] = []
            for path in list(paths or []):
                backend = self._resolve_backend(path)
                responses.extend(list(backend.download_files([path]) or []))
            return responses

        def ls_info(self, path: str) -> list[dict[str, Any]]:
            backend = self._resolve_backend(path)
            return list(backend.ls_info(path) or [])


_LOG = logging.getLogger(__name__)


class ManagedCompositeBackend(CompositeBackend):
    """Composite backend with a hard write_file size guard."""

    def __init__(
        self,
        *,
        default,
        routes,
        write_file_max_chars: int,
        user_id: int | None = None,
        workspace: str | None = None,
        seed_files: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(default=default, routes=routes)
        self.write_file_max_chars = max(0, int(write_file_max_chars or 0))
        self.user_id = int(user_id or 0)
        self.workspace = str(workspace or "default")
        self.seed_files = self._clone_seed_files(seed_files)
        self._seed_runtime_files()

    @staticmethod
    def _clone_seed_files(
        seed_files: dict[str, dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        cloned: dict[str, dict[str, Any]] = {}
        for path, file_data in (seed_files or {}).items():
            if not isinstance(file_data, dict):
                continue
            content = file_data.get("content")
            cloned[path] = {
                "content": list(content) if isinstance(content, list) else [],
                "created_at": str(file_data.get("created_at") or ""),
                "modified_at": str(file_data.get("modified_at") or ""),
            }
        return cloned

    def _seed_runtime_files(self) -> None:
        if not self.seed_files:
            return
        runtime = getattr(self.default, "runtime", None)
        state = getattr(runtime, "state", None)
        if not isinstance(state, dict):
            return

        existing_files = state.get("files", {})
        if not isinstance(existing_files, dict):
            existing_files = {}

        merged_files = dict(existing_files)
        merged_files.update(self._clone_seed_files(self.seed_files))
        state["files"] = merged_files

    def _log_write_decision(
        self,
        *,
        file_path: str,
        content_chars: int,
        decision: str,
        reason: str,
        threshold_chars: int,
    ) -> None:
        level = logging.WARNING if decision == "rejected" else logging.INFO
        _LOG.log(
            level,
            (
                "deepagents_write_file_guard "
                "decision=%s path=%s content_chars=%s threshold_chars=%s "
                "user_id=%s workspace=%s reason=%s"
            ),
            decision,
            file_path,
            content_chars,
            threshold_chars,
            self.user_id,
            self.workspace,
            reason,
        )

    def _guard_write(self, file_path: str, content: str) -> WriteResult | None:
        content_chars = len(content or "")
        threshold_chars = self.write_file_max_chars
        if threshold_chars <= 0 or content_chars <= threshold_chars:
            self._log_write_decision(
                file_path=file_path,
                content_chars=content_chars,
                decision="allowed",
                reason="within_limit",
                threshold_chars=threshold_chars,
            )
            return None

        reason = (
            f"write_file_too_large: content has {content_chars} chars, exceeding the "
            f"configured limit of {threshold_chars} chars. Do not retry with another huge blob. "
            "Split the output into smaller files or reduce the artifact size first."
        )
        self._log_write_decision(
            file_path=file_path,
            content_chars=content_chars,
            decision="rejected",
            reason="content_exceeds_limit",
            threshold_chars=threshold_chars,
        )
        return WriteResult(error=reason)

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        blocked = self._guard_write(file_path, content)
        if blocked is not None:
            return blocked
        return super().write(file_path, content)

    async def awrite(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        blocked = self._guard_write(file_path, content)
        if blocked is not None:
            return blocked
        return await super().awrite(file_path, content)
