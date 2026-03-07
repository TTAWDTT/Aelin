from __future__ import annotations

from typing import Any


def normalize_positive_ints(values: list[Any] | tuple[Any, ...] | None, *, cap: int = 20) -> list[int]:
    out: list[int] = []
    for item in list(values or []):
        try:
            value = int(item)
        except Exception:
            continue
        if value <= 0:
            continue
        out.append(value)
    slice_cap = int(cap)
    return sorted(set(out))[: max(1, slice_cap)]


def escape_sql_like(value: str, *, escape: str = "\\") -> str:
    text = str(value or "")
    return text.replace(escape, escape + escape).replace("%", escape + "%").replace("_", escape + "_")
