from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import (
    AelinMemoryLayerItem,
    AelinMemoryLayers,
    AelinTodoItem,
    AgentMemoryNoteOut,
)
from app.services.agent_memory import AgentMemoryService


def build_context_bundle(
    db: Session,
    user_id: int,
    *,
    workspace: str,
    query: str,
    memory_service: AgentMemoryService,
) -> dict:
    workspace_norm = workspace
    summary = memory_service.get_summary(db, user_id, workspace=workspace_norm)
    note_rows = memory_service.list_notes(db, user_id, limit=24)
    notes: list[AgentMemoryNoteOut] = []
    for row in note_rows:
        src = (row.source or "").strip().lower()
        if src == "todo" or src.startswith("card_layout"):
            continue
        notes.append(
            AgentMemoryNoteOut(
                id=row.id,
                kind=row.kind,
                content=row.content,
                source=row.source,
                updated_at=row.updated_at.isoformat() if row.updated_at else "",
            )
        )
        if len(notes) >= 12:
            break

    todos_raw = memory_service.list_todos(db, user_id, include_done=False, limit=10)
    todos: list[AelinTodoItem] = []
    for row in todos_raw:
        try:
            todos.append(AelinTodoItem(**row))
        except Exception:
            continue
    memory_layers_raw = memory_service.build_memory_layers_from_items(
        summary=summary,
        notes=note_rows,
        focus_items=None,
        todos=todos_raw,
        layout_cards=None,
        workspace=workspace_norm,
        query=query,
    )
    memory_layers = AelinMemoryLayers(
        facts=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("facts") or [])],
        preferences=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("preferences") or [])],
        in_progress=[AelinMemoryLayerItem(**item) for item in (memory_layers_raw.get("in_progress") or [])],
        generated_at=datetime.now(timezone.utc),
    )

    return {
        "workspace": workspace_norm,
        "summary": str(summary or ""),
        "notes": notes,
        "notes_count": len(notes),
        "todos": todos,
        "memory_layers": memory_layers,
    }


def build_cached_base_context_bundle(
    db: Session,
    *,
    user_id: int,
    workspace: str,
    memory_service: AgentMemoryService,
    ttl_seconds: float,
    max_entries: int,
    cache: dict[tuple[int, str], tuple[float, dict[str, Any]]],
    lock,
) -> dict[str, Any]:
    workspace_norm = workspace
    if ttl_seconds <= 0 or max_entries <= 0:
        return build_context_bundle(db, user_id, workspace=workspace_norm, query="", memory_service=memory_service)

    cache_key = (int(user_id), workspace_norm)
    now = time.monotonic()
    with lock:
        hit = cache.get(cache_key)
        if hit is not None:
            ts, cached_bundle = hit
            if (now - float(ts)) <= ttl_seconds and isinstance(cached_bundle, dict):
                return cached_bundle
            cache.pop(cache_key, None)

    bundle = build_context_bundle(db, user_id, workspace=workspace_norm, query="", memory_service=memory_service)
    with lock:
        cache[cache_key] = (now, bundle)
        _prune_ttl_cache(cache, max_entries=max_entries)
    return bundle


def _prune_ttl_cache(
    cache: dict[Any, tuple[float, Any]],
    *,
    max_entries: int,
) -> None:
    if max_entries <= 0:
        cache.clear()
        return
    overflow = len(cache) - max_entries
    if overflow <= 0:
        return
    for key, _ in sorted(cache.items(), key=lambda item: float(item[1][0]))[:overflow]:
        cache.pop(key, None)
