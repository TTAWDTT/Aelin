from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _slug(text: str, *, fallback: str = "item", max_len: int = 64) -> str:
    raw = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", (text or "").strip()).strip("-")
    if not raw:
        return fallback
    return raw[:max_len]


def _normalize_workspace(value: str) -> str:
    clean = " ".join((value or "").strip().split())
    return clean[:64] if clean else "default"


def _safe_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        return "{}"


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass(slots=True)
class FileMemoryHit:
    path: str
    title: str
    preview: str
    score: float
    updated_at: str
    canonical_id: str
    target: str
    source: str
    kind: str
    topic_path: str = ""
    entry_kind: str = ""


@dataclass(slots=True)
class DiaryTreeNode:
    name: str
    path: str
    kind: str
    title: str = ""
    preview: str = ""
    updated_at: str = ""
    source: str = ""
    topic_path: str = ""
    entry_kind: str = ""
    children: list["DiaryTreeNode"] = field(default_factory=list)
