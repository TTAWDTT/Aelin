from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import websockets

from app.db import create_session
from app.schemas import RemoteControlExecuteRequest
from app.services.device.remote_control import (
    RemoteCommandSource,
    execute_remote_control_request,
    resolve_remote_control_user,
)
from app.settings import settings

_log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv(raw: str) -> set[str]:
    return {item.strip() for item in str(raw or "").split(",") if item.strip()}


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _trim_trailing_path(path: str) -> str:
    cleaned = str(path or "").rstrip("/")
    if cleaned.endswith("/api"):
        return cleaned[:-4]
    if cleaned.endswith("/event"):
        return cleaned[:-6]
    return cleaned


def _build_ws_url(path_suffix: str) -> str:
    raw = str(getattr(settings, "qq_bot_ws_url", "") or "").strip()
    parsed = urlparse(raw)
    base_path = _trim_trailing_path(parsed.path or "")
    suffix = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}"
    new_path = f"{base_path}{suffix}" if base_path else suffix
    return urlunparse(parsed._replace(path=new_path or "/"))


def _extract_message_text(message: Any, raw_message: Any) -> str:
    raw_text = str(raw_message or "").strip()
    if raw_text:
        return raw_text
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, dict):
        if str(message.get("type") or "").strip().lower() == "text":
            data = message.get("data") or {}
            if isinstance(data, dict):
                return str(data.get("text") or "").strip()
        return ""
    if not isinstance(message, list):
        return ""
    parts: list[str] = []
    for segment in message:
        if not isinstance(segment, dict):
            continue
        if str(segment.get("type") or "").strip().lower() != "text":
            continue
        data = segment.get("data") or {}
        if isinstance(data, dict):
            parts.append(str(data.get("text") or ""))
    return "".join(parts).strip()


@dataclass(slots=True)
class QQOutgoingMessage:
    message_type: str
    user_id: int = 0
    group_id: int = 0
    text: str = ""


class QQBotService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event_ws: Any = None
        self._running = False
        self._last_error = ""
        self._started_at = ""
        self._last_event_at = ""
        self._seen_message_ids: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._command_lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            configured = bool(str(getattr(settings, "qq_bot_ws_url", "") or "").strip()) and bool(
                str(getattr(settings, "qq_bot_token", "") or "").strip()
            )
            return {
                "enabled": bool(getattr(settings, "qq_bot_enabled", False)),
                "running": self._running,
                "configured": configured,
                "started_at": self._started_at,
                "last_event_at": self._last_event_at,
                "last_error": self._last_error,
            }

    def start(self) -> None:
        if not getattr(settings, "qq_bot_enabled", False):
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._last_error = ""
            self._thread = threading.Thread(target=self._run, name="qq-bot", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        loop: asyncio.AbstractEventLoop | None
        ws: Any
        with self._lock:
            loop = self._loop
            ws = self._event_ws
        if loop is not None and ws is not None:
            try:
                asyncio.run_coroutine_threadsafe(ws.close(), loop)
            except Exception:
                pass

    def _set_running(self, value: bool) -> None:
        with self._lock:
            self._running = bool(value)
            if value:
                self._started_at = _now_iso()

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = str(message or "")[:500]

    def _mark_event(self) -> None:
        with self._lock:
            self._last_event_at = _now_iso()

    def _run(self) -> None:  # pragma: no cover - runtime integration
        try:
            asyncio.run(self._run_forever())
        except Exception as exc:
            self._set_error(f"qq_bot_runtime_error: {str(exc)[:300]}")
        finally:
            with self._lock:
                self._loop = None
                self._event_ws = None
            self._set_running(False)

    async def _run_forever(self) -> None:  # pragma: no cover - runtime integration
        ws_url = str(getattr(settings, "qq_bot_ws_url", "") or "").strip()
        token = str(getattr(settings, "qq_bot_token", "") or "").strip()
        if not ws_url or not token:
            self._set_error("qq_bot_credentials_missing")
            return

        event_url = _build_ws_url("/event")
        reconnect_delay = 3.0
        with self._lock:
            self._loop = asyncio.get_running_loop()

        while not self._stop_event.is_set():
            try:
                async with websockets.connect(
                    event_url,
                    additional_headers={"Authorization": f"Bearer {token}"},
                    open_timeout=5,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=None,
                ) as ws:
                    with self._lock:
                        self._event_ws = ws
                    self._set_running(True)
                    self._set_error("")
                    _log.info("qq bot connected event_url=%s", event_url)
                    await self._consume_event_stream(ws)
            except Exception as exc:
                self._set_running(False)
                self._set_error(f"qq_bot_event_stream_error: {str(exc)[:300]}")
                _log.warning("qq bot event stream disconnected: %s", str(exc)[:200])
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(reconnect_delay)
            finally:
                with self._lock:
                    self._event_ws = None

    def _parse_ws_payload(self, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8", errors="replace")
            except Exception:
                return None
        if not isinstance(raw, str):
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    async def _consume_event_stream(self, ws: Any) -> None:
        async for raw in ws:
            if self._stop_event.is_set():
                break
            payload = self._parse_ws_payload(raw)
            if payload is None:
                continue
            try:
                await self._process_event_payload(payload)
            except Exception as exc:
                self._set_error(f"qq_message_handle_error: {str(exc)[:300]}")
                _log.warning("qq bot message handling failed: %s", str(exc)[:200])

    def _is_duplicate_message(self, message_id: str) -> bool:
        message_id_clean = str(message_id or "").strip()
        if not message_id_clean:
            return False
        now = time.time()
        ttl = max(60, int(getattr(settings, "qq_bot_message_dedupe_ttl_seconds", 600) or 600))
        with self._lock:
            expired = [key for key, ts in self._seen_message_ids.items() if (now - float(ts)) > ttl]
            for key in expired:
                self._seen_message_ids.pop(key, None)
            if message_id_clean in self._seen_message_ids:
                return True
            self._seen_message_ids[message_id_clean] = now
        return False

    def _is_allowed(self, *, user_id: int, group_id: int) -> bool:
        allowed_user_ids = _split_csv(str(getattr(settings, "qq_bot_allowed_user_ids_csv", "") or ""))
        allowed_group_ids = _split_csv(str(getattr(settings, "qq_bot_allowed_group_ids_csv", "") or ""))
        if allowed_user_ids and str(user_id) not in allowed_user_ids:
            return False
        if group_id and allowed_group_ids and str(group_id) not in allowed_group_ids:
            return False
        return True

    async def _process_event_payload(self, payload: dict[str, Any]) -> None:
        reply = await asyncio.to_thread(self.handle_message_payload, payload)
        if reply is None or not str(reply.text or "").strip():
            return
        await self._send_text(reply)

    def handle_message_payload(self, payload: dict[str, Any]) -> QQOutgoingMessage | None:
        if not isinstance(payload, dict):
            return None
        self._mark_event()
        if str(payload.get("post_type") or "").strip().lower() != "message":
            return None

        message_type = str(payload.get("message_type") or "").strip().lower()
        if message_type not in {"private", "group"}:
            return None

        message_id = str(payload.get("message_id") or "").strip()
        if self._is_duplicate_message(message_id):
            return None

        user_id = _to_int(payload.get("user_id"))
        group_id = _to_int(payload.get("group_id"))
        self_id = _to_int(payload.get("self_id"))
        if user_id and self_id and user_id == self_id:
            return None

        sender = payload.get("sender") or {}
        sender_name = ""
        if isinstance(sender, dict):
            sender_name = str(sender.get("card") or sender.get("nickname") or sender.get("user_id") or "").strip()

        if not self._is_allowed(user_id=user_id, group_id=group_id):
            return QQOutgoingMessage(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                text="You are not allowed to use this Aelin bot.",
            )

        text = _extract_message_text(payload.get("message"), payload.get("raw_message"))
        if not text:
            return QQOutgoingMessage(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                text="Only plain text messages are supported right now.",
            )

        prefix = str(getattr(settings, "qq_bot_command_prefix", "") or "").strip()
        require_prefix = bool(message_type == "group" and getattr(settings, "qq_bot_group_require_prefix", True))
        normalized = str(text or "").strip()
        if require_prefix and prefix and not normalized.lower().startswith(prefix.lower()):
            return None

        with self._command_lock:
            with create_session() as db:
                user = resolve_remote_control_user(
                    db,
                    bind_user_email=str(getattr(settings, "qq_bot_bind_user_email", "") or "").strip(),
                )
                result = execute_remote_control_request(
                    db,
                    current_user=user,
                    payload=RemoteControlExecuteRequest(
                        text=text,
                        workspace=str(getattr(settings, "qq_bot_workspace", "default") or "default"),
                        source="qq",
                    ),
                    source=RemoteCommandSource(
                        source="qq",
                        open_id=str(user_id or ""),
                        chat_id=str(group_id or user_id or ""),
                        message_id=message_id,
                        user_name=sender_name or str(user_id or "QQ User"),
                    ),
                )

        response = getattr(result, "response", result)
        reply_text = str(getattr(response, "answer", "") or "").strip() or "Aelin received the message but did not produce a usable reply."
        return QQOutgoingMessage(
            message_type=message_type,
            user_id=user_id,
            group_id=group_id,
            text=reply_text,
        )

    async def _call_api(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        api_url = _build_ws_url("/api")
        token = str(getattr(settings, "qq_bot_token", "") or "").strip()
        if not token:
            raise RuntimeError("qq_bot_token_missing")
        echo = f"qq-bot-{uuid4().hex}"
        timeout_s = max(3.0, float(getattr(settings, "qq_bot_api_timeout_seconds", 15.0) or 15.0))
        async with websockets.connect(
            api_url,
            additional_headers={"Authorization": f"Bearer {token}"},
            open_timeout=5,
            ping_interval=None,
            close_timeout=5,
            max_size=None,
        ) as ws:
            await ws.send(json.dumps({"action": action, "params": params, "echo": echo}, ensure_ascii=False))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
                payload = self._parse_ws_payload(raw)
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("echo") or "") != echo:
                    continue
                if str(payload.get("status") or "").strip().lower() != "ok" or int(payload.get("retcode") or 0) != 0:
                    raise RuntimeError(f"qq_api_error:{str(payload)[:240]}")
                data = payload.get("data")
                return data if isinstance(data, dict) else {}

    async def _send_text(self, outgoing: QQOutgoingMessage) -> None:
        params: dict[str, Any] = {
            "message_type": outgoing.message_type,
            "message": str(outgoing.text or "").strip(),
            "auto_escape": False,
        }
        if outgoing.message_type == "group":
            params["group_id"] = int(outgoing.group_id or 0)
        else:
            params["user_id"] = int(outgoing.user_id or 0)
        await self._call_api("send_msg", params)


qq_bot_service = QQBotService()

