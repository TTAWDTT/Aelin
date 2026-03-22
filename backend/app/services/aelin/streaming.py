from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n"
