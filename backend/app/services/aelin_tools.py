from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services.aelin_attachment_service import (
    AelinAttachmentService,
    get_aelin_attachment_service,
)
from app.services.aelin_utils import normalize_positive_ints
from app.services.device_center import (
    activate_desktop_module,
    capture_device_screen as device_capture_screen,
    DesktopPluginActionError,
    DeviceScreenCaptureError,
    device_status_snapshot,
    open_desktop_external_url,
)
from app.services.google_workspace_cli import get_google_workspace_cli_service
from app.services.llm import LLMService
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


def _is_http_url(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


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
        llm_service: LLMService | None = None,
    ) -> None:
        self.db = db
        self.user_id = int(user_id)
        self.workspace = _normalize_workspace(workspace)
        self._web_search = web_search_service or WebSearchService()
        self._attachments = attachment_service or get_aelin_attachment_service()
        self._available_attachment_ids = normalize_positive_ints(
            available_attachment_ids, cap=20
        )
        # Optional reference to the current LLM service so tools can delegate
        # sub-tasks in the future if needed.
        self._llm_service = llm_service

    # ---- device helpers (used by tools_device) -----------------------------------

    def _tool_device_status(self, args: dict[str, Any]) -> dict[str, Any]:
        _ = args
        snapshot = device_status_snapshot()
        return _result_ok(
            platform=str(snapshot.get("platform") or "unknown"),
            capabilities=dict(snapshot.get("capabilities") or {}),
            notes=list(snapshot.get("notes") or []),
            desktop_plugin_reachable=bool(snapshot.get("desktop_plugin_reachable")),
            desktop_plugin_configured=bool(snapshot.get("desktop_plugin_configured")),
            summary=(
                f"platform={str(snapshot.get('platform') or 'unknown')}; "
                f"plugin_reachable={1 if bool(snapshot.get('desktop_plugin_reachable')) else 0}"
            ),
        )

    def _tool_desktop_open_url(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url") or "").strip()
        if not url:
            return _result_error("missing url")
        if not _is_http_url(url):
            return _result_error("invalid_url_scheme")
        try:
            result = open_desktop_external_url(url)
        except DesktopPluginActionError as exc:
            return _result_error(f"desktop_open_url_failed:{exc.detail}")
        except Exception as exc:  # noqa: BLE001
            return _result_error(f"desktop_open_url_failed:{str(exc)[:160]}")
        return _result_ok(
            url=str(result.get("url") or url),
            opened=bool(result.get("opened")),
            detail=str(result.get("detail") or ""),
            summary=f"已尝试打开链接: {str(result.get('url') or url)[:220]}",
        )

    def _tool_desktop_open_aelin(self, args: dict[str, Any]) -> dict[str, Any]:
        route = str(args.get("route") or "/").strip() or "/"
        try:
            result = activate_desktop_module(route)
        except DesktopPluginActionError as exc:
            return _result_error(f"desktop_open_aelin_failed:{exc.detail}")
        except Exception as exc:  # noqa: BLE001
            return _result_error(f"desktop_open_aelin_failed:{str(exc)[:160]}")
        return _result_ok(
            route=str(result.get("route") or route),
            opened=bool(result.get("opened")),
            detail=str(result.get("detail") or ""),
            summary=f"Aelin 已切换到 {str(result.get('route') or route)[:120]}",
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
