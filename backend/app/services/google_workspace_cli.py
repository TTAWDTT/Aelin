from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from email.message import EmailMessage
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


def _normalize_string_list(values: Any, *, max_items: int, item_len: int = 254) -> list[str]:
    out: list[str] = []
    if not values:
        return out
    for raw in list(values)[: max(0, int(max_items))]:
        text = str(raw or "").strip()
        if text:
            out.append(text[: max(1, int(item_len))])
    return out


class GoogleWorkspaceCliService:
    """
    Thin wrapper around the local `gws` CLI.

    Aelin should never shell out to arbitrary Google Workspace commands. This
    service constrains the integration to a small set of stable helpers,
    primarily read-focused, plus a few carefully wrapped write helpers for
    sending mail and creating calendar events.
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

    def _build_gmail_raw_message(
        self,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        subject: str = "",
        body: str = "",
    ) -> str:
        msg = EmailMessage()
        if to:
            msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        if subject:
            msg["Subject"] = subject[:300]
        msg.set_content(str(body or "")[:8000], charset="utf-8")
        raw_bytes = msg.as_bytes()
        encoded = base64.urlsafe_b64encode(raw_bytes).decode("ascii")
        return encoded

    def gmail_send_message(
        self,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        subject: str = "",
        body: str = "",
    ) -> dict[str, Any]:
        to_clean = _normalize_string_list(to, max_items=16)
        cc_clean = _normalize_string_list(cc or [], max_items=16)
        bcc_clean = _normalize_string_list(bcc or [], max_items=16)
        if not to_clean and not cc_clean and not bcc_clean:
            return {"ok": False, "error": "missing_recipients"}
        raw_encoded = self._build_gmail_raw_message(
            to=to_clean,
            cc=cc_clean or None,
            bcc=bcc_clean or None,
            subject=str(subject or "")[:300],
            body=str(body or ""),
        )
        payload = {"raw": raw_encoded}
        result = self._run_json(["gmail", "users", "messages", "send", "--json", _compact_json(payload)])
        if not bool(result.get("ok")):
            return result
        data = result.get("data")
        return {"ok": True, "item": data if isinstance(data, dict) else {}, "raw": data}

    def gmail_create_draft(
        self,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        subject: str = "",
        body: str = "",
    ) -> dict[str, Any]:
        to_clean = _normalize_string_list(to, max_items=16)
        cc_clean = _normalize_string_list(cc or [], max_items=16)
        bcc_clean = _normalize_string_list(bcc or [], max_items=16)
        if not to_clean and not cc_clean and not bcc_clean:
            return {"ok": False, "error": "missing_recipients"}
        raw_encoded = self._build_gmail_raw_message(
            to=to_clean,
            cc=cc_clean or None,
            bcc=bcc_clean or None,
            subject=str(subject or "")[:300],
            body=str(body or ""),
        )
        payload = {"message": {"raw": raw_encoded}}
        result = self._run_json(["gmail", "users", "drafts", "create", "--json", _compact_json(payload)])
        if not bool(result.get("ok")):
            return result
        data = result.get("data")
        return {"ok": True, "item": data if isinstance(data, dict) else {}, "raw": data}

    def calendar_create_event(
        self,
        *,
        calendar_id: str = "primary",
        summary: str = "",
        description: str = "",
        start: str = "",
        end: str = "",
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        cal_id = str(calendar_id or "primary").strip() or "primary"
        start_clean = str(start or "").strip()
        end_clean = str(end or "").strip()
        if not start_clean or not end_clean:
            return {"ok": False, "error": "missing_event_time"}
        event: dict[str, Any] = {
            "summary": str(summary or "")[:300],
            "start": {"dateTime": start_clean[:64]},
            "end": {"dateTime": end_clean[:64]},
        }
        if description:
            event["description"] = str(description or "")[:2000]
        attendee_list = _normalize_string_list(attendees or [], max_items=16)
        if attendee_list:
            event["attendees"] = [{"email": addr} for addr in attendee_list]
        params = {"calendarId": cal_id}
        result = self._run_json(
            ["calendar", "events", "insert", "--params", _compact_json(params), "--json", _compact_json(event)]
        )
        if not bool(result.get("ok")):
            return result
        data = result.get("data")
        return {"ok": True, "item": data if isinstance(data, dict) else {}, "raw": data}

    def docs_create_document(self, *, title: str) -> dict[str, Any]:
        """
        Create a new Google Docs document via gws.

        Thin wrapper around:

            gws docs documents create --json '{\"title\": \"...\"}'
        """
        title_clean = str(title or "").strip()[:300] or "Untitled"
        payload = {"title": title_clean}
        result = self._run_json(["docs", "documents", "create", "--json", _compact_json(payload)])
        if not bool(result.get("ok")):
            return result
        data = result.get("data")
        return {"ok": True, "item": data if isinstance(data, dict) else {}, "raw": data}

    def docs_append_text(self, *, document_id: str, text: str) -> dict[str, Any]:
        """
        Append plain text to an existing Google Docs document via gws.

        Thin wrapper around:

            gws docs +write --document DOC_ID --text '...'
        """
        doc_id = str(document_id or "").strip()
        if not doc_id:
            return {"ok": False, "error": "missing_document_id"}
        text_clean = str(text or "").strip()
        if not text_clean:
            return {"ok": False, "error": "missing_text"}
        # Avoid sending unbounded payloads over the CLI; this limit is
        # comparable to Gmail body truncation above.
        text_clean = text_clean[:8000]
        result = self._run_json(["docs", "+write", "--document", doc_id, "--text", text_clean])
        if not bool(result.get("ok")):
            return result
        data = result.get("data")
        return {"ok": True, "item": data if isinstance(data, dict) else {}, "raw": data}


_google_workspace_cli_service: GoogleWorkspaceCliService | None = None


def get_google_workspace_cli_service() -> GoogleWorkspaceCliService:
    global _google_workspace_cli_service
    if _google_workspace_cli_service is None:
        _google_workspace_cli_service = GoogleWorkspaceCliService()
    return _google_workspace_cli_service
