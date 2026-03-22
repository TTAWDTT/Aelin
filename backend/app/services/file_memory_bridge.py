from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _normalize_workspace(value: str) -> str:
    clean = " ".join((value or "").strip().split())
    return clean[:64] if clean else "default"


def _safe_json(payload: Any) -> str:
    try:
        import json

        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        return "{}"


def _slug(text: str, *, fallback: str = "item", max_len: int = 64) -> str:
    import re

    raw = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", (text or "").strip()).strip("-")
    if not raw:
        return fallback
    return raw[:max_len]


@dataclass
class FileMemoryReadParams:
    user_id: int
    workspace: str
    path: str = ""
    kind: str = ""
    topic_path: str = ""


@dataclass
class FileMemoryWriteTarget:
    user_id: int
    workspace: str
    source_type: str
    track_type: str
    source_key: str
    display_name: str


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

    def append_insight(
        self,
        *,
        target: FileMemoryWriteTarget,
        title: str,
        markdown: str,
        reason: str,
        confidence: float,
        source_query: str,
        topic_path: list[str],
        source_indices: list[dict[str, Any]],
        entry_kind: str = "memory_insight",
    ) -> str | None:
        base = self._memory_root(user_id=target.user_id, workspace=target.workspace)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe_title = _slug(title or "memory", fallback="memory", max_len=48)
        file_name = f"{ts}-{safe_title}.md"
        path = base / file_name

        meta_lines = [
            f"- source: {target.source_type}",
            f"- kind: memory",
            f"- entry_kind: {entry_kind}",
            f"- topic_path: {' > '.join(topic_path) if topic_path else ''}",
            f"- created_at: {_iso(datetime.now(timezone.utc))}",
            f"- updated_at: {_iso(datetime.now(timezone.utc))}",
            f"- reason: {str(reason or '')[:200]}",
            f"- confidence: {float(confidence or 0.0):.2f}",
        ]
        if source_query.strip():
            meta_lines.append(f"- query: {source_query.strip()[:320]}")
        if source_indices:
            meta_lines.append("- source_indices_json:")
            json_blob = _safe_json(source_indices)
            for raw in json_blob.splitlines():
                meta_lines.append(f"  {raw}")

        body: list[str] = [
            f"# {title or '记忆'}",
            "",
            *meta_lines,
            "",
            markdown or "",
            "",
        ]
        path.write_text("\n".join(body), encoding="utf-8")
        return str(path)


file_memory_bridge = FileMemoryBridge()
