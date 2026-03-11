from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.db import create_session
from app.services.remote_control import RemoteCommandSource, execute_remote_command, resolve_remote_control_user
from app.settings import settings

try:
    import lark_oapi as lark  # type: ignore

    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    lark = None  # type: ignore[assignment]
    _SDK_AVAILABLE = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv(raw: str) -> set[str]:
    return {item.strip() for item in str(raw or "").split(",") if item.strip()}


def _dig(payload: dict[str, Any], *parts: str) -> Any:
    cursor: Any = payload
    for part in parts:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _parse_message_text(raw_content: Any) -> str:
    if isinstance(raw_content, dict):
        text = raw_content.get("text")
        return str(text or "").strip()
    if not isinstance(raw_content, str):
        return ""
    text = raw_content.strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    if isinstance(parsed, dict):
        return str(parsed.get("text") or "").strip()
    return text


class FeishuBotService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_error = ""
        self._started_at = ""
        self._last_event_at = ""
        self._seen_message_ids: dict[str, float] = {}
        self._ws_client: Any = None
        self._tenant_access_token = ""
        self._tenant_access_token_expire_at = 0.0
        self._command_lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            configured = bool(str(getattr(settings, "feishu_app_id", "") or "").strip()) and bool(
                str(getattr(settings, "feishu_app_secret", "") or "").strip()
            )
            return {
                "enabled": bool(getattr(settings, "feishu_bot_enabled", False)),
                "running": self._running,
                "configured": configured,
                "sdk_available": _SDK_AVAILABLE,
                "started_at": self._started_at,
                "last_event_at": self._last_event_at,
                "last_error": self._last_error,
            }

    def start(self) -> None:
        if not getattr(settings, "feishu_bot_enabled", False):
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._last_error = ""
            self._thread = threading.Thread(target=self._run, name="feishu-bot", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            client = self._ws_client
        stopper = getattr(client, "stop", None)
        if callable(stopper):
            try:
                stopper()
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

    def _run(self) -> None:  # pragma: no cover - exercised through runtime integration
        app_id = str(getattr(settings, "feishu_app_id", "") or "").strip()
        app_secret = str(getattr(settings, "feishu_app_secret", "") or "").strip()
        if not app_id or not app_secret:
            self._set_error("feishu_app_credentials_missing")
            return
        if not _SDK_AVAILABLE:
            self._set_error("lark_oapi_not_installed")
            return

        try:
            thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(thread_loop)
            try:
                import lark_oapi.ws.client as lark_ws_client  # type: ignore

                lark_ws_client.loop = thread_loop
            except Exception:
                pass
            handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(
                self._on_message_event
            ).build()
            log_level = getattr(getattr(lark, "LogLevel", object), "INFO", None)
            kwargs = {"event_handler": handler}
            if log_level is not None:
                kwargs["log_level"] = log_level
            client = lark.ws.Client(app_id, app_secret, **kwargs)
            with self._lock:
                self._ws_client = client
            self._set_running(True)
            client.start()
        except Exception as exc:
            self._set_error(f"feishu_bot_runtime_error: {str(exc)[:300]}")
        finally:
            try:
                current_loop = asyncio.get_event_loop()
                if current_loop and not current_loop.is_closed():
                    current_loop.stop()
                    current_loop.close()
            except Exception:
                pass
            with self._lock:
                self._ws_client = None
            self._set_running(False)

    def _event_to_dict(self, data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            return data
        if _SDK_AVAILABLE:
            try:
                raw = lark.JSON.marshal(data)
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        try:
            parsed = json.loads(json.dumps(data, ensure_ascii=False, default=lambda item: getattr(item, "__dict__", str(item))))
        except Exception:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    def _is_duplicate_message(self, message_id: str) -> bool:
        message_id_clean = str(message_id or "").strip()
        if not message_id_clean:
            return False
        now = time.time()
        ttl = max(60, int(getattr(settings, "feishu_bot_message_dedupe_ttl_seconds", 600) or 600))
        with self._lock:
            expired = [key for key, ts in self._seen_message_ids.items() if (now - float(ts)) > ttl]
            for key in expired:
                self._seen_message_ids.pop(key, None)
            if message_id_clean in self._seen_message_ids:
                return True
            self._seen_message_ids[message_id_clean] = now
        return False

    def _is_allowed(self, *, open_id: str, chat_id: str) -> bool:
        allowed_open_ids = _split_csv(str(getattr(settings, "feishu_bot_allowed_open_ids_csv", "") or ""))
        allowed_chat_ids = _split_csv(str(getattr(settings, "feishu_bot_allowed_chat_ids_csv", "") or ""))
        if allowed_open_ids and str(open_id or "").strip() not in allowed_open_ids:
            return False
        if allowed_chat_ids and str(chat_id or "").strip() not in allowed_chat_ids:
            return False
        return True

    def _get_tenant_access_token(self) -> str:
        now = time.time()
        with self._lock:
            if self._tenant_access_token and now < max(0.0, self._tenant_access_token_expire_at - 60):
                return self._tenant_access_token

        payload = {
            "app_id": str(getattr(settings, "feishu_app_id", "") or "").strip(),
            "app_secret": str(getattr(settings, "feishu_app_secret", "") or "").strip(),
        }
        timeout_s = max(5.0, float(getattr(settings, "feishu_bot_reply_timeout_seconds", 15.0) or 15.0))
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
            resp = client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json=payload,
            )
        resp.raise_for_status()
        data = resp.json()
        if int(data.get("code") or 0) != 0:
            raise RuntimeError(f"tenant_access_token_failed:{str(data.get('msg') or data)[:200]}")
        token = str(data.get("tenant_access_token") or "").strip()
        if not token:
            raise RuntimeError(f"tenant_access_token_missing:{str(data)[:200]}")
        expire = max(300, int(data.get("expire") or 7200))
        with self._lock:
            self._tenant_access_token = token
            self._tenant_access_token_expire_at = now + expire
        return token

    def _send_text(self, chat_id: str, text: str) -> None:
        chat_id_clean = str(chat_id or "").strip()
        text_clean = str(text or "").strip()
        if not chat_id_clean or not text_clean:
            return
        token = self._get_tenant_access_token()
        body = {
            "receive_id": chat_id_clean,
            "msg_type": "text",
            "content": json.dumps({"text": text_clean}, ensure_ascii=False),
        }
        timeout_s = max(5.0, float(getattr(settings, "feishu_bot_reply_timeout_seconds", 15.0) or 15.0))
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
            resp = client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
        resp.raise_for_status()
        data = resp.json()
        if int(data.get("code") or 0) != 0:
            raise RuntimeError(f"send_message_failed:{str(data.get('msg') or data)[:200]}")

    def _on_message_event(self, data: Any) -> None:  # pragma: no cover - exercised through runtime integration
        payload = self._event_to_dict(data)
        try:
            self.handle_message_payload(payload)
        except Exception as exc:
            self._set_error(f"feishu_message_handle_error: {str(exc)[:300]}")

    def handle_message_payload(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        self._mark_event()
        event = _dig(payload, "event")
        if not isinstance(event, dict):
            return

        message = _dig(event, "message")
        sender = _dig(event, "sender")
        if not isinstance(message, dict) or not isinstance(sender, dict):
            return

        message_type = str(message.get("message_type") or "").strip().lower()
        if message_type and message_type != "text":
            chat_id = str(message.get("chat_id") or "").strip()
            self._send_text(chat_id, "当前只支持文本指令。")
            return

        sender_type = str(sender.get("sender_type") or "").strip().lower()
        if sender_type and sender_type != "user":
            return

        message_id = str(message.get("message_id") or "").strip()
        if self._is_duplicate_message(message_id):
            return

        chat_id = str(message.get("chat_id") or "").strip()
        chat_type = str(message.get("chat_type") or "").strip().lower()
        open_id = str(_dig(sender, "sender_id", "open_id") or "").strip()
        user_name = str(sender.get("sender_name") or sender.get("name") or open_id or "Feishu User").strip()
        text = _parse_message_text(message.get("content"))
        if not text:
            self._send_text(chat_id, "消息内容为空，请发送文本指令。")
            return

        if not self._is_allowed(open_id=open_id, chat_id=chat_id):
            self._send_text(chat_id, "你没有被授权执行电脑端指令。")
            return

        prefix = str(getattr(settings, "feishu_bot_command_prefix", "") or "").strip()
        require_prefix = bool(chat_type and chat_type != "p2p" and getattr(settings, "feishu_bot_group_require_prefix", True))
        normalized = str(text or "").strip()
        if require_prefix and prefix and not normalized.lower().startswith(prefix.lower()):
            return

        with self._command_lock:
            with create_session() as db:
                user = resolve_remote_control_user(db)
                row, result = execute_remote_command(
                    db,
                    user=user,
                    text=text,
                    workspace=str(getattr(settings, "feishu_bot_workspace", "default") or "default"),
                    source=RemoteCommandSource(
                        source="feishu",
                        open_id=open_id,
                        chat_id=chat_id,
                        message_id=message_id,
                        user_name=user_name,
                    ),
                    prefix=prefix,
                    allow_without_prefix=not require_prefix,
                )
                _ = row
        self._send_text(chat_id, result.reply_text)


feishu_bot_service = FeishuBotService()
