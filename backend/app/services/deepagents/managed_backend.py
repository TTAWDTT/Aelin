from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

try:
    from deepagents.backends.composite import CompositeBackend
    from deepagents.backends.protocol import FileDownloadResponse, WriteResult
except Exception:  # pragma: no cover - fallback for test environments without deepagents
    @dataclass
    class WriteResult:
        path: str = ""
        error: str | None = None

    @dataclass
    class FileDownloadResponse:
        path: str = ""
        content: bytes | None = None
        error: str | None = None

    class CompositeBackend:
        def __init__(self, *, default: Any, routes: dict[str, Any]) -> None:
            self.default = default
            self.routes = dict(routes or {})

        def _resolve_backend(self, file_path: str) -> tuple[Any, str]:
            normalized = str(file_path or "")
            matched_prefix = ""
            matched_backend = None
            for prefix, backend in self.routes.items():
                prefix_text = str(prefix or "")
                if not prefix_text:
                    continue
                if normalized.startswith(prefix_text) and len(prefix_text) > len(matched_prefix):
                    matched_prefix = prefix_text
                    matched_backend = backend
            if matched_backend is None:
                return self.default, normalized
            try:
                setter = getattr(matched_backend, "set_route_prefix", None)
                if callable(setter):
                    setter(matched_prefix)
            except Exception:
                pass
            return matched_backend, normalized

        def write(self, file_path: str, content: str) -> WriteResult:
            backend, resolved_path = self._resolve_backend(file_path)
            return backend.write(resolved_path, content)

        async def awrite(self, file_path: str, content: str) -> WriteResult:
            backend, resolved_path = self._resolve_backend(file_path)
            awrite = getattr(backend, "awrite", None)
            if callable(awrite):
                return await awrite(resolved_path, content)
            return backend.write(resolved_path, content)

        def download_files(self, paths: list[str]) -> list[Any]:
            outputs: list[Any] = []
            for path in list(paths or []):
                backend, resolved_path = self._resolve_backend(path)
                downloader = getattr(backend, "download_files", None)
                if callable(downloader):
                    outputs.extend(list(downloader([resolved_path]) or []))
            return outputs

        def ls_info(self, path: str) -> list[dict[str, Any]]:
            backend, resolved_path = self._resolve_backend(path)
            lister = getattr(backend, "ls_info", None)
            if callable(lister):
                return list(lister(resolved_path) or [])
            return []

        async def als_info(self, path: str) -> list[dict[str, Any]]:
            return await asyncio.to_thread(self.ls_info, path)

        async def adownload_files(self, paths: list[str]) -> list[Any]:
            return await asyncio.to_thread(self.download_files, paths)


@dataclass
class LsResult:
    error: str | None = None
    entries: list[dict[str, Any]] | None = None


_LOG = logging.getLogger(__name__)


class ManagedCompositeBackend(CompositeBackend):
    """Composite backend with optional runtime file seeding and write_file guard."""

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
        self._overlay_files = self._clone_seed_files(seed_files)
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
            cloned_content: list[str] | str
            if isinstance(content, list):
                cloned_content = [str(line) for line in content]
            else:
                cloned_content = str(content or "")
            cloned_entry: dict[str, Any] = {
                "content": cloned_content,
                "created_at": str(file_data.get("created_at") or ""),
                "modified_at": str(file_data.get("modified_at") or ""),
            }
            encoding = file_data.get("encoding")
            if encoding is not None or isinstance(cloned_content, str):
                cloned_entry["encoding"] = str(encoding or "utf-8")
            cloned[str(path)] = cloned_entry
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

    @staticmethod
    def _file_text(file_data: dict[str, Any] | None) -> str:
        payload = dict(file_data or {})
        content = payload.get("content")
        if isinstance(content, list):
            return "\n".join(str(line) for line in content)
        return str(content or "")

    def _overlay_download_response(self, file_path: str) -> FileDownloadResponse:
        file_data = self._overlay_files.get(str(file_path)) or {}
        return FileDownloadResponse(
            path=str(file_path),
            content=self._file_text(file_data).encode("utf-8"),
            error=None,
        )

    def _overlay_write(self, file_path: str, content: str) -> WriteResult:
        normalized_path = str(file_path or "")
        if normalized_path in self._overlay_files:
            return WriteResult(
                error=(
                    f"Cannot write to {normalized_path} because it already exists. "
                    "Read and then make an edit, or write to a new path."
                )
            )

        now = datetime.now(UTC).isoformat()
        self._overlay_files[normalized_path] = {
            "content": str(content or ""),
            "encoding": "utf-8",
            "created_at": now,
            "modified_at": now,
        }
        return WriteResult(path=normalized_path, error=None)

    def _is_routed_path(self, file_path: str) -> bool:
        normalized = str(file_path or "")
        for prefix in self.routes.keys():
            route_prefix = str(prefix or "")
            if not route_prefix:
                continue
            prefix_no_slash = route_prefix.rstrip("/")
            if normalized == prefix_no_slash:
                return True
            effective_prefix = route_prefix if route_prefix.endswith("/") else f"{route_prefix}/"
            if normalized.startswith(effective_prefix):
                return True
        return False

    @staticmethod
    def _is_state_backend_graph_context_error(exc: RuntimeError) -> bool:
        message = str(exc or "")
        return "StateBackend must be used inside a LangGraph graph execution" in message

    def _overlay_entries_for_path(self, path: str) -> list[dict[str, Any]]:
        normalized_path = str(path or "/")
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path.lstrip('/')}"

        prefix = normalized_path if normalized_path.endswith("/") else f"{normalized_path}/"
        entries: list[dict[str, Any]] = []
        directories: set[str] = set()

        for file_path, file_data in sorted(self._overlay_files.items()):
            if normalized_path == "/":
                relative = file_path.lstrip("/")
                if not relative:
                    continue
                if "/" in relative:
                    directories.add("/" + relative.split("/", 1)[0] + "/")
                    continue
                entries.append(
                    {
                        "path": file_path,
                        "is_dir": False,
                        "size": len(self._file_text(file_data)),
                        "modified_at": str(file_data.get("modified_at") or ""),
                    }
                )
                continue

            if not file_path.startswith(prefix):
                continue
            relative = file_path[len(prefix) :]
            if not relative:
                continue
            if "/" in relative:
                directories.add(prefix + relative.split("/", 1)[0] + "/")
                continue
            entries.append(
                {
                    "path": file_path,
                    "is_dir": False,
                    "size": len(self._file_text(file_data)),
                    "modified_at": str(file_data.get("modified_at") or ""),
                }
            )

        entries.extend(
            {
                "path": directory_path,
                "is_dir": True,
                "size": 0,
                "modified_at": "",
            }
            for directory_path in sorted(directories)
        )
        entries.sort(key=lambda item: str(item.get("path") or ""))
        return entries

    @staticmethod
    def _merge_entries(
        base_entries: list[dict[str, Any]] | None,
        overlay_entries: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for entry in list(base_entries or []):
            path = str(entry.get("path") or "")
            if path:
                merged[path] = dict(entry)
        for entry in list(overlay_entries or []):
            path = str(entry.get("path") or "")
            if path:
                merged[path] = dict(entry)
        return [merged[path] for path in sorted(merged.keys())]

    def ls(self, path: str) -> LsResult:
        overlay_entries = self._overlay_entries_for_path(path)
        try:
            base_ls = getattr(super(), "ls", None)
            if callable(base_ls):
                base_result = base_ls(path)
            else:
                base_lister = getattr(super(), "ls_info", None)
                base_result = LsResult(entries=list(base_lister(path) or [])) if callable(base_lister) else LsResult(entries=[])
        except RuntimeError as exc:
            if not self._is_state_backend_graph_context_error(exc):
                raise
            route_entries: list[dict[str, Any]] = []
            if str(path or "/") == "/":
                route_entries = [
                    {
                        "path": str(prefix or ""),
                        "is_dir": True,
                        "size": 0,
                        "modified_at": "",
                    }
                    for prefix in sorted(self.routes.keys())
                ]
            return LsResult(entries=self._merge_entries(route_entries, overlay_entries))

        return LsResult(
            error=getattr(base_result, "error", None),
            entries=self._merge_entries(getattr(base_result, "entries", None), overlay_entries),
        )

    def ls_info(self, path: str) -> list[dict[str, Any]]:
        result = self.ls(path)
        return list(getattr(result, "entries", None) or [])

    def download_files(self, paths: list[str]) -> list[Any]:
        responses: list[Any] = [None] * len(list(paths or []))
        passthrough_indexes: list[int] = []
        passthrough_paths: list[str] = []

        for index, raw_path in enumerate(list(paths or [])):
            path = str(raw_path or "")
            if path in self._overlay_files:
                responses[index] = self._overlay_download_response(path)
                continue
            passthrough_indexes.append(index)
            passthrough_paths.append(path)

        if passthrough_paths:
            try:
                passthrough = list(super().download_files(passthrough_paths) or [])
            except RuntimeError as exc:
                if not self._is_state_backend_graph_context_error(exc):
                    raise
                passthrough = [
                    FileDownloadResponse(path=path, content=None, error=str(exc))
                    for path in passthrough_paths
                ]
            for index, response in zip(passthrough_indexes, passthrough, strict=False):
                responses[index] = response

        return [response for response in responses if response is not None]

    async def adownload_files(self, paths: list[str]) -> list[Any]:
        responses: list[Any] = [None] * len(list(paths or []))
        passthrough_indexes: list[int] = []
        passthrough_paths: list[str] = []

        for index, raw_path in enumerate(list(paths or [])):
            path = str(raw_path or "")
            if path in self._overlay_files:
                responses[index] = self._overlay_download_response(path)
                continue
            passthrough_indexes.append(index)
            passthrough_paths.append(path)

        if passthrough_paths:
            try:
                async_downloader = getattr(super(), "adownload_files", None)
                if callable(async_downloader):
                    passthrough = list(await async_downloader(passthrough_paths) or [])
                else:
                    passthrough = list(super().download_files(passthrough_paths) or [])
            except RuntimeError as exc:
                if not self._is_state_backend_graph_context_error(exc):
                    raise
                passthrough = [
                    FileDownloadResponse(path=path, content=None, error=str(exc))
                    for path in passthrough_paths
                ]
            for index, response in zip(passthrough_indexes, passthrough, strict=False):
                responses[index] = response

        return [response for response in responses if response is not None]

    async def als_info(self, path: str) -> list[dict[str, Any]]:
        overlay_entries = self._overlay_entries_for_path(path)
        try:
            async_lister = getattr(super(), "als_info", None)
            if callable(async_lister):
                base_entries = list(await async_lister(path) or [])
            else:
                base_entries = list(super().ls_info(path) or [])
        except RuntimeError as exc:
            if not self._is_state_backend_graph_context_error(exc):
                raise
            route_entries: list[dict[str, Any]] = []
            if str(path or "/") == "/":
                route_entries = [
                    {
                        "path": str(prefix or ""),
                        "is_dir": True,
                        "size": 0,
                        "modified_at": "",
                    }
                    for prefix in sorted(self.routes.keys())
                ]
            return self._merge_entries(route_entries, overlay_entries)

        return self._merge_entries(base_entries, overlay_entries)

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
        try:
            return super().write(file_path, content)
        except RuntimeError as exc:
            if self._is_routed_path(file_path) or not self._is_state_backend_graph_context_error(exc):
                raise
            return self._overlay_write(file_path, content)

    async def awrite(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        blocked = self._guard_write(file_path, content)
        if blocked is not None:
            return blocked
        try:
            return await super().awrite(file_path, content)
        except RuntimeError as exc:
            if self._is_routed_path(file_path) or not self._is_state_backend_graph_context_error(exc):
                raise
            return self._overlay_write(file_path, content)
