from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.aelin.runtime import normalize_workspace as _normalize_workspace


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
        root = Path("../data/aelin_memory")
        if not root.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            root = (backend_root / root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.root = root

    def _workspace_root(self, *, user_id: int, workspace: str) -> Path:
        ws = _normalize_workspace(workspace)
        return self.root / "users" / str(max(0, int(user_id))) / "workspaces" / ws

    def _memory_root(self, *, user_id: int, workspace: str) -> Path:
        base = self._workspace_root(user_id=user_id, workspace=workspace) / "memory"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def read_agents_memory(self, *, user_id: int, workspace: str) -> str:
        path = self._memory_root(user_id=user_id, workspace=workspace) / "AGENTS.md"
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def write_agents_memory(self, *, user_id: int, workspace: str, content: str) -> None:
        path = self._memory_root(user_id=user_id, workspace=workspace) / "AGENTS.md"
        path.write_text(str(content or ""), encoding="utf-8")

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
        text = candidate.read_text(encoding="utf-8")
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


file_memory_bridge = FileMemoryBridge()

