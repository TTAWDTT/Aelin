from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Iterable

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.models import AgentConversationMemory, AgentMemoryNote, Contact, Message
from app.services.agent_memory_utils import (
    _clean_text,
    _extract_terms,
    _iso_or_empty,
    _note_candidates_from_user_text,
    _parse_json_or_none,
    _truncate,
)
from app.services.openviking_bridge import file_memory_bridge

_SOCIAL_SOURCES = {"x", "douyin", "bilibili", "xiaohongshu", "weibo", "rss"}
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


class AgentMemoryService:
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

    def _notes_from_agents_md(
        self,
        *,
        user_id: int,
        workspace: str,
        limit: int,
    ) -> list[AgentMemoryNote]:
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

        out: list[AgentMemoryNote] = []
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

            # 为了与 DB-backed notes 兼容，提供稳定的 id 与 updated_at。
            row = AgentMemoryNote(
                id=idx + 1,
                user_id=user_id,
                kind=kind,
                content=content,
                source="agents_md",
            )
            row.updated_at = datetime.now(timezone.utc)
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

    def get_summary(self, db: Session, user_id: int, *, workspace: str = "default") -> str:
        """
        Return the short conversation summary for a user.

        When available, this prefers the DeepAgents-style AGENTS.md memory file
        stored via FileMemoryBridge; otherwise it falls back to the legacy
        AgentConversationMemory.summary field in the database.
        """
        agents_md = self._read_agents_md_text(user_id=user_id, workspace=workspace)
        if agents_md:
            text = _clean_text(agents_md)
            # Prefer the "## 会话摘要" section if present.
            summary = ""
            marker = "## 会话摘要"
            idx = text.find(marker)
            if idx >= 0:
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
            if summary:
                return summary.strip()
        # Fallback: legacy DB summary.
        row = db.get(AgentConversationMemory, user_id)
        if row is None:
            return ""
        return (row.summary or "").strip()

    def set_summary(self, db: Session, user_id: int, summary: str) -> None:
        row = db.get(AgentConversationMemory, user_id)
        clean_summary = _truncate(_clean_text(summary), 1800)
        if row is None:
            row = AgentConversationMemory(user_id=user_id, summary=clean_summary)
            db.add(row)
        else:
            row.summary = clean_summary
            db.add(row)

    def list_notes(
        self,
        db: Session,
        user_id: int,
        limit: int = 12,
        workspace: str = "default",
    ) -> list[AgentMemoryNote]:
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

    def add_note(self, db: Session, user_id: int, content: str, *, kind: str = "note", source: str | None = None) -> AgentMemoryNote:
        clean = _truncate(_clean_text(content), 500)
        if not clean:
            raise ValueError("memory note content is empty")
        dup_stmt: Select[tuple[AgentMemoryNote]] = (
            select(AgentMemoryNote)
            .where(AgentMemoryNote.user_id == user_id, AgentMemoryNote.content == clean)
            .order_by(AgentMemoryNote.updated_at.desc(), AgentMemoryNote.id.desc())
            .limit(1)
        )
        existing = db.scalar(dup_stmt)
        if existing is not None:
            existing.kind = kind
            existing.source = source
            db.add(existing)
            return existing

        row = AgentMemoryNote(
            user_id=user_id,
            kind=_truncate(_clean_text(kind), 32) or "note",
            content=clean,
            source=_truncate(_clean_text(source or ""), 64) or None,
        )
        db.add(row)
        return row

    def delete_note(self, db: Session, user_id: int, note_id: int) -> bool:
        stmt = select(AgentMemoryNote).where(AgentMemoryNote.user_id == user_id, AgentMemoryNote.id == note_id)
        row = db.scalar(stmt)
        if row is None:
            return False
        db.delete(row)
        return True

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
        n = max(1, min(20, int(limit or 8)))
        stmt = (
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(200)
        )
        rows = db.scalars(stmt).all()
        if not rows:
            return []

        contact_ids = {int(m.contact_id) for m in rows if m.contact_id is not None}
        avatar_by_contact_id: dict[int, str] = {}
        if contact_ids:
            avatar_rows = db.execute(
                select(Contact.id, Contact.avatar_url).where(
                    Contact.user_id == user_id,
                    Contact.id.in_(contact_ids),
                )
            ).all()
            for cid, avatar in avatar_rows:
                if avatar:
                    avatar_by_contact_id[int(cid)] = str(avatar)

        terms = _extract_terms(query)
        contact_hits = Counter(m.contact_id for m in rows if m.contact_id is not None)
        now = datetime.now(timezone.utc)
        scored: list[FocusItem] = []

        for m in rows:
            title = _clean_text(m.subject or "") or _clean_text(m.body_preview or "")
            if not title:
                continue

            received = m.received_at
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (now - received).total_seconds() / 3600.0)
            recency_score = max(0.0, 8.0 - age_hours / 12.0)

            source = (m.source or "").lower()
            source_bonus = 2.0 if source in _SOCIAL_SOURCES else 0.4
            contact_bonus = min(2.0, contact_hits.get(m.contact_id, 0) * 0.2)
            unread_bonus = 0.7 if not m.is_read else 0.0

            text_blob = f"{m.sender} {m.subject} {m.body_preview}".lower()
            keyword_bonus = 0.0
            if terms:
                for t in terms:
                    if t in text_blob:
                        keyword_bonus += 1.5
                keyword_bonus = min(6.0, keyword_bonus)

            score = recency_score + source_bonus + contact_bonus + unread_bonus + keyword_bonus
            scored.append(
                FocusItem(
                    message_id=m.id,
                    source=source or "unknown",
                    sender=_truncate(_clean_text(m.sender or ""), 60),
                    sender_avatar_url=avatar_by_contact_id.get(int(m.contact_id or 0)),
                    title=_truncate(title, 140),
                    received_at=received.strftime("%Y-%m-%d %H:%M"),
                    score=score,
                )
            )

        scored.sort(key=lambda x: (x.score, x.received_at), reverse=True)
        return scored[:n]

    # Advanced inbox search for the legacy `/agent` surface has been removed.
    # New search scenarios should be implemented as explicit tools instead of
    # embedding DB-specific query logic inside the memory service.

    def build_memory_layers_from_items(
        self,
        *,
        summary: str,
        notes: list[AgentMemoryNote] | None,
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


    def build_system_memory_prompt(self, db: Session, user_id: int, *, query: str = "") -> str:
        """
        Build a single concise markdown string representing the user's memory.

        This is designed to be mounted as a virtual AGENTS.md-style file for
        DeepAgents, and to serve as the `memory_summary` passed through the
        rest of the Aelin pipeline.

        When an AGENTS.md file already exists for the default workspace, it is
        treated as the primary truth and used directly, with an optional
        “当前问题” section appended for the caller's query. If no AGENTS.md is
        available, an empty skeleton document is created instead of falling
        back to legacy DB-backed summary/notes/todos, so that the DeepAgents
        runtime can remain file-first and DB-independent for memory.
        """
        # Prefer an existing AGENTS.md snapshot for the default workspace.
        agents_md = self._read_agents_md_text(user_id=user_id, workspace="default")
        query_text = _clean_text(query or "")
        if agents_md:
            base = str(agents_md).strip()
            if not base:
                return ""
            if query_text:
                extra = "## 当前问题\n" + _truncate(query_text, 240)
                sep = "\n\n" if not base.endswith("\n") else "\n"
                return base + sep + extra
            return base

        # Fallback: synthesize a minimal, empty AGENTS.md skeleton. We do not
        # attempt to reconstruct historical memory from the DB here, so that
        # the runtime only depends on file-backed memory.
        parts: list[str] = []
        if query_text:
            parts.append("## 当前问题\n" + _truncate(query_text, 240))
        body = "\n\n".join(parts).strip()
        if not body:
            return "# Aelin Session Memory\n"
        return "# Aelin Session Memory\n\n" + body

    def update_after_turn(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - legacy shim
        """
        Legacy no-op shim for older callers.

        DeepAgents 版本的 Aelin 不再通过这个入口写入 DB 记忆；所有长期
        记忆写入都应通过 `memory` 工具直接编辑 `/memory/AGENTS.md`。
        该方法仅为兼容旧测试/调用点而保留，不做任何实质操作。
        """
        return None
