from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.aelin_attachment_service import (
    AelinAttachmentService,
    get_aelin_attachment_service,
)
from app.services.aelin_utils import normalize_positive_ints
from app.services.device_center import (
    capture_device_screen as device_capture_screen,
    DeviceScreenCaptureError,
)
from app.services.google_workspace_cli import get_google_workspace_cli_service
from app.services.web_search import WebSearchService


def _normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


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


class AelinToolHub:
    """
    Thin context binder for the current DB/user/workspace/services.

    DeepAgents now registers tools explicitly in `deepagents_graph.py`, so this
    object only carries runtime context and a few shared helpers used by those
    tools.
    """

    def __init__(
        self,
        *,
        db: Session,
        user_id: int,
        workspace: str,
        web_search_service: WebSearchService | None = None,
        attachment_service: AelinAttachmentService | None = None,
        available_attachment_ids: list[int] | None = None,
    ) -> None:
        self.db = db
        self.user_id = int(user_id)
        self.workspace = _normalize_workspace(workspace)
        self._web_search = web_search_service or WebSearchService()
        self._attachments = attachment_service or get_aelin_attachment_service()
        self._available_attachment_ids = normalize_positive_ints(
            available_attachment_ids, cap=20
        )


__all__ = [
    "AelinToolHub",
    "_safe_int",
    "_result_ok",
    "_result_error",
    "_result_items",
    "DeviceScreenCaptureError",
    "device_capture_screen",
    "get_google_workspace_cli_service",
]
