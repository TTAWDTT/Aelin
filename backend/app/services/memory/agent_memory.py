from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import threading
from typing import Any

from sqlalchemy.orm import Session

from app.services.memory.agent_memory_utils import (
    _clean_text,
    _iso_or_empty,
    _truncate,
)
from app.services.memory.file_memory_bridge import file_memory_bridge

_SOURCE_LABELS = {
    "x": "X",
    "douyin": "Douyin",
    "bilibili": "Bilibili",
    "xiaohongshu": "Xiaohongshu",
    "weibo": "Weibo",
    "web": "Web",
    "rss": "RSS",
    "github": "GitHub",
    "imap": "Email",
    "mock": "Message",
}
_TODO_SOURCE = "todo"
_LAYOUT_SOURCE = "card_layout"
_MEMORY_STORE_PATH = "_structured_memory.json"
_PROFILE_MEMORY_PATH = "PROFILE.md"
_PREFERENCES_MEMORY_PATH = "PREFERENCES.md"
_FACTS_MEMORY_PATH = "FACTS.md"
_PROJECTS_MEMORY_PATH = "PROJECTS.md"
_RECENT_CONTEXT_MEMORY_PATH = "RECENT_CONTEXT.md"
_TODOS_MEMORY_PATH = "TODOS.md"
_INDEX_MEMORY_PATH = "INDEX.json"
_STRUCTURED_MEMORY_CORRUPT_PREFIX = "_structured_memory.corrupt"
_SUMMARY_SECTION_ALIASES = ("summary", "\u4f1a\u8bdd\u6458\u8981")
_LONG_TERM_MEMORY_SECTION_ALIASES = (
    "long_term_memory",
    "long-term memory",
    "\u957f\u671f\u8bb0\u5fc6",
)
_TODO_SECTION_ALIASES = ("todos", "todo", "\u5f85\u529e")
_PROFILE_SECTION_ALIASES = ("profile", "user_profile", "\u7528\u6237\u6863\u6848")
_PROJECT_SECTION_ALIASES = ("projects", "active_projects", "\u9879\u76ee")
_FACT_KIND_ALIASES = {"fact", "\u4e8b\u5b9e"}
_PREFERENCE_KIND_ALIASES = {"preference", "profile", "\u504f\u597d", "\u559c\u597d"}
_IN_PROGRESS_KIND_ALIASES = {"in_progress", "in-progress", "todo", "\u8fdb\u884c\u4e2d"}
_DONE_TODO_ALIASES = {"x", "done", "\u5b8c\u6210"}
_HIGH_PRIORITY_TODO_ALIASES = {"!", "high", "high-priority", "\u91cd\u8981"}
_DEFAULT_PROFILE_FIELDS = (
    "name",
    "role",
    "team",
    "location",
    "timezone",
    "language",
    "communication_style",
    "working_preferences",
)
_MAX_RUNTIME_PROMPT_CHARS = 4200
_MAX_FACT_NOTES = 80
_MAX_PREFERENCE_NOTES = 60
_MAX_IN_PROGRESS_NOTES = 36
_MAX_GENERAL_NOTES = 60
_MAX_ACTIVE_PROJECTS = 24
_MAX_INACTIVE_PROJECTS = 12
_MAX_RECENT_CONTEXT_ITEMS = 18
_MAX_ACTIVE_TODOS = 24
_MAX_DONE_TODOS = 10
_MEMORY_BUNDLE_CACHE_MAX_ENTRIES = 64


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
    id: int
    user_id: int
    kind: str
    content: str
    source: str | None
    updated_at: datetime


class AgentMemoryService:
    """File-first memory service with a structured canonical store."""

    def __init__(self) -> None:
        self._bundle_cache_lock = threading.RLock()
        self._memory_bundle_cache: OrderedDict[tuple[int, str, str, str], dict[str, Any]] = OrderedDict()
        self._search_cache_lock = threading.RLock()
        self._search_candidate_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _now_iso(self) -> str:
        return self._now().isoformat()

    def _normalize_heading(self, value: str) -> str:
        return _clean_text(value).lower().replace("-", "_").replace(" ", "_")

    def _normalize_identity(self, value: str) -> str:
        return self._normalize_heading(value).replace("_", "")

    def _parse_updated_at(self, value: Any) -> datetime | None:
        raw = _clean_text(str(value or ""))
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _updated_at_sort_key(self, row: dict[str, Any]) -> tuple[float, int]:
        parsed = self._parse_updated_at(row.get("updated_at"))
        timestamp = parsed.timestamp() if parsed is not None else 0.0
        try:
            row_id = int(row.get("id") or 0)
        except Exception:
            row_id = 0
        return timestamp, row_id

    def _fingerprint_text(self, value: str) -> str:
        return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()

    def _fingerprint_store(self, store: dict[str, Any]) -> str:
        payload = json.dumps(
            self._normalize_store(store),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._fingerprint_text(payload)

    def _copy_memory_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "prompt_path": str(bundle.get("prompt_path") or "/memory/AGENTS.md"),
            "prompt_text": str(bundle.get("prompt_text") or ""),
            "files": {
                str(path): str(content or "")
                for path, content in dict(bundle.get("files") or {}).items()
            },
            "memory_paths": [str(path) for path in list(bundle.get("memory_paths") or []) if str(path or "").strip()],
            "index": dict(bundle.get("index") or {}),
        }

    def _cached_memory_bundle(self, key: tuple[int, str, str, str]) -> dict[str, Any] | None:
        with self._bundle_cache_lock:
            cached = self._memory_bundle_cache.get(key)
            if cached is None:
                return None
            self._memory_bundle_cache.move_to_end(key)
            return self._copy_memory_bundle(cached)

    def _remember_memory_bundle(self, key: tuple[int, str, str, str], bundle: dict[str, Any]) -> dict[str, Any]:
        stored = self._copy_memory_bundle(bundle)
        with self._bundle_cache_lock:
            self._memory_bundle_cache[key] = stored
            self._memory_bundle_cache.move_to_end(key)
            while len(self._memory_bundle_cache) > _MEMORY_BUNDLE_CACHE_MAX_ENTRIES:
                self._memory_bundle_cache.popitem(last=False)
        return self._copy_memory_bundle(stored)

    def _clear_memory_bundle_cache_for_scope(self, *, user_id: int, workspace: str) -> None:
        with self._bundle_cache_lock:
            keys_to_drop = [
                key
                for key in self._memory_bundle_cache.keys()
                if key[0] == int(user_id) and key[1] == str(workspace or "default")
            ]
            for key in keys_to_drop:
                self._memory_bundle_cache.pop(key, None)

    def _cached_search_candidates(self, store_fingerprint: str) -> list[dict[str, Any]] | None:
        with self._search_cache_lock:
            cached = self._search_candidate_cache.get(store_fingerprint)
            if cached is None:
                return None
            self._search_candidate_cache.move_to_end(store_fingerprint)
            return [dict(row) for row in cached]

    def _remember_search_candidates(
        self,
        store_fingerprint: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stored = [dict(row) for row in rows]
        with self._search_cache_lock:
            self._search_candidate_cache[store_fingerprint] = stored
            self._search_candidate_cache.move_to_end(store_fingerprint)
            while len(self._search_candidate_cache) > _MEMORY_BUNDLE_CACHE_MAX_ENTRIES:
                self._search_candidate_cache.popitem(last=False)
        return [dict(row) for row in stored]

    def _clear_search_candidate_cache(self) -> None:
        with self._search_cache_lock:
            self._search_candidate_cache.clear()

    def _normalize_note_kind(self, value: str) -> str:
        normalized = self._normalize_heading(value)
        if normalized in {self._normalize_heading(item) for item in _FACT_KIND_ALIASES}:
            return "fact"
        if normalized in {self._normalize_heading(item) for item in _PREFERENCE_KIND_ALIASES}:
            return "preference"
        if normalized in {self._normalize_heading(item) for item in _IN_PROGRESS_KIND_ALIASES}:
            return "in_progress"
        return "note"

    def _normalize_todo_priority(self, value: str) -> str:
        normalized = self._normalize_heading(value)
        if normalized in {self._normalize_heading(item) for item in _HIGH_PRIORITY_TODO_ALIASES}:
            return "high"
        return "normal"

    def _section_name_matches(self, name: str, aliases: tuple[str, ...]) -> bool:
        normalized = self._normalize_heading(name)
        return normalized in {self._normalize_heading(item) for item in aliases}

    def _read_agents_md_text(self, user_id: int, workspace: str = "default") -> str:
        try:
            text = file_memory_bridge.read_agents_memory(user_id=user_id, workspace=workspace)
        except Exception:
            return ""
        return str(text or "")

    def _write_agents_md_text(self, user_id: int, workspace: str, content: str) -> None:
        try:
            file_memory_bridge.write_agents_memory(
                user_id=user_id,
                workspace=workspace,
                content=str(content or ""),
            )
        except Exception:
            return

    def _parse_agents_md_sections(self, text: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        if not text:
            return sections
        current: str | None = None
        for raw in str(text).splitlines():
            line = str(raw or "")
            if line.startswith("## "):
                current = line[3:].strip()
                if current:
                    sections.setdefault(current, [])
                else:
                    current = None
                continue
            if current is None:
                continue
            sections.setdefault(current, []).append(line)
        return sections

    def _find_section_lines(self, sections: dict[str, list[str]], aliases: tuple[str, ...]) -> list[str]:
        for name, lines in sections.items():
            if self._section_name_matches(name, aliases):
                return list(lines)
        return []

    def _append_line_to_section(self, text: str, section: str, line: str) -> str:
        base = str(text or "")
        header = f"## {section}"
        if not base.strip():
            base = "# Aelin Session Memory\n\n"

        idx = base.find(header)
        if idx < 0:
            if not base.endswith("\n"):
                base += "\n"
            return base + f"\n{header}\n{line}\n"

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

    def _default_store(self) -> dict[str, Any]:
        return {
            "version": 3,
            "summary": {
                "content": "",
                "updated_at": "",
            },
            "profile": {
                "fields": {},
                "updated_at": "",
            },
            "notes": [],
            "projects": [],
            "recent_context": [],
            "todos": [],
            "meta": {
                "schema": "aelin-structured-memory-v3",
                "last_projected_at": "",
            },
        }

    def _next_numeric_id(self, items: list[dict[str, Any]]) -> int:
        current = 0
        for row in items:
            try:
                current = max(current, int(row.get("id") or 0))
            except Exception:
                continue
        return current + 1

    def _normalize_summary_payload(self, value: Any) -> dict[str, str]:
        if isinstance(value, dict):
            content = _truncate(_clean_text(str(value.get("content") or "")), 1000)
            updated_at = _truncate(_clean_text(str(value.get("updated_at") or "")), 64)
            return {
                "content": content,
                "updated_at": updated_at,
            }
        return {
            "content": _truncate(_clean_text(str(value or "")), 1000),
            "updated_at": "",
        }

    def _normalize_note_item(self, row: Any, *, fallback_id: int) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        content = _truncate(_clean_text(str(row.get("content") or "")), 500)
        if not content:
            return None
        try:
            note_id = int(row.get("id") or 0)
        except Exception:
            note_id = 0
        note_id = note_id if note_id > 0 else fallback_id
        return {
            "id": note_id,
            "kind": self._normalize_note_kind(str(row.get("kind") or "note")),
            "content": content,
            "source": _truncate(_clean_text(str(row.get("source") or "memory")), 64) or "memory",
            "updated_at": _truncate(_clean_text(str(row.get("updated_at") or self._now_iso())), 64),
        }

    def _normalize_todo_item(self, row: Any, *, fallback_id: int) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        title = _truncate(_clean_text(str(row.get("title") or "")), 240)
        if not title:
            return None
        try:
            todo_id = int(row.get("id") or 0)
        except Exception:
            todo_id = 0
        todo_id = todo_id if todo_id > 0 else fallback_id
        return {
            "id": todo_id,
            "title": title,
            "detail": _truncate(_clean_text(str(row.get("detail") or "")), 500),
            "done": bool(row.get("done", False)),
            "priority": self._normalize_todo_priority(str(row.get("priority") or "normal")),
            "due_at": _truncate(_clean_text(str(row.get("due_at") or "")), 64),
            "updated_at": _truncate(_clean_text(str(row.get("updated_at") or self._now_iso())), 64),
        }

    def _normalize_profile_payload(self, value: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"fields": {}, "updated_at": ""}
        if not isinstance(value, dict):
            return out
        raw_fields = value.get("fields")
        if not isinstance(raw_fields, dict):
            raw_fields = {
                key: item
                for key, item in value.items()
                if str(key) != "updated_at"
            }
        fields: dict[str, str] = {}
        for raw_key, raw_value in raw_fields.items():
            key = _truncate(_clean_text(str(raw_key or "")), 48).lower().replace("-", "_").replace(" ", "_")
            item = _truncate(_clean_text(str(raw_value or "")), 240)
            if key and item:
                fields[key] = item
        out["fields"] = fields
        out["updated_at"] = _truncate(_clean_text(str(value.get("updated_at") or "")), 64)
        return out

    def _normalize_project_item(self, row: Any, *, fallback_id: int) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        name = _truncate(_clean_text(str(row.get("name") or row.get("title") or "")), 120)
        if not name:
            return None
        try:
            project_id = int(row.get("id") or 0)
        except Exception:
            project_id = 0
        project_id = project_id if project_id > 0 else fallback_id
        tags: list[str] = []
        for raw_tag in list(row.get("tags") or [])[:8]:
            tag = _truncate(_clean_text(str(raw_tag or "")), 40)
            if tag and tag not in tags:
                tags.append(tag)
        return {
            "id": project_id,
            "name": name,
            "status": _truncate(_clean_text(str(row.get("status") or "active")), 32) or "active",
            "summary": _truncate(_clean_text(str(row.get("summary") or "")), 280),
            "detail": _truncate(_clean_text(str(row.get("detail") or "")), 500),
            "tags": tags,
            "updated_at": _truncate(_clean_text(str(row.get("updated_at") or self._now_iso())), 64),
        }

    def _normalize_recent_context_item(self, row: Any, *, fallback_id: int) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        content = _truncate(_clean_text(str(row.get("content") or row.get("detail") or "")), 500)
        title = _truncate(_clean_text(str(row.get("title") or "")), 120)
        if not content and not title:
            return None
        try:
            context_id = int(row.get("id") or 0)
        except Exception:
            context_id = 0
        context_id = context_id if context_id > 0 else fallback_id
        return {
            "id": context_id,
            "title": title,
            "content": content or title,
            "source": _truncate(_clean_text(str(row.get("source") or "memory")), 64) or "memory",
            "updated_at": _truncate(_clean_text(str(row.get("updated_at") or self._now_iso())), 64),
        }

    def _normalize_store(self, payload: Any) -> dict[str, Any]:
        store = self._default_store()
        if not isinstance(payload, dict):
            return store

        try:
            version = int(payload.get("version") or 0)
        except Exception:
            version = 0
        store["version"] = version if version > 0 else 3
        store["summary"] = self._normalize_summary_payload(payload.get("summary"))
        store["profile"] = self._normalize_profile_payload(payload.get("profile"))

        notes: list[dict[str, Any]] = []
        for row in list(payload.get("notes") or []):
            item = self._normalize_note_item(row, fallback_id=self._next_numeric_id(notes))
            if item is not None:
                notes.append(item)
        store["notes"] = notes

        projects: list[dict[str, Any]] = []
        for row in list(payload.get("projects") or []):
            item = self._normalize_project_item(row, fallback_id=self._next_numeric_id(projects))
            if item is not None:
                projects.append(item)
        store["projects"] = projects

        recent_context: list[dict[str, Any]] = []
        for row in list(payload.get("recent_context") or []):
            item = self._normalize_recent_context_item(row, fallback_id=self._next_numeric_id(recent_context))
            if item is not None:
                recent_context.append(item)
        store["recent_context"] = recent_context

        todos: list[dict[str, Any]] = []
        for row in list(payload.get("todos") or []):
            item = self._normalize_todo_item(row, fallback_id=self._next_numeric_id(todos))
            if item is not None:
                todos.append(item)
        store["todos"] = todos

        meta = payload.get("meta")
        store["meta"] = dict(meta) if isinstance(meta, dict) else {}
        store["meta"]["schema"] = str(store["meta"].get("schema") or "aelin-structured-memory-v3")
        store["meta"]["last_projected_at"] = _truncate(
            _clean_text(str(store["meta"].get("last_projected_at") or "")),
            64,
        )
        return store

    def _prefer_richer_text(self, left: str, right: str, *, max_chars: int) -> str:
        left_clean = _truncate(_clean_text(left), max_chars)
        right_clean = _truncate(_clean_text(right), max_chars)
        if not left_clean:
            return right_clean
        if not right_clean:
            return left_clean
        left_identity = self._normalize_identity(left_clean)
        right_identity = self._normalize_identity(right_clean)
        if left_identity == right_identity:
            return left_clean if len(left_clean) >= len(right_clean) else right_clean
        if left_identity and left_identity in right_identity:
            return right_clean
        if right_identity and right_identity in left_identity:
            return left_clean
        return right_clean if len(right_clean) >= len(left_clean) else left_clean

    def _is_active_project_status(self, value: str) -> bool:
        normalized = self._normalize_heading(value)
        return normalized not in {"done", "completed", "complete", "archived", "cancelled", "closed"}

    def _project_status_rank(self, value: str) -> int:
        normalized = self._normalize_heading(value)
        if normalized in {"active", "doing", "ongoing", "in_progress"}:
            return 0
        if normalized in {"blocked", "paused"}:
            return 1
        if normalized in {"planned", "backlog"}:
            return 2
        if normalized in {"done", "completed", "complete"}:
            return 3
        if normalized in {"archived", "cancelled", "closed"}:
            return 4
        return 2

    def _merge_project_items(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        current_rank = self._project_status_rank(str(current.get("status") or "active"))
        incoming_rank = self._project_status_rank(str(incoming.get("status") or "active"))
        merged["name"] = self._prefer_richer_text(
            str(current.get("name") or ""),
            str(incoming.get("name") or ""),
            max_chars=120,
        )
        merged["status"] = (
            str(incoming.get("status") or "active")
            if incoming_rank <= current_rank
            else str(current.get("status") or "active")
        )
        merged["summary"] = self._prefer_richer_text(
            str(current.get("summary") or ""),
            str(incoming.get("summary") or ""),
            max_chars=280,
        )
        merged["detail"] = self._prefer_richer_text(
            str(current.get("detail") or ""),
            str(incoming.get("detail") or ""),
            max_chars=500,
        )
        tags: list[str] = []
        for raw_tag in [*list(current.get("tags") or []), *list(incoming.get("tags") or [])]:
            tag = _truncate(_clean_text(str(raw_tag or "")), 40)
            if tag and tag not in tags:
                tags.append(tag)
        merged["tags"] = tags[:8]
        merged["updated_at"] = max(
            str(current.get("updated_at") or ""),
            str(incoming.get("updated_at") or ""),
        )
        return self._normalize_project_item(merged, fallback_id=int(current.get("id") or incoming.get("id") or 1)) or dict(current)

    def _merge_todo_items(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        merged["title"] = self._prefer_richer_text(
            str(current.get("title") or ""),
            str(incoming.get("title") or ""),
            max_chars=240,
        )
        merged["detail"] = self._prefer_richer_text(
            str(current.get("detail") or ""),
            str(incoming.get("detail") or ""),
            max_chars=500,
        )
        merged["done"] = bool(current.get("done")) and bool(incoming.get("done"))
        merged["priority"] = (
            "high"
            if str(current.get("priority") or "") == "high" or str(incoming.get("priority") or "") == "high"
            else "normal"
        )
        merged["due_at"] = self._prefer_richer_text(
            str(current.get("due_at") or ""),
            str(incoming.get("due_at") or ""),
            max_chars=64,
        )
        merged["updated_at"] = max(
            str(current.get("updated_at") or ""),
            str(incoming.get("updated_at") or ""),
        )
        return self._normalize_todo_item(merged, fallback_id=int(current.get("id") or incoming.get("id") or 1)) or dict(current)

    def _compact_notes(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limits = {
            "fact": _MAX_FACT_NOTES,
            "preference": _MAX_PREFERENCE_NOTES,
            "in_progress": _MAX_IN_PROGRESS_NOTES,
            "note": _MAX_GENERAL_NOTES,
        }
        normalized_rows = [
            item
            for item in (
                self._normalize_note_item(row, fallback_id=index + 1)
                for index, row in enumerate(list(rows or []))
            )
            if item is not None
        ]
        normalized_rows.sort(key=self._updated_at_sort_key, reverse=True)
        kept: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        for row in normalized_rows:
            kind = self._normalize_note_kind(str(row.get("kind") or "note"))
            identity = self._normalize_identity(str(row.get("content") or ""))
            dedupe_key = (kind, identity)
            if identity and dedupe_key in seen:
                continue
            if counts.get(kind, 0) >= limits.get(kind, _MAX_GENERAL_NOTES):
                continue
            if identity:
                seen.add(dedupe_key)
            counts[kind] = counts.get(kind, 0) + 1
            kept.append(row)
        kept.sort(key=self._updated_at_sort_key)
        return kept

    def _compact_projects(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_rows = [
            item
            for item in (
                self._normalize_project_item(row, fallback_id=index + 1)
                for index, row in enumerate(list(rows or []))
            )
            if item is not None
        ]
        normalized_rows.sort(key=self._updated_at_sort_key, reverse=True)
        merged: list[dict[str, Any]] = []
        by_name: dict[str, int] = {}
        for row in normalized_rows:
            key = self._normalize_identity(str(row.get("name") or ""))
            if key and key in by_name:
                target_index = by_name[key]
                merged[target_index] = self._merge_project_items(merged[target_index], row)
                continue
            if key:
                by_name[key] = len(merged)
            merged.append(row)
        active = [row for row in merged if self._is_active_project_status(str(row.get("status") or "active"))]
        inactive = [row for row in merged if row not in active]
        active.sort(key=lambda row: (self._project_status_rank(str(row.get("status") or "")), *self._updated_at_sort_key(row)), reverse=False)
        active.sort(key=self._updated_at_sort_key, reverse=True)
        inactive.sort(key=self._updated_at_sort_key, reverse=True)
        kept = active[:_MAX_ACTIVE_PROJECTS] + inactive[:_MAX_INACTIVE_PROJECTS]
        kept.sort(key=self._updated_at_sort_key)
        return kept

    def _compact_recent_context(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_rows = [
            item
            for item in (
                self._normalize_recent_context_item(row, fallback_id=index + 1)
                for index, row in enumerate(list(rows or []))
            )
            if item is not None
        ]
        normalized_rows.sort(key=self._updated_at_sort_key, reverse=True)
        kept: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in normalized_rows:
            dedupe_key = self._normalize_identity(
                f"{str(row.get('title') or '')}|{str(row.get('content') or '')}"
            )
            if dedupe_key and dedupe_key in seen:
                continue
            if dedupe_key:
                seen.add(dedupe_key)
            kept.append(row)
            if len(kept) >= _MAX_RECENT_CONTEXT_ITEMS:
                break
        kept.sort(key=self._updated_at_sort_key)
        return kept

    def _compact_todos(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_rows = [
            item
            for item in (
                self._normalize_todo_item(row, fallback_id=index + 1)
                for index, row in enumerate(list(rows or []))
            )
            if item is not None
        ]
        normalized_rows.sort(key=self._updated_at_sort_key, reverse=True)
        merged: list[dict[str, Any]] = []
        by_identity: dict[str, int] = {}
        for row in normalized_rows:
            dedupe_key = self._normalize_identity(
                f"{str(row.get('title') or '')}|{str(row.get('detail') or '')}"
            )
            if dedupe_key and dedupe_key in by_identity:
                target_index = by_identity[dedupe_key]
                merged[target_index] = self._merge_todo_items(merged[target_index], row)
                continue
            if dedupe_key:
                by_identity[dedupe_key] = len(merged)
            merged.append(row)
        active = [row for row in merged if not bool(row.get("done"))]
        done = [row for row in merged if bool(row.get("done"))]
        active.sort(
            key=lambda row: (
                str(row.get("priority") or "") != "high",
                -self._updated_at_sort_key(row)[0],
                -self._updated_at_sort_key(row)[1],
            )
        )
        done.sort(key=self._updated_at_sort_key, reverse=True)
        kept = active[:_MAX_ACTIVE_TODOS] + done[:_MAX_DONE_TODOS]
        kept.sort(key=self._updated_at_sort_key)
        return kept

    def _compact_store(self, store: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_store(store)
        normalized["notes"] = self._compact_notes(list(normalized.get("notes") or []))
        normalized["projects"] = self._compact_projects(list(normalized.get("projects") or []))
        normalized["recent_context"] = self._compact_recent_context(list(normalized.get("recent_context") or []))
        normalized["todos"] = self._compact_todos(list(normalized.get("todos") or []))
        return normalized

    def _read_memory_store(self, *, user_id: int, workspace: str) -> dict[str, Any] | None:
        try:
            payload = file_memory_bridge.read_memory_json(
                user_id=user_id,
                workspace=workspace,
                path=_MEMORY_STORE_PATH,
            )
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return self._normalize_store(payload)

    def _read_memory_store_status(
        self,
        *,
        user_id: int,
        workspace: str,
    ) -> tuple[dict[str, Any] | None, str, str]:
        store = self._read_memory_store(user_id=user_id, workspace=workspace)
        if store is not None:
            return store, "ok", ""
        raw_payload = file_memory_bridge.read_memory_text(
            user_id=user_id,
            workspace=workspace,
            path=_MEMORY_STORE_PATH,
        )
        if str(raw_payload or "").strip():
            return None, "corrupt", str(raw_payload or "")
        return None, "missing", ""

    def _recover_corrupt_store(
        self,
        *,
        user_id: int,
        workspace: str,
        raw_payload: str,
    ) -> dict[str, Any]:
        timestamp = self._now().strftime("%Y%m%dT%H%M%SZ")
        backup_path = f"{_STRUCTURED_MEMORY_CORRUPT_PREFIX}.{timestamp}.json"
        try:
            file_memory_bridge.write_memory_text(
                user_id=user_id,
                workspace=workspace,
                path=backup_path,
                content=str(raw_payload or ""),
            )
        except Exception:
            backup_path = ""

        agents_md = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        recovered = (
            self._store_from_agents_md_text(agents_md)
            if str(agents_md or "").strip()
            else self._default_store()
        )
        recovered = self._normalize_store(recovered)
        recovered.setdefault("meta", {})
        recovered["meta"]["schema"] = "aelin-structured-memory-v3"
        recovered["meta"]["recovered_from_corrupt_store_at"] = self._now_iso()
        if backup_path:
            recovered["meta"]["recovered_from_corrupt_store_backup"] = backup_path
        return self._persist_memory_store(user_id=user_id, workspace=workspace, store=recovered)

    def _load_memory_store(self, *, user_id: int, workspace: str) -> tuple[dict[str, Any], bool]:
        store, status, raw_payload = self._read_memory_store_status(user_id=user_id, workspace=workspace)
        if store is not None:
            return store, True
        if status == "corrupt":
            return self._recover_corrupt_store(
                user_id=user_id,
                workspace=workspace,
                raw_payload=raw_payload,
            ), True
        agents_md = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        if agents_md.strip():
            return self._store_from_agents_md_text(agents_md), False
        return self._default_store(), False

    def _persist_memory_store(self, *, user_id: int, workspace: str, store: dict[str, Any]) -> dict[str, Any]:
        normalized = self._compact_store(store)
        normalized["version"] = 3
        normalized.setdefault("meta", {})
        normalized["meta"]["schema"] = "aelin-structured-memory-v3"
        normalized["meta"]["last_projected_at"] = self._now_iso()
        runtime_text, projection_files, index_payload = self._projection_files_from_store(normalized)
        self._clear_memory_bundle_cache_for_scope(user_id=user_id, workspace=workspace)
        self._clear_search_candidate_cache()
        file_memory_bridge.write_memory_json(
            user_id=user_id,
            workspace=workspace,
            path=_MEMORY_STORE_PATH,
            payload=normalized,
        )
        for path, content in projection_files.items():
            file_memory_bridge.write_memory_text(
                user_id=user_id,
                workspace=workspace,
                path=path,
                content=content,
            )
        file_memory_bridge.write_memory_json(
            user_id=user_id,
            workspace=workspace,
            path=_INDEX_MEMORY_PATH,
            payload=index_payload,
        )
        files = {
            f"/memory/{path}": str(content or "").strip()
            for path, content in projection_files.items()
            if str(content or "").strip()
        }
        files[f"/memory/{_INDEX_MEMORY_PATH}"] = json.dumps(
            index_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self._remember_memory_bundle(
            (
                int(user_id),
                str(workspace or "default"),
                self._fingerprint_store(normalized),
                self._fingerprint_text("|"),
            ),
            {
                "prompt_path": "/memory/AGENTS.md",
                "prompt_text": str(runtime_text or "").strip(),
                "files": files,
                "memory_paths": ["/memory/AGENTS.md"] if str(runtime_text or "").strip() else [],
                "index": index_payload,
            },
        )
        return normalized

    def _parse_summary_from_sections(self, sections: dict[str, list[str]]) -> dict[str, str]:
        lines = self._find_section_lines(sections, _SUMMARY_SECTION_ALIASES)
        summary_lines: list[str] = []
        for raw in lines:
            line = str(raw or "").strip()
            if not line:
                continue
            summary_lines.append(line.lstrip("- ").strip())
        return {
            "content": _truncate(_clean_text(" ".join(summary_lines)), 1000),
            "updated_at": "",
        }

    def _parse_note_line(self, line: str) -> tuple[str, str] | None:
        text = str(line or "").strip()
        if not text:
            return None
        if text.startswith("-"):
            text = text[1:].strip()
        if not text:
            return None
        match = re.match(r"\[(?P<tag>[^\]]+)\]\s*(?P<body>.+)", text)
        if match:
            return str(match.group("tag") or "").strip(), str(match.group("body") or "").strip()
        return "", text

    def _parse_todo_line(self, line: str) -> tuple[str, str] | None:
        text = str(line or "").strip()
        if not text:
            return None
        if text.startswith("-"):
            text = text[1:].strip()
        if not text:
            return None
        match = re.match(r"\[(?P<tag>[^\]]*)\]\s*(?P<body>.+)", text)
        if match:
            return str(match.group("tag") or "").strip(), str(match.group("body") or "").strip()
        return "", text

    def _store_from_agents_md_text(self, text: str) -> dict[str, Any]:
        sections = self._parse_agents_md_sections(text)
        store = self._default_store()
        store["summary"] = self._parse_summary_from_sections(sections)

        notes: list[dict[str, Any]] = []
        for raw in self._find_section_lines(sections, _LONG_TERM_MEMORY_SECTION_ALIASES):
            parsed = self._parse_note_line(raw)
            if parsed is None:
                continue
            tag, body = parsed
            content = _truncate(_clean_text(body), 500)
            if not content:
                continue
            notes.append(
                {
                    "id": self._next_numeric_id(notes),
                    "kind": self._normalize_note_kind(tag or "note"),
                    "content": content,
                    "source": "agents_md",
                    "updated_at": "",
                }
            )
        store["notes"] = notes

        todos: list[dict[str, Any]] = []
        for raw in self._find_section_lines(sections, _TODO_SECTION_ALIASES):
            parsed = self._parse_todo_line(raw)
            if parsed is None:
                continue
            tag, body = parsed
            title = _truncate(_clean_text(body), 240)
            if not title:
                continue
            normalized_tag = self._normalize_heading(tag)
            todos.append(
                {
                    "id": self._next_numeric_id(todos),
                    "title": title,
                    "detail": "",
                    "done": normalized_tag in {self._normalize_heading(item) for item in _DONE_TODO_ALIASES},
                    "priority": (
                        "high"
                        if normalized_tag in {self._normalize_heading(item) for item in _HIGH_PRIORITY_TODO_ALIASES}
                        else "normal"
                    ),
                    "due_at": "",
                    "updated_at": "",
                }
            )
        store["todos"] = todos
        return self._normalize_store(store)

    def _profile_fields_from_store(self, store: dict[str, Any]) -> list[tuple[str, str]]:
        profile = store.get("profile")
        fields_payload = profile.get("fields") if isinstance(profile, dict) else {}
        fields = dict(fields_payload) if isinstance(fields_payload, dict) else {}
        ordered: list[tuple[str, str]] = []
        for key in _DEFAULT_PROFILE_FIELDS:
            value = _truncate(_clean_text(str(fields.get(key) or "")), 240)
            if value:
                ordered.append((key, value))
        for key in sorted(str(item) for item in fields.keys()):
            if key in {item[0] for item in ordered}:
                continue
            value = _truncate(_clean_text(str(fields.get(key) or "")), 240)
            if value:
                ordered.append((key, value))
        return ordered

    def _notes_by_kind(self, store: dict[str, Any], kind: str) -> list[dict[str, Any]]:
        normalized_kind = self._normalize_note_kind(kind)
        rows = [
            dict(row)
            for row in list(store.get("notes") or [])
            if self._normalize_note_kind(str(row.get("kind") or "")) == normalized_kind
        ]
        rows.sort(
            key=lambda row: (
                str(row.get("updated_at") or ""),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )
        return rows

    def _project_rows_from_store(self, store: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [dict(row) for row in list(store.get("projects") or [])]
        rows.sort(
            key=lambda row: (
                str(row.get("updated_at") or ""),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )
        return rows

    def _recent_context_rows_from_store(self, store: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row in list(store.get("recent_context") or []):
            item = self._normalize_recent_context_item(row, fallback_id=self._next_numeric_id(rows))
            if item is None:
                continue
            dedupe_key = f"{item['title']}|{item['content']}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(item)

        for row in list(store.get("notes") or []):
            kind = self._normalize_note_kind(str(row.get("kind") or "note"))
            if kind not in {"in_progress", "note"}:
                continue
            content = _truncate(_clean_text(str(row.get("content") or "")), 500)
            if not content:
                continue
            item = {
                "id": int(row.get("id") or self._next_numeric_id(rows)),
                "title": content[:80],
                "content": content,
                "source": _truncate(_clean_text(str(row.get("source") or "memory")), 64) or "memory",
                "updated_at": _truncate(_clean_text(str(row.get("updated_at") or "")), 64),
            }
            dedupe_key = f"{item['title']}|{item['content']}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(item)

        rows.sort(
            key=lambda row: (
                str(row.get("updated_at") or ""),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )
        return rows

    def _store_has_meaningful_content(self, store: dict[str, Any]) -> bool:
        return bool(
            _clean_text(str(store.get("summary", {}).get("content") or ""))
            or self._profile_fields_from_store(store)
            or list(store.get("notes") or [])
            or list(store.get("projects") or [])
            or list(store.get("recent_context") or [])
            or list(store.get("todos") or [])
        )

    def _render_profile_md_from_store(self, store: dict[str, Any]) -> str:
        lines = ["# Profile Snapshot", ""]
        fields = self._profile_fields_from_store(store)
        if fields:
            for key, value in fields:
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        else:
            lines.append("- No profile fields recorded yet.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_preferences_md_from_store(self, store: dict[str, Any]) -> str:
        lines = ["# Preferences", ""]
        rows = self._notes_by_kind(store, "preference")
        if rows:
            for row in rows[:24]:
                lines.append(f"- {str(row.get('content') or '').strip()}")
        else:
            lines.append("- No preferences recorded yet.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_facts_md_from_store(self, store: dict[str, Any]) -> str:
        lines = ["# Stable Facts", ""]
        rows = self._notes_by_kind(store, "fact")
        if rows:
            for row in rows[:32]:
                lines.append(f"- {str(row.get('content') or '').strip()}")
        else:
            lines.append("- No stable facts recorded yet.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_projects_md_from_store(self, store: dict[str, Any]) -> str:
        lines = ["# Active Projects", ""]
        rows = self._project_rows_from_store(store)
        if rows:
            for row in rows[:20]:
                status = _truncate(_clean_text(str(row.get("status") or "active")), 32) or "active"
                name = str(row.get("name") or "").strip()
                summary = str(row.get("summary") or "").strip()
                detail = str(row.get("detail") or "").strip()
                tags = ", ".join(str(tag) for tag in list(row.get("tags") or []) if str(tag).strip())
                bullet = f"- [{status}] {name}"
                if summary:
                    bullet += f": {summary}"
                elif detail:
                    bullet += f": {detail}"
                if tags:
                    bullet += f" (tags: {tags})"
                lines.append(bullet)
        else:
            lines.append("- No active projects recorded yet.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_recent_context_md_from_store(self, store: dict[str, Any]) -> str:
        lines = ["# Recent Context", ""]
        rows = self._recent_context_rows_from_store(store)
        if rows:
            for row in rows[:24]:
                title = str(row.get("title") or "").strip()
                content = str(row.get("content") or "").strip()
                source = str(row.get("source") or "").strip()
                if title and content and content != title:
                    bullet = f"- {title}: {content}"
                else:
                    bullet = f"- {content or title}"
                if source:
                    bullet += f" [{source}]"
                lines.append(bullet)
        else:
            lines.append("- No recent context recorded yet.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_todos_md_from_store(self, store: dict[str, Any]) -> str:
        lines = ["# Todos", ""]
        rows = list(store.get("todos") or [])
        if rows:
            for row in rows[:24]:
                badge = "x" if bool(row.get("done")) else "!" if str(row.get("priority") or "") == "high" else " "
                title = str(row.get("title") or "").strip()
                detail = str(row.get("detail") or "").strip()
                bullet = f"- [{badge}] {title}"
                if detail:
                    bullet += f": {detail}"
                lines.append(bullet)
        else:
            lines.append("- [ ] No active todos.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _build_memory_index(self, store: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "generated_at": self._now_iso(),
            "runtime_prompt_path": "/memory/AGENTS.md",
            "counts": {
                "profile_fields": len(self._profile_fields_from_store(store)),
                "facts": len(self._notes_by_kind(store, "fact")),
                "preferences": len(self._notes_by_kind(store, "preference")),
                "projects": len(self._project_rows_from_store(store)),
                "recent_context": len(self._recent_context_rows_from_store(store)),
                "todos": len(list(store.get("todos") or [])),
            },
            "files": [
                {"path": "/memory/AGENTS.md", "kind": "runtime_prompt", "title": "Runtime memory prompt"},
                {"path": f"/memory/{_PROFILE_MEMORY_PATH}", "kind": "profile", "title": "Profile snapshot"},
                {"path": f"/memory/{_PREFERENCES_MEMORY_PATH}", "kind": "preferences", "title": "Stable preferences"},
                {"path": f"/memory/{_FACTS_MEMORY_PATH}", "kind": "facts", "title": "Stable facts"},
                {"path": f"/memory/{_PROJECTS_MEMORY_PATH}", "kind": "projects", "title": "Active projects"},
                {"path": f"/memory/{_RECENT_CONTEXT_MEMORY_PATH}", "kind": "recent_context", "title": "Recent context"},
                {"path": f"/memory/{_TODOS_MEMORY_PATH}", "kind": "todos", "title": "Todo items"},
                {"path": f"/memory/{_INDEX_MEMORY_PATH}", "kind": "index", "title": "Memory index"},
            ],
        }

    def _projection_files_from_store(self, store: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any]]:
        runtime_text = self._render_agents_md_from_store(store)
        index_payload = self._build_memory_index(store)
        files = {
            "AGENTS.md": runtime_text,
            _PROFILE_MEMORY_PATH: self._render_profile_md_from_store(store),
            _PREFERENCES_MEMORY_PATH: self._render_preferences_md_from_store(store),
            _FACTS_MEMORY_PATH: self._render_facts_md_from_store(store),
            _PROJECTS_MEMORY_PATH: self._render_projects_md_from_store(store),
            _RECENT_CONTEXT_MEMORY_PATH: self._render_recent_context_md_from_store(store),
            _TODOS_MEMORY_PATH: self._render_todos_md_from_store(store),
        }
        return runtime_text, files, index_payload

    def _render_note_tag(self, kind: str) -> str:
        normalized = self._normalize_note_kind(kind)
        if normalized == "fact":
            return "fact"
        if normalized == "preference":
            return "preference"
        if normalized == "in_progress":
            return "in_progress"
        return "note"

    def _runtime_project_rows(self, store: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self._project_rows_from_store(store)
        rows.sort(
            key=lambda row: (
                not self._is_active_project_status(str(row.get("status") or "active")),
                self._project_status_rank(str(row.get("status") or "active")),
                -self._updated_at_sort_key(row)[0],
                -self._updated_at_sort_key(row)[1],
            )
        )
        return rows

    def _runtime_todo_rows(self, store: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [self._normalize_todo_item(row, fallback_id=index + 1) for index, row in enumerate(list(store.get("todos") or []))]
        normalized = [row for row in rows if row is not None]
        normalized.sort(
            key=lambda row: (
                bool(row.get("done")),
                str(row.get("priority") or "") != "high",
                -self._updated_at_sort_key(row)[0],
                -self._updated_at_sort_key(row)[1],
            )
        )
        active = [row for row in normalized if not bool(row.get("done"))][:5]
        done = [row for row in normalized if bool(row.get("done"))][:2]
        return active + done

    def _render_agents_md_from_store(self, store: dict[str, Any]) -> str:
        normalized = self._normalize_store(store)
        lines: list[str] = ["# Aelin Session Memory", ""]

        summary = str(normalized.get("summary", {}).get("content") or "").strip()
        lines.extend(["## Summary"])
        if summary:
            lines.append(summary)
        else:
            lines.append("- No summary recorded yet.")
        lines.append("")

        lines.extend(["## Profile Snapshot"])
        profile_fields = self._profile_fields_from_store(normalized)
        if profile_fields:
            for key, value in profile_fields[:4]:
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        else:
            lines.append("- No profile fields recorded yet.")
        lines.append("")

        lines.extend(["## Preferences"])
        preferences = self._notes_by_kind(normalized, "preference")
        if preferences:
            for row in preferences[:4]:
                lines.append(f"- {str(row.get('content') or '').strip()}")
        else:
            lines.append("- No preferences recorded yet.")
        lines.append("")

        lines.extend(["## Long-term Memory"])
        facts = self._notes_by_kind(normalized, "fact")
        if facts:
            for row in facts[:5]:
                lines.append(f"- [{self._render_note_tag(str(row.get('kind') or 'fact'))}] {str(row.get('content') or '').strip()}")
        else:
            lines.append("- No stable facts recorded yet.")
        lines.append("")

        lines.extend(["## Active Projects"])
        projects = self._runtime_project_rows(normalized)
        if projects:
            for row in projects[:4]:
                status = _truncate(_clean_text(str(row.get("status") or "active")), 32) or "active"
                name = str(row.get("name") or "").strip()
                summary_text = str(row.get("summary") or row.get("detail") or "").strip()
                bullet = f"- [{status}] {name}"
                if summary_text:
                    bullet += f": {summary_text}"
                lines.append(bullet)
        else:
            lines.append("- No active projects recorded yet.")
        lines.append("")

        lines.extend(["## Current Focus"])
        recent_context = self._recent_context_rows_from_store(normalized)
        if recent_context:
            for row in recent_context[:4]:
                content = str(row.get("content") or row.get("title") or "").strip()
                if content:
                    lines.append(f"- {content}")
        else:
            lines.append("- No recent context recorded yet.")
        lines.append("")

        lines.extend(["## Todos"])
        todos = self._runtime_todo_rows(normalized)
        if todos:
            for row in todos:
                badge = "x" if bool(row.get("done")) else "!" if str(row.get("priority") or "") == "high" else " "
                title = str(row.get("title") or "").strip()
                detail = str(row.get("detail") or "").strip()
                rendered_title = title if not detail else f"{title}: {detail}"
                lines.append(f"- [{badge}] {rendered_title}")
        else:
            lines.append("- [ ] No active todos.")
        lines.append("")

        lines.extend(["## Memory Map"])
        lines.append(f"- /memory/{_PROFILE_MEMORY_PATH}")
        lines.append(f"- /memory/{_PREFERENCES_MEMORY_PATH}")
        lines.append(f"- /memory/{_FACTS_MEMORY_PATH}")
        lines.append(f"- /memory/{_PROJECTS_MEMORY_PATH}")
        lines.append(f"- /memory/{_RECENT_CONTEXT_MEMORY_PATH}")
        lines.append(f"- /memory/{_TODOS_MEMORY_PATH}")
        lines.append(f"- /memory/{_INDEX_MEMORY_PATH}")
        lines.append("")
        rendered = "\n".join(lines).strip() + "\n"
        if len(rendered) <= _MAX_RUNTIME_PROMPT_CHARS:
            return rendered
        clipped = _truncate(rendered, _MAX_RUNTIME_PROMPT_CHARS - 72).rstrip()
        return clipped + "\n\n- Runtime prompt trimmed; use memory_search for deeper recall.\n"

    def _memory_note_from_store(self, *, user_id: int, row: dict[str, Any]) -> MemoryNote:
        updated_at_raw = str(row.get("updated_at") or "").strip()
        try:
            updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else self._now()
        except Exception:
            updated_at = self._now()
        return MemoryNote(
            id=int(row.get("id") or 0),
            user_id=user_id,
            kind=self._normalize_note_kind(str(row.get("kind") or "note")),
            content=_truncate(_clean_text(str(row.get("content") or "")), 500),
            source=_truncate(_clean_text(str(row.get("source") or "")), 64) or "memory",
            updated_at=updated_at,
        )

    def _notes_from_store(
        self,
        *,
        user_id: int,
        workspace: str,
        limit: int,
    ) -> list[MemoryNote]:
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        rows = list(store.get("notes") or [])
        notes = [self._memory_note_from_store(user_id=user_id, row=row) for row in rows]
        notes.sort(key=lambda row: (row.updated_at, row.id), reverse=True)
        return notes[: max(1, min(50, int(limit or 12)))]

    def _todos_from_store(
        self,
        *,
        user_id: int,
        workspace: str,
        include_done: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        rows = list(store.get("todos") or [])
        todos: list[dict[str, Any]] = []
        for row in rows:
            if bool(row.get("done")) and not include_done:
                continue
            todos.append(
                {
                    "id": int(row.get("id") or 0),
                    "title": _truncate(_clean_text(str(row.get("title") or "")), 240),
                    "detail": _truncate(_clean_text(str(row.get("detail") or "")), 500),
                    "done": bool(row.get("done")),
                    "due_at": str(row.get("due_at") or "") or None,
                    "priority": self._normalize_todo_priority(str(row.get("priority") or "normal")),
                    "contact_id": None,
                    "message_id": None,
                    "updated_at": str(row.get("updated_at") or ""),
                }
            )
        todos.sort(
            key=lambda row: (
                bool(row.get("done")),
                str(row.get("priority") or "") != "high",
                str(row.get("updated_at") or ""),
                int(row.get("id") or 0),
            )
        )
        return todos[: max(1, min(200, int(limit or 100)))]

    def _normalize_search_kind(self, value: str) -> str:
        normalized = self._normalize_heading(value)
        if not normalized:
            return ""
        if normalized in {"profile"}:
            return "profile"
        if normalized in {self._normalize_heading(item) for item in _FACT_KIND_ALIASES}:
            return "fact"
        if normalized in {self._normalize_heading(item) for item in _PREFERENCE_KIND_ALIASES}:
            return "preference"
        if normalized in {self._normalize_heading(item) for item in _IN_PROGRESS_KIND_ALIASES}:
            return "recent_context"
        if normalized in {"summary"}:
            return "summary"
        if normalized in {"project", "projects"}:
            return "project"
        if normalized in {"todo", "todos"}:
            return "todo"
        if normalized in {"recent_context", "recent"}:
            return "recent_context"
        if normalized in {"note", "notes"}:
            return "note"
        return ""

    def _tokenize_search_text(self, value: str) -> list[str]:
        text = _clean_text(value).lower()
        if not text:
            return []
        parts = re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", text)
        return [part for part in parts if part]

    def _search_candidate_rows_from_store(self, store: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        summary = _truncate(_clean_text(str(store.get("summary", {}).get("content") or "")), 1000)
        summary_updated_at = _truncate(_clean_text(str(store.get("summary", {}).get("updated_at") or "")), 64)
        if summary:
            rows.append(
                {
                    "canonical_id": "summary",
                    "path": "/memory/AGENTS.md",
                    "target": "/memory/AGENTS.md",
                    "title": "Conversation summary",
                    "preview": summary,
                    "updated_at": summary_updated_at,
                    "source": "memory",
                    "kind": "summary",
                    "topic_path": "memory/summary",
                    "entry_kind": "summary",
                }
            )

        for key, value in self._profile_fields_from_store(store):
            rows.append(
                {
                    "canonical_id": f"profile:{key}",
                    "path": f"/memory/{_PROFILE_MEMORY_PATH}",
                    "target": f"/memory/{_PROFILE_MEMORY_PATH}",
                    "title": key.replace("_", " ").title(),
                    "preview": value,
                    "updated_at": str(store.get("profile", {}).get("updated_at") or ""),
                    "source": "memory",
                    "kind": "profile",
                    "topic_path": "memory/profile",
                    "entry_kind": "profile_field",
                    "field_key": key,
                }
            )

        for kind, path in (
            ("fact", f"/memory/{_FACTS_MEMORY_PATH}"),
            ("preference", f"/memory/{_PREFERENCES_MEMORY_PATH}"),
        ):
            for row in self._notes_by_kind(store, kind):
                preview = _truncate(_clean_text(str(row.get("content") or "")), 500)
                rows.append(
                    {
                        "canonical_id": f"{kind}:{int(row.get('id') or 0)}",
                        "path": path,
                        "target": path,
                        "title": _truncate(preview, 120) or kind.replace("_", " ").title(),
                        "preview": preview,
                        "updated_at": str(row.get("updated_at") or ""),
                        "source": _truncate(_clean_text(str(row.get("source") or "memory")), 64) or "memory",
                        "kind": kind,
                        "topic_path": f"memory/{kind}",
                        "entry_kind": "memory_note",
                        "field_key": "",
                        "tags": [],
                    }
                )

        for row in self._project_rows_from_store(store):
            rows.append(
                {
                    "canonical_id": f"project:{int(row.get('id') or 0)}",
                    "path": f"/memory/{_PROJECTS_MEMORY_PATH}",
                    "target": f"/memory/{_PROJECTS_MEMORY_PATH}",
                    "title": _truncate(_clean_text(str(row.get("name") or "")), 120),
                    "preview": _truncate(
                        _clean_text(
                            str(row.get("summary") or row.get("detail") or row.get("status") or "")
                        ),
                        500,
                    ),
                    "updated_at": str(row.get("updated_at") or ""),
                    "source": "memory",
                    "kind": "project",
                    "topic_path": "memory/projects",
                    "entry_kind": "project",
                    "field_key": "",
                    "tags": list(row.get("tags") or []),
                    "status": str(row.get("status") or "active"),
                }
            )

        for row in self._recent_context_rows_from_store(store):
            rows.append(
                {
                    "canonical_id": f"recent_context:{int(row.get('id') or 0)}",
                    "path": f"/memory/{_RECENT_CONTEXT_MEMORY_PATH}",
                    "target": f"/memory/{_RECENT_CONTEXT_MEMORY_PATH}",
                    "title": _truncate(_clean_text(str(row.get("title") or "Current focus")), 120) or "Current focus",
                    "preview": _truncate(_clean_text(str(row.get("content") or "")), 500),
                    "updated_at": str(row.get("updated_at") or ""),
                    "source": _truncate(_clean_text(str(row.get("source") or "memory")), 64) or "memory",
                    "kind": "recent_context",
                    "topic_path": "memory/recent_context",
                    "entry_kind": "recent_context",
                    "field_key": "",
                    "tags": [],
                }
            )

        for row in list(store.get("todos") or []):
            preview = _truncate(
                _clean_text(
                    f"{str(row.get('title') or '').strip()} {str(row.get('detail') or '').strip()}"
                ),
                500,
            )
            rows.append(
                {
                    "canonical_id": f"todo:{int(row.get('id') or 0)}",
                    "path": f"/memory/{_TODOS_MEMORY_PATH}",
                    "target": f"/memory/{_TODOS_MEMORY_PATH}",
                    "title": _truncate(_clean_text(str(row.get("title") or "")), 120),
                    "preview": preview,
                    "updated_at": str(row.get("updated_at") or ""),
                    "source": "memory",
                    "kind": "todo",
                    "topic_path": "memory/todos",
                    "entry_kind": "todo",
                    "field_key": "",
                    "tags": [],
                    "done": bool(row.get("done")),
                    "priority": self._normalize_todo_priority(str(row.get("priority") or "normal")),
                }
            )
        return rows

    def _cached_search_rows_for_store(self, store: dict[str, Any]) -> list[dict[str, Any]]:
        fingerprint = self._fingerprint_store(store)
        cached = self._cached_search_candidates(fingerprint)
        if cached is not None:
            return cached
        rows = self._search_candidate_rows_from_store(store)
        return self._remember_search_candidates(fingerprint, rows)

    def _search_kind_bias(self, row: dict[str, Any]) -> float:
        kind = str(row.get("kind") or "")
        if kind == "project":
            status = self._normalize_heading(str(row.get("status") or "active"))
            return 0.7 if self._is_active_project_status(status) else 0.2
        if kind == "todo":
            return 0.18 if not bool(row.get("done")) else -0.2
        if kind == "recent_context":
            return 0.3
        if kind == "profile":
            return 0.25
        if kind in {"fact", "preference"}:
            return 0.4 if kind == "fact" else 0.25
        if kind == "summary":
            return 0.05
        return 0.1

    def _search_recency_bonus(self, updated_at: Any) -> float:
        parsed = self._parse_updated_at(updated_at)
        if parsed is None:
            return 0.0
        age_seconds = max(0.0, (self._now() - parsed).total_seconds())
        age_days = age_seconds / 86400.0
        if age_days <= 1:
            return 0.5
        if age_days <= 7:
            return 0.35
        if age_days <= 30:
            return 0.2
        return 0.05

    def _score_memory_candidate(
        self,
        *,
        query: str,
        query_tokens: set[str],
        query_chars: set[str],
        row: dict[str, Any],
    ) -> float:
        title = _clean_text(str(row.get("title") or ""))
        preview = _clean_text(str(row.get("preview") or ""))
        kind = _clean_text(str(row.get("kind") or ""))
        topic_path = _clean_text(str(row.get("topic_path") or ""))
        field_key = _clean_text(str(row.get("field_key") or ""))
        tags = [
            _clean_text(str(tag or ""))
            for tag in list(row.get("tags") or [])
            if _clean_text(str(tag or ""))
        ]
        status = _clean_text(str(row.get("status") or ""))
        priority = _clean_text(str(row.get("priority") or ""))
        haystack = " ".join(part for part in [title, preview, kind, topic_path, field_key, status, priority, *tags] if part).lower()
        if not haystack:
            return 0.0
        score = 0.0
        title_lower = title.lower()
        preview_lower = preview.lower()
        if query and title_lower == query:
            score += 7.0
        elif query and query in title_lower:
            score += 4.5
        if query and query in preview_lower:
            score += 2.6
        elif query and query in haystack:
            score += 1.4

        title_tokens = set(self._tokenize_search_text(title_lower))
        preview_tokens = set(self._tokenize_search_text(preview_lower))
        candidate_tokens = set(self._tokenize_search_text(haystack))
        if query_tokens and candidate_tokens:
            title_overlap = len(query_tokens & title_tokens)
            preview_overlap = len(query_tokens & preview_tokens)
            total_overlap = len(query_tokens & candidate_tokens)
            if title_overlap > 0:
                score += 2.5 + (title_overlap / max(1, len(query_tokens)))
            if preview_overlap > 0:
                score += 1.5 + (preview_overlap / max(1, len(query_tokens)))
            if total_overlap == len(query_tokens):
                score += 1.0
        candidate_chars = {char for char in haystack.replace(" ", "") if char}
        if query_chars and candidate_chars:
            shared_chars = len(query_chars & candidate_chars)
            if shared_chars > 0:
                score += min(1.5, shared_chars / max(1, min(12, len(query_chars))))
        if query and title_lower.startswith(query):
            score += 0.6
        if field_key:
            field_tokens = set(self._tokenize_search_text(field_key.lower()))
            if query_tokens and field_tokens and query_tokens & field_tokens:
                score += 1.2
        if tags:
            tag_tokens = set(self._tokenize_search_text(" ".join(tags).lower()))
            if query_tokens and tag_tokens and query_tokens & tag_tokens:
                score += 1.4
        score += self._search_kind_bias(row)
        score += self._search_recency_bonus(row.get("updated_at"))
        return round(score, 4)

    def _search_rows_in_store(
        self,
        *,
        store: dict[str, Any],
        query: str,
        top_k: int = 6,
        kinds: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        clean_query = _truncate(_clean_text(query), 240).lower()
        if not clean_query:
            return []
        candidates = self._cached_search_rows_for_store(store)
        query_tokens = set(self._tokenize_search_text(clean_query))
        query_chars = {char for char in clean_query.replace(" ", "") if char}

        scored: list[dict[str, Any]] = []
        for row in candidates:
            row_kind = str(row.get("kind") or "")
            if kinds and row_kind not in kinds:
                continue
            score = self._score_memory_candidate(
                query=clean_query,
                query_tokens=query_tokens,
                query_chars=query_chars,
                row=row,
            )
            if score <= 0:
                continue
            scored.append({**row, "score": score})
        scored.sort(
            key=lambda row: (
                float(row.get("score") or 0.0),
                str(row.get("updated_at") or ""),
                str(row.get("canonical_id") or ""),
            ),
            reverse=True,
        )
        return scored[: max(1, min(20, int(top_k or 6)))]

    def _render_query_relevant_memory_section(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return ""
        lines = ["## Query-Relevant Memory"]
        seen: set[str] = set()
        for row in rows[:4]:
            kind = str(row.get("kind") or "memory").replace("_", " ")
            title = _truncate(_clean_text(str(row.get("title") or "")), 120)
            preview = _truncate(_clean_text(str(row.get("preview") or "")), 220)
            path = str(row.get("path") or "").strip()
            bullet = f"- [{kind}]"
            if title:
                bullet += f" {title}"
            if preview and preview != title:
                bullet += f": {preview}"
            if path and path not in seen:
                bullet += f" ({path})"
                seen.add(path)
            lines.append(bullet)
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
        fallback_text = str(fallback_agents_text or "").strip()
        clean_query_hint = _truncate(_clean_text(query_hint), 240)
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        if not self._store_has_meaningful_content(store) and fallback_text:
            store = self._store_from_agents_md_text(fallback_text)
        store = self._normalize_store(store)
        cache_key = (
            int(user_id),
            str(workspace or "default"),
            self._fingerprint_store(store),
            self._fingerprint_text(f"{fallback_text}|{clean_query_hint}"),
        )
        cached = self._cached_memory_bundle(cache_key)
        if cached is not None:
            return cached
        if not self._store_has_meaningful_content(store):
            if fallback_text:
                return self._remember_memory_bundle(cache_key, {
                    "prompt_path": "/memory/AGENTS.md",
                    "prompt_text": fallback_text,
                    "files": {"/memory/AGENTS.md": fallback_text},
                    "memory_paths": ["/memory/AGENTS.md"],
                    "index": {},
                })
            return self._remember_memory_bundle(cache_key, {
                "prompt_path": "/memory/AGENTS.md",
                "prompt_text": "",
                "files": {},
                "memory_paths": [],
                "index": {},
            })

        runtime_text, projection_files, index_payload = self._projection_files_from_store(store)
        focused_hits = self._search_rows_in_store(
            store=store,
            query=clean_query_hint,
            top_k=6,
        ) if clean_query_hint else []
        if focused_hits:
            focused_section = self._render_query_relevant_memory_section(focused_hits)
            if focused_section:
                runtime_text = f"{str(runtime_text or '').rstrip()}\n\n{focused_section}".strip() + "\n"
                projection_files["AGENTS.md"] = runtime_text
        files: dict[str, str] = {
            f"/memory/{path}": str(content or "").strip()
            for path, content in projection_files.items()
            if str(content or "").strip()
        }
        files[f"/memory/{_INDEX_MEMORY_PATH}"] = json.dumps(
            index_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        extra_memory_paths: list[str] = []
        for row in focused_hits:
            path = str(row.get("path") or "").strip()
            if not path or path == "/memory/AGENTS.md" or path == f"/memory/{_INDEX_MEMORY_PATH}":
                continue
            if path in extra_memory_paths:
                continue
            extra_memory_paths.append(path)
            if len(extra_memory_paths) >= 2:
                break
        return self._remember_memory_bundle(cache_key, {
            "prompt_path": "/memory/AGENTS.md",
            "prompt_text": str(runtime_text or "").strip(),
            "files": files,
            "memory_paths": (
                ["/memory/AGENTS.md", *extra_memory_paths]
                if str(runtime_text or "").strip()
                else extra_memory_paths
            ),
            "index": index_payload,
        })

    def search_memory(
        self,
        *,
        user_id: int,
        workspace: str,
        query: str,
        top_k: int = 6,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        clean_query = _truncate(_clean_text(query), 240).lower()
        if not clean_query:
            return []
        normalized_kinds = {
            kind
            for kind in (
                self._normalize_search_kind(item)
                for item in list(kinds or [])
            )
            if kind
        }
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        return self._search_rows_in_store(
            store=store,
            query=clean_query,
            top_k=top_k,
            kinds=normalized_kinds,
        )

    def upsert_profile_fields(
        self,
        *,
        user_id: int,
        workspace: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        profile = self._normalize_profile_payload(store.get("profile"))
        merged = dict(profile.get("fields") or {})
        for raw_key, raw_value in dict(fields or {}).items():
            key = _truncate(_clean_text(str(raw_key or "")), 48).lower().replace("-", "_").replace(" ", "_")
            value = _truncate(_clean_text(str(raw_value or "")), 240)
            if key and value:
                merged[key] = self._prefer_richer_text(str(merged.get(key) or ""), value, max_chars=240)
        store["profile"] = {
            "fields": merged,
            "updated_at": self._now_iso(),
        }
        normalized = self._persist_memory_store(user_id=user_id, workspace=workspace, store=store)
        return dict(normalized.get("profile") or {})

    def upsert_project(
        self,
        *,
        user_id: int,
        workspace: str,
        project: dict[str, Any],
    ) -> dict[str, Any] | None:
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        rows = list(store.get("projects") or [])
        candidate = self._normalize_project_item(project, fallback_id=self._next_numeric_id(rows))
        if candidate is None:
            return None
        incoming_id = int(candidate.get("id") or 0)
        incoming_name = self._normalize_identity(str(candidate.get("name") or ""))
        updated = False
        for index, row in enumerate(rows):
            row_id = int(row.get("id") or 0)
            row_name = self._normalize_identity(str(row.get("name") or ""))
            if (incoming_id > 0 and row_id == incoming_id) or (incoming_name and row_name == incoming_name):
                candidate["id"] = row_id or incoming_id or self._next_numeric_id(rows)
                rows[index] = self._merge_project_items(dict(row), candidate)
                updated = True
                break
        if not updated:
            candidate["id"] = self._next_numeric_id(rows)
            rows.append(candidate)
        store["projects"] = rows
        normalized = self._persist_memory_store(user_id=user_id, workspace=workspace, store=store)
        for row in list(normalized.get("projects") or []):
            if int(row.get("id") or 0) == int(candidate.get("id") or 0):
                return dict(row)
        return candidate

    def get_agents_memory_text(
        self,
        db: Session,
        user_id: int,
        *,
        workspace: str = "default",
    ) -> str:
        _ = db
        store = self._read_memory_store(user_id=user_id, workspace=workspace or "default")
        cached_projection = self._read_agents_md_text(user_id=user_id, workspace=workspace or "default")
        if store is not None and cached_projection.strip():
            return cached_projection.strip()
        bundle = self.get_memory_bundle(
            user_id=user_id,
            workspace=workspace or "default",
            fallback_agents_text=cached_projection,
        )
        if str(bundle.get("prompt_text") or "").strip():
            return str(bundle.get("prompt_text") or "").strip()
        return ""

    def append_fact_to_memory(self, *, user_id: int, workspace: str, content: str) -> None:
        clean = _truncate(_clean_text(content), 280)
        if not clean:
            return
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        notes = list(store.get("notes") or [])
        target_key = self._normalize_identity(clean)
        updated = False
        for row in notes:
            if self._normalize_note_kind(str(row.get("kind") or "")) != "fact":
                continue
            if self._normalize_identity(str(row.get("content") or "")) != target_key:
                continue
            row["content"] = self._prefer_richer_text(str(row.get("content") or ""), clean, max_chars=280)
            row["updated_at"] = self._now_iso()
            updated = True
            break
        if not updated:
            notes.append(
                {
                    "id": self._next_numeric_id(notes),
                    "kind": "fact",
                    "content": clean,
                    "source": "memory",
                    "updated_at": self._now_iso(),
                }
            )
        store["notes"] = notes
        self._persist_memory_store(user_id=user_id, workspace=workspace, store=store)

    def append_preference_to_memory(self, *, user_id: int, workspace: str, content: str) -> None:
        clean = _truncate(_clean_text(content), 280)
        if not clean:
            return
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        notes = list(store.get("notes") or [])
        target_key = self._normalize_identity(clean)
        updated = False
        for row in notes:
            if self._normalize_note_kind(str(row.get("kind") or "")) != "preference":
                continue
            if self._normalize_identity(str(row.get("content") or "")) != target_key:
                continue
            row["content"] = self._prefer_richer_text(str(row.get("content") or ""), clean, max_chars=280)
            row["updated_at"] = self._now_iso()
            updated = True
            break
        if not updated:
            notes.append(
                {
                    "id": self._next_numeric_id(notes),
                    "kind": "preference",
                    "content": clean,
                    "source": "memory",
                    "updated_at": self._now_iso(),
                }
            )
        store["notes"] = notes
        self._persist_memory_store(user_id=user_id, workspace=workspace, store=store)

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
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        todos = list(store.get("todos") or [])
        target_key = self._normalize_identity(clean_title)
        updated = False
        for row in todos:
            if self._normalize_identity(str(row.get("title") or "")) != target_key:
                continue
            row["done"] = False
            if self._normalize_todo_priority(priority) == "high":
                row["priority"] = "high"
            row["updated_at"] = self._now_iso()
            updated = True
            break
        if not updated:
            todos.append(
                {
                    "id": self._next_numeric_id(todos),
                    "title": clean_title,
                    "detail": "",
                    "done": False,
                    "priority": self._normalize_todo_priority(priority),
                    "due_at": "",
                    "updated_at": self._now_iso(),
                }
            )
        store["todos"] = todos
        self._persist_memory_store(user_id=user_id, workspace=workspace, store=store)

    def get_summary(self, db: Session, user_id: int, *, workspace: str = "default") -> str:
        _ = db
        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        return _truncate(_clean_text(str(store.get("summary", {}).get("content") or "")), 1000)

    def list_notes(
        self,
        db: Session,
        user_id: int,
        limit: int = 12,
        workspace: str = "default",
    ) -> list[MemoryNote]:
        _ = db
        return self._notes_from_store(user_id=user_id, workspace=workspace, limit=limit)

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
        _ = db
        clean = _truncate(_clean_text(content), 500)
        if not clean:
            raise ValueError("memory note content is empty")

        store, _ = self._load_memory_store(user_id=user_id, workspace=workspace)
        notes = list(store.get("notes") or [])
        normalized_kind = self._normalize_note_kind(kind)
        normalized_source = _truncate(_clean_text(str(source or "memory")), 64) or "memory"
        target_key = (normalized_kind, self._normalize_identity(clean))
        row: dict[str, Any] | None = None
        for existing in notes:
            existing_key = (
                self._normalize_note_kind(str(existing.get("kind") or "note")),
                self._normalize_identity(str(existing.get("content") or "")),
            )
            if existing_key != target_key:
                continue
            existing["content"] = self._prefer_richer_text(str(existing.get("content") or ""), clean, max_chars=500)
            existing["source"] = normalized_source
            existing["updated_at"] = self._now_iso()
            row = dict(existing)
            break
        if row is None:
            row = {
                "id": self._next_numeric_id(notes),
                "kind": normalized_kind,
                "content": clean,
                "source": normalized_source,
                "updated_at": self._now_iso(),
            }
            notes.append(row)
        store["notes"] = notes
        self._persist_memory_store(user_id=user_id, workspace=workspace, store=store)
        return self._memory_note_from_store(user_id=user_id, row=row)

    def list_todos(
        self,
        db: Session,
        user_id: int,
        *,
        include_done: bool = True,
        limit: int = 100,
        workspace: str = "default",
    ) -> list[dict[str, Any]]:
        _ = db
        return self._todos_from_store(
            user_id=user_id,
            workspace=workspace,
            include_done=include_done,
            limit=limit,
        )

    def build_focus_items(self, db: Session, user_id: int, *, query: str = "", limit: int = 8) -> list[FocusItem]:
        _ = db, user_id, query, limit
        return []

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
                title="Recent conversation summary",
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
            bucket = (
                preferences
                if kind in {"preference", "profile"}
                else in_progress
                if kind in {"in_progress", "todo"}
                else facts
            )
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
                detail=(
                    f"{_SOURCE_LABELS.get(str(getattr(item, 'source', '') or ''), str(getattr(item, 'source', '') or 'message'))}"
                    f" / {str(getattr(item, 'sender', '') or '')}"
                ),
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
                title="Pinned contact ordering preference",
                detail="Prioritize: " + ", ".join([name for name in pinned_names if name]),
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


_agent_memory_service: AgentMemoryService | None = None


def get_agent_memory_service() -> AgentMemoryService:
    global _agent_memory_service
    if _agent_memory_service is None:
        _agent_memory_service = AgentMemoryService()
    return _agent_memory_service
