from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.services.memory.file_memory_bridge import file_memory_bridge
from app.services.memory.agent_memory_utils import (
    _clean_text,
    _iso_or_empty,
    _truncate,
)

# Human-readable labels for legacy message sources. These values are only used
# when projecting historical focus items or notes that still carry an old
# `source` field; the current DeepAgents-only runtime no longer produces new
# entries for these sources, but we keep the map so that existing AGENTS.md or
# in-memory data can still render sensible labels.
_SOURCE_LABELS = {
    "x": "X",
    "douyin": "抖音",
    "bilibili": "Bilibili",
    "xiaohongshu": "小红书",
    "weibo": "微博",
    "web": "Web",
    "rss": "RSS",
    "github": "GitHub",
    "imap": "Email",
    "mock": "消息",
}
_TODO_SOURCE = "todo"
_LAYOUT_SOURCE = "card_layout"
_PROFILE_MEMORY_PATH = "profile.md"
_PREFERENCES_MEMORY_PATH = "preferences.md"
_FACTS_MEMORY_PATH = "facts.md"
_PROJECTS_MEMORY_PATH = "projects.md"
_RECENT_CONTEXT_MEMORY_PATH = "recent_context.md"
_TODOS_MEMORY_PATH = "todos.md"
_INDEX_MEMORY_PATH = "memory_index.json"

_SUMMARY_SECTION_ALIASES = ("会话摘要", "summary", "session summary")
_LONG_TERM_MEMORY_SECTION_ALIASES = ("长期记忆", "memory", "long-term memory")
_TODO_SECTION_ALIASES = ("待办", "todos", "todo")
_PROJECT_SECTION_ALIASES = ("项目", "projects", "active projects")


@dataclass
class FocusItem:
    message_id: int
    source: str
    sender: str
    sender_avatar_url: str | None
    title: str
    received_at: str
    score: float


def serialize_focus_item(item: FocusItem) -> dict[str, Any]:
    source = _truncate(_clean_text(getattr(item, "source", "")), 32) or "unknown"
    return {
        "message_id": int(getattr(item, "message_id", 0) or 0),
        "source": source,
        "source_label": _SOURCE_LABELS.get(source, source.title() if source else "Unknown"),
        "sender": _truncate(_clean_text(getattr(item, "sender", "")), 60),
        "sender_avatar_url": getattr(item, "sender_avatar_url", None),
        "title": _truncate(_clean_text(getattr(item, "title", "")), 140),
        "received_at": _truncate(_clean_text(getattr(item, "received_at", "")), 32),
        "score": float(getattr(item, "score", 0.0) or 0.0),
    }


@dataclass
class MemoryNote:
    """
    Lightweight in-memory representation of a long-term memory note.

    This replaces the legacy DB-backed AgentMemoryNote ORM model so that the
    memory service can operate purely on file-backed AGENTS.md content while
    keeping the rest of the codebase unchanged.
    """

    id: int
    user_id: int
    kind: str
    content: str
    source: str | None
    updated_at: datetime


class AgentMemoryService:
    """
    File-first memory service used by Aelin in the DeepAgents runtime.

    There are two distinct layers of responsibility:

    1. DeepAgents chat-loop interface（最小职责）
       - 读写 `/memory/AGENTS.md`（通过 `_read_agents_md_text` / `_write_agents_md_text`）
       - 直接返回该文件文本：
         `get_agents_memory_text(...)`
       DeepAgents agent loop 仅依赖这一文件视图，不会再直接触碰任何
       DB 记忆模型，也不会再经过“summary -> AGENTS.md”的桥接。

    2. UI / 工具视图（仅用于 context_get / profile 等工具）
       - `get_summary` / `list_notes` / `list_todos`
       - `build_memory_layers_from_items`
       - `add_note` 及若干 append_* 帮助函数

    这些 helper 只为画像 / 待办 / 记忆工具提供投影，不影响 DeepAgents 的主
    agent loop 行为。
    """
    # === DeepAgents chat-loop helpers (AGENTS.md IO) ===

    def _read_agents_md_text(self, user_id: int, workspace: str = "default") -> str:
        """
        Best-effort read of the DeepAgents-style AGENTS.md memory file.

        This is a thin wrapper around FileMemoryBridge with defensive guards,
        so that higher-level helpers do not need to catch IO errors.
        """
        try:
            text = file_memory_bridge.read_agents_memory(user_id=user_id, workspace=workspace)
        except Exception:
            return ""
        return str(text or "")

    def _write_agents_md_text(self, user_id: int, workspace: str, content: str) -> None:
        """
        Best-effort write of the AGENTS.md memory file for a workspace.

        This wraps FileMemoryBridge so callers do not have to deal with paths
        or IO errors. Failures are swallowed to avoid breaking the main flow.
        """
        try:
            file_memory_bridge.write_agents_memory(
                user_id=user_id,
                workspace=workspace,
                content=str(content or ""),
            )
        except Exception:
            return

    def _parse_agents_md_sections(self, text: str) -> dict[str, list[str]]:
        """
        Parse a minimal section map from an AGENTS.md-style markdown document.

        The map keys are headings without the leading '## ', values are the
        raw lines (including bullet markers) that belong to that section.
        """
        sections: dict[str, list[str]] = {}
        if not text:
            return sections
        current: str | None = None
        for raw in str(text).splitlines():
            line = str(raw or "")
            if line.startswith("## "):
                current = line[3:].strip()
                if not current:
                    current = None
                else:
                    sections.setdefault(current, [])
                continue
            if current is None:
                continue
            sections.setdefault(current, []).append(line)
        return sections

    def _section_name_matches(self, name: str, aliases: tuple[str, ...]) -> bool:
        normalized = _clean_text(name).lower()
        return any(normalized == _clean_text(alias).lower() for alias in aliases if alias)

    def _find_section_lines(
        self,
        sections: dict[str, list[str]],
        aliases: tuple[str, ...],
    ) -> list[str]:
        for name, lines in sections.items():
            if self._section_name_matches(name, aliases):
                return list(lines)
        return []

    def _append_line_to_section(self, text: str, section: str, line: str) -> str:
        """
        Append a single markdown line to the given section, creating the
        section and document skeleton if needed.
        """
        base = str(text or "")
        header = f"## {section}"
        if not base.strip():
            base = "# Aelin Session Memory\n\n"

        idx = base.find(header)
        if idx < 0:
            # Append a new section at the end.
            if not base.endswith("\n"):
                base += "\n"
            return base + f"\n{header}\n{line}\n"

        # Insert inside existing section, before the next heading.
        tail = base[idx:]
        next_rel = min(
            (pos for pos in (tail.find("\n## "), tail.find("\n# ")) if pos > 0),
            default=-1,
        )
        end_idx = idx + next_rel if next_rel > 0 else len(base)
        section_block = base[idx:end_idx]
        if not section_block.endswith("\n"):
            section_block += "\n"
        section_block = section_block + line + "\n"
        return base[:idx] + section_block + base[end_idx:]

    def get_agents_memory_text(
        self,
        db: Session,
        user_id: int,
        *,
        workspace: str = "default",
    ) -> str:
        """
        Return the raw AGENTS.md text for the requested workspace.

        DeepAgents mounts this text directly as `/memory/AGENTS.md`; no
        query-specific sections or synthetic wrappers are added here.
        """
        _ = db
        return str(
            self._read_agents_md_text(user_id=user_id, workspace=workspace or "default") or ""
        ).strip()

    def append_fact_to_memory(self, *, user_id: int, workspace: str, content: str) -> None:
        clean = _truncate(_clean_text(content), 280)
        if not clean:
            return
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        updated = self._append_line_to_section(text, "长期记忆", f"- [事实] {clean}")
        self._write_agents_md_text(user_id=user_id, workspace=workspace, content=updated)

    def append_preference_to_memory(self, *, user_id: int, workspace: str, content: str) -> None:
        clean = _truncate(_clean_text(content), 280)
        if not clean:
            return
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        updated = self._append_line_to_section(text, "长期记忆", f"- [偏好] {clean}")
        self._write_agents_md_text(user_id=user_id, workspace=workspace, content=updated)

    def add_todo_to_memory(
        self,
        *,
        user_id: int,
        workspace: str,
        title: str,
        priority: str = "normal",
    ) -> None:
        clean_title = _truncate(_clean_text(title), 200)
        if not clean_title:
            return
        priority_norm = (_clean_text(priority) or "normal").lower()
        badge = "!" if priority_norm == "high" else "-"
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        updated = self._append_line_to_section(text, "待办", f"- [{badge}] {clean_title}")
        self._write_agents_md_text(user_id=user_id, workspace=workspace, content=updated)

    def _summary_from_sections(self, sections: dict[str, list[str]]) -> str:
        lines = self._find_section_lines(sections, _SUMMARY_SECTION_ALIASES)
        if not lines:
            return ""
        parts: list[str] = []
        for raw in lines:
            line = _clean_text(str(raw or ""))
            if line:
                parts.append(line)
        return _truncate(" ".join(parts), 1000)

    def _normalize_note_kind(self, value: str) -> str:
        normalized = _clean_text(value).lower()
        if normalized in {"偏好", "preference", "preferences", "profile", "喜好"}:
            return "preference"
        if normalized in {"事实", "fact", "facts"}:
            return "fact"
        if normalized in {"进行中", "in_progress", "todo", "todos", "待办"}:
            return "in_progress"
        if normalized in {"项目", "project", "projects"}:
            return "project"
        if normalized in {"summary", "会话摘要"}:
            return "summary"
        return "note"

    def _normalize_search_kind(self, value: str) -> str:
        normalized = self._normalize_note_kind(value)
        if normalized == "note":
            raw = _clean_text(value).lower()
            if raw in {"recent", "recent_context", "context"}:
                return "recent_context"
            if raw in {"todo", "todos"}:
                return "todo"
            if raw in {"profile", "preferences"}:
                return "preference"
        if normalized == "in_progress":
            raw = _clean_text(value).lower()
            if raw in {"todo", "todos"}:
                return "todo"
            return "recent_context"
        return normalized

    def _note_rows_from_sections(self, sections: dict[str, list[str]]) -> list[dict[str, str]]:
        lines = self._find_section_lines(sections, _LONG_TERM_MEMORY_SECTION_ALIASES)
        rows: list[dict[str, str]] = []
        for raw in lines:
            line = str(raw or "").strip()
            if not line or not line.lstrip().startswith("-"):
                continue
            bullet = line.lstrip()[1:].strip()
            if not bullet:
                continue
            tag = ""
            body = bullet
            matched = re.match(r"\[(?P<tag>[^\]]+)\]\s*(?P<body>.+)", bullet)
            if matched:
                tag = str(matched.group("tag") or "").strip()
                body = str(matched.group("body") or "").strip()
            content = _truncate(_clean_text(body), 500)
            if not content:
                continue
            rows.append(
                {
                    "kind": self._normalize_note_kind(tag),
                    "content": content,
                }
            )

        project_lines = self._find_section_lines(sections, _PROJECT_SECTION_ALIASES)
        for raw in project_lines:
            line = _truncate(_clean_text(str(raw or "").lstrip("- ").strip()), 500)
            if not line:
                continue
            rows.append({"kind": "project", "content": line})
        return rows

    def _todo_rows_from_sections(self, sections: dict[str, list[str]]) -> list[dict[str, Any]]:
        lines = self._find_section_lines(sections, _TODO_SECTION_ALIASES)
        rows: list[dict[str, Any]] = []
        for index, raw in enumerate(lines):
            line = str(raw or "").strip()
            if not line or not line.lstrip().startswith("-"):
                continue
            bullet = line.lstrip()[1:].strip()
            if not bullet:
                continue
            tag = ""
            title = bullet
            matched = re.match(r"\[(?P<tag>[^\]]*)\]\s*(?P<title>.+)", bullet)
            if matched:
                tag = str(matched.group("tag") or "").strip()
                title = str(matched.group("title") or "").strip()
            title_clean = _truncate(_clean_text(title), 240)
            if not title_clean:
                continue
            tag_norm = _clean_text(tag).lower()
            rows.append(
                {
                    "id": index + 1,
                    "title": title_clean,
                    "done": tag_norm in {"x", "done", "✓", "✔", "完成"},
                    "priority": "high" if tag_norm in {"!", "high", "重要", "high-priority"} else "normal",
                }
            )
        return rows

    def _render_markdown_document(self, title: str, bullets: Iterable[str]) -> str:
        rows = [f"# {title}", ""]
        added = False
        for bullet in bullets:
            clean = _truncate(_clean_text(bullet), 600)
            if not clean:
                continue
            rows.append(f"- {clean}")
            added = True
        if not added:
            return ""
        rows.append("")
        return "\n".join(rows)

    def _search_rows_from_agents_text(self, text: str) -> list[dict[str, Any]]:
        sections = self._parse_agents_md_sections(text)
        summary = self._summary_from_sections(sections)
        notes = self._note_rows_from_sections(sections)
        todos = self._todo_rows_from_sections(sections)
        updated_at = _iso_or_empty(datetime.now(timezone.utc))
        rows: list[dict[str, Any]] = []

        if summary:
            rows.append(
                {
                    "path": f"/memory/{_RECENT_CONTEXT_MEMORY_PATH}",
                    "target": _RECENT_CONTEXT_MEMORY_PATH,
                    "title": "近期对话摘要",
                    "preview": _truncate(summary, 280),
                    "score": 0.0,
                    "updated_at": updated_at,
                    "canonical_id": "summary:session",
                    "source": "agents_md",
                    "kind": "recent_context",
                    "topic_path": "recent_context",
                    "entry_kind": "summary",
                }
            )

        kind_counters: dict[str, int] = {}
        for note in notes:
            kind = str(note.get("kind") or "note")
            topic_path = {
                "preference": "preferences",
                "fact": "facts",
                "project": "projects",
                "in_progress": "recent_context",
            }.get(kind, "facts")
            relative_path = {
                "preference": _PREFERENCES_MEMORY_PATH,
                "fact": _FACTS_MEMORY_PATH,
                "project": _PROJECTS_MEMORY_PATH,
                "in_progress": _RECENT_CONTEXT_MEMORY_PATH,
            }.get(kind, _FACTS_MEMORY_PATH)
            kind_counters[kind] = kind_counters.get(kind, 0) + 1
            canonical_id = f"{kind}:{kind_counters[kind]}"
            rows.append(
                {
                    "path": f"/memory/{relative_path}",
                    "target": relative_path,
                    "title": _truncate(str(note.get("content") or ""), 120),
                    "preview": _truncate(str(note.get("content") or ""), 280),
                    "score": 0.0,
                    "updated_at": updated_at,
                    "canonical_id": canonical_id,
                    "source": "agents_md",
                    "kind": kind if kind != "note" else "fact",
                    "topic_path": topic_path,
                    "entry_kind": "note",
                }
            )

        for todo in todos:
            rows.append(
                {
                    "path": f"/memory/{_TODOS_MEMORY_PATH}",
                    "target": _TODOS_MEMORY_PATH,
                    "title": _truncate(str(todo.get("title") or ""), 120),
                    "preview": _truncate(str(todo.get("title") or ""), 280),
                    "score": 0.0,
                    "updated_at": updated_at,
                    "canonical_id": f"todo:{int(todo.get('id') or 0)}",
                    "source": "agents_md",
                    "kind": "todo",
                    "topic_path": "todos",
                    "entry_kind": "todo",
                }
            )

        return rows

    def _build_projection_documents(self, text: str) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
        rows = self._search_rows_from_agents_text(text)
        preference_rows = [row for row in rows if row.get("kind") == "preference"]
        fact_rows = [row for row in rows if row.get("kind") == "fact"]
        project_rows = [row for row in rows if row.get("kind") == "project"]
        recent_rows = [row for row in rows if row.get("kind") == "recent_context"]
        todo_rows = [row for row in rows if row.get("kind") == "todo"]

        files = {
            _PROFILE_MEMORY_PATH: self._render_markdown_document(
                "Profile Snapshot",
                [str(row.get("preview") or "") for row in preference_rows[:8]],
            ),
            _PREFERENCES_MEMORY_PATH: self._render_markdown_document(
                "Stable Preferences",
                [str(row.get("preview") or "") for row in preference_rows],
            ),
            _FACTS_MEMORY_PATH: self._render_markdown_document(
                "Stable Facts",
                [str(row.get("preview") or "") for row in fact_rows],
            ),
            _PROJECTS_MEMORY_PATH: self._render_markdown_document(
                "Projects",
                [str(row.get("preview") or "") for row in project_rows],
            ),
            _RECENT_CONTEXT_MEMORY_PATH: self._render_markdown_document(
                "Recent Context",
                [str(row.get("preview") or "") for row in recent_rows],
            ),
            _TODOS_MEMORY_PATH: self._render_markdown_document(
                "Todo Items",
                [
                    (
                        f"[{'done' if '已完成' in str(row.get('preview') or '') else 'todo'}] "
                        f"{str(row.get('preview') or '')}"
                    )
                    for row in todo_rows
                ],
            ),
        }
        files = {
            path: str(content or "").strip()
            for path, content in files.items()
            if str(content or "").strip()
        }
        index_payload = {
            "version": 1,
            "generated_at": _iso_or_empty(datetime.now(timezone.utc)),
            "runtime_prompt_path": "/memory/AGENTS.md",
            "counts": {
                "preferences": len(preference_rows),
                "facts": len(fact_rows),
                "projects": len(project_rows),
                "recent_context": len(recent_rows),
                "todos": len(todo_rows),
            },
            "files": [
                {
                    "path": "/memory/AGENTS.md",
                    "kind": "runtime_prompt",
                    "title": "Runtime memory prompt",
                },
                *[
                    {
                        "path": f"/memory/{path}",
                        "kind": path.rsplit(".", 1)[0],
                        "title": path.rsplit(".", 1)[0].replace("_", " "),
                    }
                    for path in sorted(files.keys())
                ],
                {
                    "path": f"/memory/{_INDEX_MEMORY_PATH}",
                    "kind": "index",
                    "title": "Memory index",
                },
            ],
        }
        return files, index_payload, rows

    def _persist_projection_documents(
        self,
        *,
        user_id: int,
        workspace: str,
        files: dict[str, str],
        index_payload: dict[str, Any],
    ) -> None:
        for relative_path, content in files.items():
            try:
                file_memory_bridge.write_memory_text(
                    user_id=user_id,
                    workspace=workspace,
                    path=relative_path,
                    content=content,
                )
            except Exception:
                continue
        try:
            file_memory_bridge.write_memory_json(
                user_id=user_id,
                workspace=workspace,
                path=_INDEX_MEMORY_PATH,
                payload=index_payload,
            )
        except Exception:
            return

    def _normalize_search_terms(self, query: str) -> list[str]:
        clean_query = _truncate(_clean_text(query), 240).lower()
        if not clean_query:
            return []
        terms: list[str] = []
        seen: set[str] = set()
        for candidate in [clean_query, *re.split(r"[\s/,_\-]+", clean_query)]:
            token = str(candidate or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            terms.append(token)
        return terms[:12]

    def _score_memory_row(self, row: dict[str, Any], terms: list[str]) -> float:
        title = str(row.get("title") or "").lower()
        preview = str(row.get("preview") or "").lower()
        metadata = " ".join(
            [
                str(row.get("kind") or ""),
                str(row.get("topic_path") or ""),
                str(row.get("source") or ""),
            ]
        ).lower()
        score = 0.0
        for index, term in enumerate(terms):
            if not term:
                continue
            weight = 1.5 if index == 0 else 1.0
            if term in title:
                score += 4.0 * weight
            if term in preview:
                score += 2.5 * weight
            if term in metadata:
                score += 1.0 * weight
        if len(terms) == 1 and terms[0] in preview and terms[0] in title:
            score += 1.5
        return score

    def _render_query_relevant_memory_section(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        lines = ["## 当前问题相关记忆", ""]
        for row in rows[:4]:
            preview = _truncate(_clean_text(str(row.get("preview") or row.get("title") or "")), 220)
            if not preview:
                continue
            label = str(row.get("kind") or "memory")
            lines.append(f"- [{label}] {preview}")
        if len(lines) <= 2:
            return ""
        lines.append("")
        return "\n".join(lines)

    def get_memory_bundle(
        self,
        *,
        user_id: int,
        workspace: str,
        fallback_agents_text: str = "",
        query_hint: str = "",
    ) -> dict[str, Any]:
        # Treat the provided AGENTS.md text as the authoritative snapshot for
        # this run. The caller has already resolved runtime memory, and
        # re-reading storage here can accidentally drift to a different file
        # view during tests or concurrent requests.
        base_text = str(fallback_agents_text or "").strip()
        if not base_text:
            base_text = str(
                self._read_agents_md_text(user_id=user_id, workspace=workspace) or ""
            ).strip()
        if not base_text:
            return {
                "prompt_path": "/memory/AGENTS.md",
                "prompt_text": "",
                "files": {},
                "memory_paths": [],
                "index": {},
            }

        projection_files, index_payload, rows = self._build_projection_documents(base_text)
        self._persist_projection_documents(
            user_id=user_id,
            workspace=workspace,
            files=projection_files,
            index_payload=index_payload,
        )

        focused_hits: list[dict[str, Any]] = []
        terms = self._normalize_search_terms(query_hint)
        if terms:
            for row in rows:
                score = self._score_memory_row(row, terms)
                if score <= 0:
                    continue
                enriched = dict(row)
                enriched["score"] = round(score, 3)
                focused_hits.append(enriched)
            focused_hits.sort(
                key=lambda item: (
                    -float(item.get("score") or 0.0),
                    str(item.get("title") or ""),
                )
            )

        prompt_text = base_text
        focused_section = self._render_query_relevant_memory_section(focused_hits)
        if focused_section:
            prompt_text = f"{base_text.rstrip()}\n\n{focused_section}".strip()

        files = {"/memory/AGENTS.md": prompt_text}
        for relative_path, content in projection_files.items():
            if str(content or "").strip():
                files[f"/memory/{relative_path}"] = str(content or "").strip()
        files[f"/memory/{_INDEX_MEMORY_PATH}"] = json.dumps(
            index_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

        memory_paths = ["/memory/AGENTS.md"]
        for row in focused_hits[:2]:
            path = str(row.get("path") or "").strip()
            if path and path not in memory_paths:
                memory_paths.append(path)

        return {
            "prompt_path": "/memory/AGENTS.md",
            "prompt_text": prompt_text,
            "files": files,
            "memory_paths": memory_paths,
            "index": index_payload,
        }

    def search_memory(
        self,
        *,
        user_id: int,
        workspace: str,
        query: str,
        top_k: int = 6,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        if not text:
            return []

        projection_files, index_payload, rows = self._build_projection_documents(text)
        self._persist_projection_documents(
            user_id=user_id,
            workspace=workspace,
            files=projection_files,
            index_payload=index_payload,
        )

        terms = self._normalize_search_terms(query)
        if not terms:
            return []
        normalized_kinds = {
            kind
            for kind in (
                self._normalize_search_kind(item)
                for item in list(kinds or [])
            )
            if kind
        }

        hits: list[dict[str, Any]] = []
        for row in rows:
            row_kind = self._normalize_search_kind(str(row.get("kind") or ""))
            if normalized_kinds and row_kind not in normalized_kinds:
                continue
            score = self._score_memory_row(row, terms)
            if score <= 0:
                continue
            enriched = dict(row)
            enriched["kind"] = row_kind
            enriched["score"] = round(score, 3)
            hits.append(enriched)
        hits.sort(
            key=lambda item: (
                -float(item.get("score") or 0.0),
                str(item.get("title") or ""),
            )
        )
        return hits[: max(1, min(20, int(top_k or 6)))]

    def _notes_from_agents_md(
        self,
        *,
        user_id: int,
        workspace: str,
        limit: int,
    ) -> list[MemoryNote]:
        """
        Project long-term notes from the '## 长期记忆' section of AGENTS.md.

        This returns in-memory AgentMemoryNote rows only; they are never
        attached to the DB session.
        """
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        if not text:
            return []
        sections = self._parse_agents_md_sections(text)
        lines = sections.get("长期记忆") or []
        if not lines:
            return []

        out: list[MemoryNote] = []
        n = max(1, min(50, int(limit or 12)))
        for idx, raw in enumerate(lines):
            line = str(raw or "").strip()
            if not line or not line.lstrip().startswith("-"):
                continue
            bullet = line.lstrip()[1:].strip()
            if not bullet:
                continue

            tag = ""
            body = bullet
            m = re.match(r"\[(?P<tag>[^\]]+)\]\s*(?P<body>.+)", bullet)
            if m:
                tag = str(m.group("tag") or "").strip()
                body = str(m.group("body") or "").strip()

            content = _truncate(_clean_text(body), 500)
            if not content:
                continue

            kind_norm = _clean_text(tag).lower()
            kind = "note"
            if kind_norm in {"偏好", "preference", "profile", "喜好"}:
                kind = "preference"
            elif kind_norm in {"事实", "fact"}:
                kind = "fact"
            elif kind_norm in {"进行中", "in_progress", "todo"}:
                kind = "in_progress"

            # 为了与旧调用点兼容，提供稳定的 id 与 updated_at 形态，但完全
            # 不再依赖底层数据库表。
            row = MemoryNote(
                id=idx + 1,
                user_id=user_id,
                kind=kind,
                content=content,
                source="agents_md",
                updated_at=datetime.now(timezone.utc),
            )
            out.append(row)
            if len(out) >= n:
                break
        return out

    def _todos_from_agents_md(
        self,
        *,
        user_id: int,
        workspace: str,
        include_done: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        """
        Project todos from the '## 待办' section of AGENTS.md.

        The returned structure matches list_todos() so that callers can use it
        transparently. When AGENTS.md does not define any todos, an empty list
        is returned and callers can fall back to DB-backed todos.
        """
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        if not text:
            return []
        sections = self._parse_agents_md_sections(text)
        lines = sections.get("待办") or []
        if not lines:
            return []

        out: list[dict[str, Any]] = []
        n = max(1, min(200, int(limit or 100)))
        for idx, raw in enumerate(lines):
            if len(out) >= n:
                break
            line = str(raw or "").strip()
            if not line or not line.lstrip().startswith("-"):
                continue
            bullet = line.lstrip()[1:].strip()
            if not bullet:
                continue

            tag = ""
            title = bullet
            m = re.match(r"\[(?P<tag>[^\]]*)\]\s*(?P<title>.+)", bullet)
            if m:
                tag = str(m.group("tag") or "").strip()
                title = str(m.group("title") or "").strip()

            title_clean = _truncate(_clean_text(title), 240)
            if not title_clean:
                continue

            tag_norm = _clean_text(tag).lower()
            done = False
            priority = "normal"
            if tag_norm in {"x", "done", "✓", "✔", "完成"}:
                done = True
            elif tag_norm in {"!", "high", "重要", "high-priority"}:
                priority = "high"

            if done and not include_done:
                continue

            out.append(
                {
                    # Use a stable, local identifier; DB-backed callers should
                    # treat AGENTS.md todos as read-only projections.
                    "id": idx + 1,
                    "title": title_clean,
                    "detail": "",
                    "done": done,
                    "due_at": None,
                    "priority": priority,
                    "contact_id": None,
                    "message_id": None,
                    "updated_at": "",
                }
            )
        return out

    # === UI / context projection helpers (not used by DeepAgents agent loop) ===

    def get_summary(self, db: Session, user_id: int, *, workspace: str = "default") -> str:
        """
        Return the short conversation summary for a user.

        In the DeepAgents 版本下，摘要只从 AGENTS.md 中的“## 会话摘要”段落
        解析，不再回落到任何 DB 表。若缺少该段落，则返回空字符串。
        """
        _ = db  # DB is no longer used for conversational summary.
        agents_md = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        if not agents_md:
            return ""
        text = _clean_text(agents_md)
        marker = "## 会话摘要"
        idx = text.find(marker)
        if idx < 0:
            return ""
        tail = text[idx + len(marker) :]
        lines: list[str] = []
        for raw in tail.splitlines():
            row = raw.strip()
            if not row:
                continue
            if row.startswith("#"):
                break
            lines.append(row)
            if len(" ".join(lines)) >= 1000:
                break
        summary = _truncate(" ".join(lines), 1000)
        return summary.strip()

    def list_notes(
        self,
        db: Session,
        user_id: int,
        limit: int = 12,
        workspace: str = "default",
    ) -> list[MemoryNote]:
        """
        List recent long-term memory notes.

        In the DeepAgents runtime this method is expected to project notes from
        the AGENTS.md file only. Legacy DB-backed notes are no longer used as a
        primary memory source and are intentionally ignored here so that the
        chat loop depends solely on file-backed memory.
        """
        n = max(1, min(50, int(limit or 12)))
        projected = self._notes_from_agents_md(user_id=user_id, workspace=workspace, limit=n)
        return projected

    def add_note(
        self,
        db: Session,
        user_id: int,
        content: str,
        *,
        kind: str = "note",
        source: str | None = None,
        workspace: str = "default",
    ) -> MemoryNote:
        """
        Append a note-style entry into AGENTS.md and return a lightweight
        MemoryNote projection. The DB is no longer used as a backing store.
        """
        _ = db
        clean = _truncate(_clean_text(content), 500)
        if not clean:
            raise ValueError("memory note content is empty")

        tag = _truncate(_clean_text(kind or "note"), 32) or "note"
        line = f"- [{tag}] {clean}"
        text = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        updated_doc = self._append_line_to_section(text, "长期记忆", line)
        self._write_agents_md_text(user_id=user_id, workspace=workspace, content=updated_doc)

        notes = self._notes_from_agents_md(user_id=user_id, workspace=workspace, limit=64)
        # 取最新一条作为刚写入的 note 投影；如果解析失败就构造一个兜底对象。
        if notes:
            return notes[-1]
        return MemoryNote(
            id=1,
            user_id=user_id,
            kind=tag,
            content=clean,
            source=source or "profile",
            updated_at=datetime.now(timezone.utc),
        )

    # Layout-based memory is no longer used as part of the core context and has
    # been removed from the public API surface. The corresponding helpers and
    # DB-backed storage are intentionally omitted in favour of file-based
    # DeepAgents memory and explicit AGENTS.md sections.

    def list_todos(
        self,
        db: Session,
        user_id: int,
        *,
        include_done: bool = True,
        limit: int = 100,
        workspace: str = "default",
    ) -> list[dict[str, Any]]:
        """
        List todo items for the user.

        In the DeepAgents runtime this method is expected to project todos from
        the AGENTS.md file only. Legacy DB-backed todo notes are no longer
        surfaced via this API so that the memory model is fully file-first.
        """
        n = max(1, min(200, int(limit or 100)))
        projected = self._todos_from_agents_md(
            user_id=user_id,
            workspace=workspace,
            include_done=include_done,
            limit=n,
        )
        return projected

    # Historic "pin recommendations" based on layout + message statistics have
    # been removed from the public API surface and are no longer used by the
    # main UI. When needed in the future, they should be reintroduced on top
    # of file-backed memory or explicit analytics rather than DB-specific
    # layout notes.

    def build_focus_items(self, db: Session, user_id: int, *, query: str = "", limit: int = 8) -> list[FocusItem]:
        """
        Legacy inbox-backed focus items have been removed.

        Aelin 现在的记忆模型只依赖 DeepAgents 的 AGENTS.md / file memory，
        不再从联系人 / 消息表投影“重点消息”。
        """
        _ = db, user_id, query, limit
        return []

    # Advanced inbox search for the legacy `/agent` surface has been removed.
    # New search scenarios should be implemented as explicit tools instead of
    # embedding DB-specific query logic inside the memory service.

    def build_memory_layers_from_items(
        self,
        *,
        summary: str,
        notes: list[MemoryNote] | None,
        focus_items: list[FocusItem] | None,
        todos: list[dict[str, Any]] | None,
        layout_cards: list[dict[str, Any]] | None,
        workspace: str = "default",
        query: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        _ = workspace, query
        now_iso = datetime.now(timezone.utc).isoformat()
        facts: list[dict[str, Any]] = []
        preferences: list[dict[str, Any]] = []
        in_progress: list[dict[str, Any]] = []

        def _push(
            bucket: list[dict[str, Any]],
            *,
            item_id: str,
            layer: str,
            title: str,
            detail: str,
            source: str,
            confidence: float,
            updated_at: str,
            meta: dict[str, str] | None = None,
            max_items: int = 12,
        ) -> None:
            clean_title = _truncate(_clean_text(title), 140)
            if not clean_title:
                return
            clean_detail = _truncate(_clean_text(detail), 280)
            if any((row.get("title") or "") == clean_title for row in bucket):
                return
            bucket.append(
                {
                    "id": item_id,
                    "layer": layer,
                    "title": clean_title,
                    "detail": clean_detail,
                    "source": _truncate(_clean_text(source), 64),
                    "confidence": max(0.0, min(1.0, float(confidence))),
                    "updated_at": updated_at or now_iso,
                    "meta": meta or {},
                }
            )
            if len(bucket) > max_items:
                del bucket[max_items:]

        if summary:
            _push(
                facts,
                item_id="summary",
                layer="fact",
                title="近期对话摘要",
                detail=str(summary),
                source="chat_summary",
                confidence=0.66,
                updated_at=now_iso,
                max_items=14,
            )

        for row in list(notes or [])[:24]:
            kind = _truncate(_clean_text(str(getattr(row, "kind", "") or "")), 32).lower()
            source = _truncate(_clean_text(str(getattr(row, "source", "") or "")), 64) or kind or "memory"
            content = _truncate(_clean_text(str(getattr(row, "content", "") or "")), 280)
            if not content:
                continue
            bucket = preferences if kind in {"preference", "profile"} else in_progress if kind in {"in_progress", "todo"} else facts
            layer = "preference" if bucket is preferences else "in_progress" if bucket is in_progress else "fact"
            _push(
                bucket,
                item_id=f"note-{int(getattr(row, 'id', 0) or 0)}",
                layer=layer,
                title=content[:80],
                detail=content,
                source=source,
                confidence=0.62,
                updated_at=_iso_or_empty(getattr(row, "updated_at", None)) or now_iso,
            )

        for item in list(focus_items or [])[:10]:
            _push(
                in_progress,
                item_id=f"focus-{int(getattr(item, 'message_id', 0) or 0)}",
                layer="in_progress",
                title=str(getattr(item, "title", "") or ""),
                detail=f"{_SOURCE_LABELS.get(str(getattr(item, 'source', '') or ''), str(getattr(item, 'source', '') or '消息'))} · {str(getattr(item, 'sender', '') or '')}",
                source=str(getattr(item, "source", "") or "focus"),
                confidence=min(0.95, max(0.4, float(getattr(item, "score", 0.0) or 0.0) / 10.0)),
                updated_at=str(getattr(item, "received_at", "") or now_iso),
                meta={"message_id": str(int(getattr(item, "message_id", 0) or 0))},
                max_items=14,
            )

        for todo in list(todos or [])[:12]:
            _push(
                in_progress,
                item_id=f"todo-{int(todo.get('id') or 0)}",
                layer="in_progress",
                title=str(todo.get("title") or ""),
                detail=str(todo.get("detail") or ""),
                source="todo",
                confidence=0.88 if str(todo.get("priority") or "").lower() == "high" else 0.78,
                updated_at=str(todo.get("updated_at") or now_iso),
                meta={
                    "todo_id": str(todo.get("id") or ""),
                    "priority": str(todo.get("priority") or "normal"),
                },
                max_items=14,
            )

        pinned_names = [
            str(row.get("display_name") or row.get("contact_id") or "")
            for row in list(layout_cards or [])
            if isinstance(row, dict) and bool(row.get("pinned"))
        ][:8]
        if pinned_names:
            _push(
                preferences,
                item_id="layout-pinned",
                layer="preference",
                title="卡片关注顺序偏好",
                detail="优先关注: " + "、".join([name for name in pinned_names if name]),
                source="layout",
                confidence=0.72,
                updated_at=now_iso,
                max_items=12,
            )

        return {
            "facts": facts[:14],
            "preferences": preferences[:12],
            "in_progress": in_progress[:14],
        }

    # DeepAgents chat-loop entrypoint is implemented above as
    # `get_agents_memory_text`. All methods below this point are used for
    # UI/context projections only and are intentionally decoupled from the
    # agent loop's core behaviour.


_memory_service = AgentMemoryService()


def get_agent_memory_service() -> AgentMemoryService:
    return _memory_service

