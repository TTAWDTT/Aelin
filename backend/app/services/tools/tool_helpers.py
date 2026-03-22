from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:  # noqa: BLE001
        out = default
    return max(low, min(high, out))


def _result_ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, **fields}


def _result_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": str(message or "unknown_error")[:180]}


def _result_items(items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return _result_ok(items=items, total=len(items), **extra)


__all__ = [
    "_safe_int",
    "_result_ok",
    "_result_error",
    "_result_items",
]
