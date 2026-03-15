from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from app.settings import settings


def _safe_int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = default
    return max(low, min(high, out))


def _compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _truncate_error(text: str, *, limit: int = 220) -> str:
    compact = " ".join(str(text or "").strip().split())
    return compact[:limit] or "google_workspace_cli_error"


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("messages", "files", "events", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


class GoogleWorkspaceCliService:
    """
    Thin wrapper around the local `gws` CLI.

    Aelin should never shell out to arbitrary Google Workspace commands. This
    service constrains the integration to a small set of stable, read-only
    helpers and normalizes their JSON output for tool consumption.
    """

    def __init__(
        self,
        *,
        bin_path: str | None = None,
        timeout_seconds: float | None = None,
        config_dir: str | None = None,
    ) -> None:
        self._configured_bin_path = str(bin_path or settings.google_workspace_cli_bin or "gws").strip() or "gws"
        self._timeout_seconds = max(
            5.0,
            float(timeout_seconds if timeout_seconds is not None else settings.google_workspace_cli_timeout_seconds),
        )
        self._config_dir = str(config_dir if config_dir is not None else settings.google_workspace_cli_config_dir).strip()

    def _resolve_bin_path(self) -> str:
        configured = self._configured_bin_path
        if os.path.isabs(configured):
            return configured if os.path.exists(configured) else ""
        found = shutil.which(configured)
        return found or ""

    def is_available(self) -> bool:
        return bool(self._resolve_bin_path())

    def configured_bin_path(self) -> str:
        return self._configured_bin_path

    def resolved_bin_path(self) -> str:
        return self._resolve_bin_path()

    def config_dir(self) -> str:
        return self._config_dir

    def login_command(self) -> list[str]:
        # Prefer the resolved binary path when available so the hint works even
        # when google_workspace_cli_bin is an absolute path and `gws` is not on PATH.
        bin_hint = self._resolve_bin_path() or self._configured_bin_path or "gws"
        return [bin_hint, "auth", "login"]

    def install_hint(self) -> str:
        configured = self._configured_bin_path
        if configured and configured != "gws":
            return f"请确认已安装 gws，并检查 MERCURYDESK_GOOGLE_WORKSPACE_CLI_BIN 指向: {configured}"
        return "当前机器未安装 gws，请先安装或随桌面版一起打包 gws 二进制。"

    def runtime_status(self) -> dict[str, Any]:
        resolved = self._resolve_bin_path()
        next_action = "login" if resolved else "install"
        return {
            "ok": True,
            "available": bool(resolved),
            "configured_bin_path": self._configured_bin_path,
            "resolved_bin_path": resolved,
            "config_dir": self._config_dir,
            "login_command": self.login_command(),
            "install_hint": ("" if resolved else self.install_hint()),
            "next_action": next_action,
        }

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self._config_dir:
            env["GWS_CONFIG_DIR"] = self._config_dir
        return env

    def _run_json(self, args: list[str], *, timeout_seconds: float | None = None) -> dict[str, Any]:
        bin_path = self._resolve_bin_path()
        if not bin_path:
            return {"ok": False, "error": "gws_not_installed"}
        timeout = max(5.0, float(timeout_seconds if timeout_seconds is not None else self._timeout_seconds))
        try:
            proc = subprocess.run(
                [bin_path, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self._env(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "gws_timeout"}
        except Exception as exc:
            return {"ok": False, "error": f"gws_exec_failed:{_truncate_error(str(exc))}"}

        stdout = str(proc.stdout or "").strip()
        stderr = str(proc.stderr or "").strip()
        if int(proc.returncode or 0) != 0:
            detail = stderr or stdout or f"exit_code={proc.returncode}"
            return {"ok": False, "error": f"gws_failed:{_truncate_error(detail)}"}
        if not stdout:
            return {"ok": True, "data": {}}
        try:
            payload = json.loads(stdout)
        except Exception:
            return {"ok": False, "error": "gws_invalid_json", "raw": stdout[:2000]}
        return {"ok": True, "data": payload}

    def auth_status(self) -> dict[str, Any]:
        runtime = self.runtime_status()
        if not bool(runtime.get("available")):
            return {
                **runtime,
                "ok": False,
                "error": "gws_not_installed",
            }
        result = self._run_json(["auth", "status"])
        if not bool(result.get("ok")):
            return {
                **runtime,
                **result,
            }
        payload = result.get("data")
        if not isinstance(payload, dict):
            payload = {}
        # Treat missing/falsey `authenticated` as unauthenticated by default.
        authenticated = bool(payload.get("authenticated"))
        return {
            "ok": True,
            **runtime,
            "authenticated": authenticated,
            "email": str(payload.get("email") or payload.get("account") or "")[:160],
            "scopes": [str(item or "")[:160] for item in list(payload.get("scopes") or [])[:32]],
            "next_action": ("ready" if authenticated else "login"),
            "raw": payload,
        }

    def gmail_list_messages(
        self,
        *,
        query: str = "",
        max_results: int = 10,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "userId": "me",
            "maxResults": _safe_int(max_results, 10, low=1, high=50),
        }
        if str(query or "").strip():
            params["q"] = str(query).strip()[:500]
        if include_spam_trash:
            params["includeSpamTrash"] = True
        result = self._run_json(["gmail", "users", "messages", "list", "--params", _compact_json(params)])
        if not bool(result.get("ok")):
            return result
        payload = result.get("data")
        items = _extract_items(payload)
        return {"ok": True, "items": items, "raw": payload}

    def gmail_get_message(self, *, message_id: str, fmt: str = "full") -> dict[str, Any]:
        msg_id = str(message_id or "").strip()
        if not msg_id:
            return {"ok": False, "error": "missing_message_id"}
        format_clean = str(fmt or "full").strip().lower()
        if format_clean not in {"full", "metadata", "minimal"}:
            format_clean = "full"
        params = {"userId": "me", "id": msg_id, "format": format_clean}
        result = self._run_json(["gmail", "users", "messages", "get", "--params", _compact_json(params)])
        if not bool(result.get("ok")):
            return result
        payload = result.get("data")
        return {"ok": True, "item": payload if isinstance(payload, dict) else {}, "raw": payload}

    def drive_list_files(self, *, query: str = "", max_results: int = 10) -> dict[str, Any]:
        params: dict[str, Any] = {"pageSize": _safe_int(max_results, 10, low=1, high=50)}
        if str(query or "").strip():
            params["q"] = str(query).strip()[:500]
        result = self._run_json(["drive", "files", "list", "--params", _compact_json(params)])
        if not bool(result.get("ok")):
            return result
        payload = result.get("data")
        items = _extract_items(payload)
        return {"ok": True, "items": items, "raw": payload}

    def calendar_list_events(
        self,
        *,
        calendar_id: str = "primary",
        time_min: str = "",
        time_max: str = "",
        max_results: int = 10,
        single_events: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "calendarId": str(calendar_id or "primary").strip()[:120] or "primary",
            "maxResults": _safe_int(max_results, 10, low=1, high=50),
            "singleEvents": bool(single_events),
            "orderBy": "startTime",
        }
        if str(time_min or "").strip():
            params["timeMin"] = str(time_min).strip()[:64]
        if str(time_max or "").strip():
            params["timeMax"] = str(time_max).strip()[:64]
        result = self._run_json(["calendar", "events", "list", "--params", _compact_json(params)])
        if not bool(result.get("ok")):
            return result
        payload = result.get("data")
        items = _extract_items(payload)
        return {"ok": True, "items": items, "raw": payload}


_google_workspace_cli_service: GoogleWorkspaceCliService | None = None


def get_google_workspace_cli_service() -> GoogleWorkspaceCliService:
    global _google_workspace_cli_service
    if _google_workspace_cli_service is None:
        _google_workspace_cli_service = GoogleWorkspaceCliService()
    return _google_workspace_cli_service
