from __future__ import annotations

import re
from typing import Any

from app.services.agent_memory import AgentMemoryService, MemoryNote


def tool_context_get(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Read summary + focus items + todos from AGENTS.md-backed memory.

    This is the implementation extracted from AelinToolHub._tool_context_get
    so that the hub itself只负责调度，逻辑集中在 tools_context 模块中。
    """
    from app.services.aelin_tools import _result_ok, _safe_int  # local import to avoid cycles

    query = str(args.get("query") or "").strip()[:400]
    limit = _safe_int(args.get("max_items"), 8, low=1, high=20)

    summary = str(
        hub._memory.get_summary(hub.db, hub.user_id, workspace=hub.workspace)
        or ""
    )
    todos = hub._memory.list_todos(
        hub.db,
        hub.user_id,
        include_done=False,
        limit=limit,
        workspace=hub.workspace,
    )
    return _result_ok(
        workspace=hub.workspace,
        summary=summary,
        focus_items=[],
        todos=todos,
    )


def tool_profile(hub: "AelinToolHub", args: dict[str, Any]) -> dict[str, Any]:
    """
    Read or append user profile/preference notes, backed by AGENTS.md only.

    行为等价于原来的 AelinToolHub._tool_profile，但不再触碰 DB 表，所有数据
    均通过 AgentMemoryService 的文件记忆接口投影。
    """
    from app.services.aelin_tools import _result_error, _result_items, _safe_int  # local import

    action = str(args.get("action") or "get").strip().lower()
    if action == "append_note":
        note = re.sub(r"\s+", " ", str(args.get("note") or "")).strip()[:500]
        if not note:
            return _result_error("empty note")
        row = hub._memory.add_note(
            hub.db,
            hub.user_id,
            note,
            kind="profile",
            source=f"profile:{hub.workspace}",
            workspace=hub.workspace,
        )
        return _result_ok(
            note_id=int(getattr(row, "id", 0) or 0),
            note=note,
        )

    max_items = _safe_int(args.get("max_items"), 12, low=1, high=24)
    raw_notes = hub._memory.list_notes(
        hub.db,
        hub.user_id,
        limit=max_items,
        workspace=hub.workspace,
    )
    notes: list[MemoryNote] = []
    for row in raw_notes:
        kind_norm = str(getattr(row, "kind", "") or "").lower()
        if kind_norm in {
            "profile",
            "identity",
            "preference",
            "user_profile",
            "user_note",
            "manual_note",
        }:
            notes.append(row)
        if len(notes) >= max_items:
            break

    items = [
        {
            "id": int(it.id),
            "kind": str(it.kind or ""),
            "content": str(it.content or "")[:220],
            "source": str(it.source or ""),
            "updated_at": (
                it.updated_at.isoformat()
                if getattr(it, "updated_at", None)
                else ""
            ),
        }
        for it in notes
    ]
    return _result_items(items)
