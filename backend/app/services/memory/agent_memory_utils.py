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


def _iso_or_empty(value: datetime | None) -> str:
    if value is None:
        return ""
    try:
        return value.isoformat()
    except Exception:
        return ""

