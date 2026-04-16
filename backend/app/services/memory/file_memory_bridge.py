from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import memory_root
from app.services.foundation.agent_config_service import normalize_workspace as _normalize_workspace
from app.settings import settings


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


class FileMemoryBridge:
    """
    Simplified file-memory bridge for DeepAgents.

    This implementation is deliberately minimal: it only reads/writes local
    markdown files under `../data/aelin_memory` and does not depend on any
    external vector index or third-party memory system.
    """

    def __init__(self) -> None:
        root = memory_root()
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self._cache_lock = threading.RLock()
        self._cache: OrderedDict[str, _CachedFileValue] = OrderedDict()

    def _workspace_root(self, *, user_id: int, workspace: str) -> Path:
        ws = _normalize_workspace(workspace)
        return self.root / "users" / str(max(0, int(user_id))) / "workspaces" / ws

    def _memory_root(self, *, user_id: int, workspace: str) -> Path:
        base = self._workspace_root(user_id=user_id, workspace=workspace) / "memory"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _cache_key(self, path: Path) -> str:
        try:
            return str(path.resolve())
        except Exception:
            return str(path)

    def _cache_ttl_seconds(self) -> float:
        try:
            return max(
                0.0,
                float(getattr(settings, "aelin_base_context_cache_ttl_seconds", 4.0) or 0.0),
            )
        except Exception:
            return 4.0

    def _cache_max_entries(self) -> int:
        try:
            return max(
                8,
                int(getattr(settings, "aelin_base_context_cache_max_entries", 128) or 128),
            )
        except Exception:
            return 128

    def _remember_cached_value(self, path: Path, value: Any) -> Any:
        key = self._cache_key(path)
        with self._cache_lock:
            self._cache[key] = _CachedFileValue(value=value, cached_at=time.monotonic())
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max_entries():
                self._cache.popitem(last=False)
        return value

    def _cached_path_value(self, path: Path) -> Any | None:
        ttl_seconds = self._cache_ttl_seconds()
        if ttl_seconds <= 0:
            return None
        key = self._cache_key(path)
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            if (time.monotonic() - float(cached.cached_at)) > ttl_seconds:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return cached.value

    def _drop_cached_path(self, path: Path) -> None:
        with self._cache_lock:
            self._cache.pop(self._cache_key(path), None)

    def clear_cache_for_tests(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def _read_text_file(self, path: Path) -> str:
        cached = self._cached_path_value(path)
        if isinstance(cached, str):
            return cached
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._drop_cached_path(path)
            return ""
        return str(self._remember_cached_value(path, str(text or "")))

    def _write_text_file(self, path: Path, content: str) -> None:
        path.write_text(str(content or ""), encoding="utf-8")
        self._remember_cached_value(path, str(content or ""))

    def _read_json_file(self, path: Path) -> dict[str, Any] | None:
        cached = self._cached_path_value(path)
        if isinstance(cached, dict):
            return dict(cached)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._drop_cached_path(path)
            return None
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        stored = dict(parsed)
        self._remember_cached_value(path, stored)
        return dict(stored)

    def _write_json_file(self, path: Path, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        path.write_text(serialized, encoding="utf-8")
        self._remember_cached_value(path, dict(payload))

    def read_agents_memory(self, *, user_id: int, workspace: str) -> str:
        path = self._memory_root(user_id=user_id, workspace=workspace) / "AGENTS.md"
        return self._read_text_file(path)

    def write_agents_memory(self, *, user_id: int, workspace: str, content: str) -> None:
        path = self._memory_root(user_id=user_id, workspace=workspace) / "AGENTS.md"
        self._write_text_file(path, str(content or ""))

    def read_memory_text(self, *, user_id: int, workspace: str, path: str) -> str:
        raw_path = str(path or "").strip()
        if not raw_path:
            return ""
        root = self._memory_root(user_id=user_id, workspace=workspace)
        candidate = (root / raw_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except Exception:
            return ""
        if not candidate.exists() or not candidate.is_file():
            return ""
        return self._read_text_file(candidate)

    def write_memory_text(self, *, user_id: int, workspace: str, path: str, content: str) -> None:
        raw_path = str(path or "").strip()
        if not raw_path:
            raise ValueError("memory_text_path_empty")
        root = self._memory_root(user_id=user_id, workspace=workspace)
        candidate = (root / raw_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except Exception as exc:
            raise ValueError("memory_text_path_outside_root") from exc
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._write_text_file(candidate, str(content or ""))

    def read_memory_json(self, *, user_id: int, workspace: str, path: str) -> dict[str, Any] | None:
        raw_path = str(path or "").strip()
        if not raw_path:
            return None
        root = self._memory_root(user_id=user_id, workspace=workspace)
        candidate = (root / raw_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except Exception:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return self._read_json_file(candidate)

    def write_memory_json(self, *, user_id: int, workspace: str, path: str, payload: dict[str, Any]) -> None:
        raw_path = str(path or "").strip()
        if not raw_path:
            raise ValueError("memory_json_path_empty")
        root = self._memory_root(user_id=user_id, workspace=workspace)
        candidate = (root / raw_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except Exception as exc:
            raise ValueError("memory_json_path_outside_root") from exc
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._write_json_file(candidate, dict(payload or {}))

    def read_memory_markdown(self, *, user_id: int, workspace: str, path: str) -> dict[str, Any] | None:
        raw_path = str(path or "").strip()
        if not raw_path:
            return None
        root = self._memory_root(user_id=user_id, workspace=workspace)
        candidate = (root / raw_path.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except Exception:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        text = self._read_text_file(candidate)
        return {
            "path": str(candidate),
            "title": candidate.stem[:120],
            "source": "memory",
            "kind": "memory",
            "topic_path": "",
            "entry_kind": "memory_insight",
            "updated_at": _iso(datetime.now(timezone.utc)),
            "content": text,
        }


@dataclass
class _CachedFileValue:
    value: Any
    cached_at: float


file_memory_bridge = FileMemoryBridge()
