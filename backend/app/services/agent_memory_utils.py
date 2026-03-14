from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


def _truncate(text: str, limit: int) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_terms(query: str) -> list[str]:
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{3,}", (query or "").lower())
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= 10:
            break
    return out


def _note_candidates_from_user_text(text: str) -> list[str]:
    src = _clean_text(text)
    if not src:
        return []

    patterns = [
        r"(?:请)?记住[:：]?\s*(.+)$",
        r"帮我记(?:一下|住)?[:：]?\s*(.+)$",
        r"remember(?: that)?[:：]?\s*(.+)$",
        r"我最近在关注[:：]?\s*(.+)$",
        r"我最近在看[:：]?\s*(.+)$",
    ]
    out: list[str] = []
    for p in patterns:
        m = re.search(p, src, flags=re.IGNORECASE)
        if not m:
            continue
        note = _truncate(_clean_text(m.group(1)), 280)
        if note:
            out.append(note)

    if not out:
        m = re.search(r"我(关注|喜欢|不喜欢)\s*(.+)$", src)
        if m:
            note = _truncate(f"{m.group(1)}: {_clean_text(m.group(2))}", 280)
            if note:
                out.append(note)
    return out


def _parse_json_or_none(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _iso_or_empty(value: datetime | None) -> str:
    if value is None:
        return ""
    try:
        return value.isoformat()
    except Exception:
        return ""


