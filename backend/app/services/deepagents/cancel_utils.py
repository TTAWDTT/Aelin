from __future__ import annotations

from typing import Any


def is_cancelled(cancel_token: Any | None) -> bool:
    """
    Small helper to check whether an optional cancel token has been marked
    as cancelled. This keeps the semantics consistent across Aelin core,
    DeepAgents graph, and the DeepAgents loop bridge.
    """
    return bool(getattr(cancel_token, "cancelled", False))

