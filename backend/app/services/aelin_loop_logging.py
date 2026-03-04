from __future__ import annotations


def safe_preview(text: str, *, limit: int = 180) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}...(len={len(compact)})"

