from __future__ import annotations


def truncate_text(text: str, *, limit: int = 180, mask_data_image_url: bool = False) -> str:
    compact = " ".join(str(text or "").split())
    if mask_data_image_url and compact.lower().startswith("data:image/"):
        return f"<data_url len={len(text)}>"
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}...(len={len(compact)})"


def safe_preview(text: str, *, limit: int = 180) -> str:
    return truncate_text(text, limit=limit)
