from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import RemoteCommand, User
from app.services.device_center import (
    DeviceScreenCaptureError,
    DesktopPluginActionError,
    activate_desktop_module,
    capture_device_screen,
    collect_device_process_items,
    desktop_plugin_health,
    device_capabilities,
    device_is_windows,
    open_desktop_external_url,
    apply_device_mode,
)
from app.settings import settings

_WHITESPACE_RE = re.compile(r"\s+")
_AT_TAG_RE = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_SUPPORTED_COMMANDS = [
    "help",
    "status",
    "screenshot",
    "processes",
    "mode",
    "open_url",
    "open_aelin",
]
_MODULE_ROUTE_ALIASES = {
    "aelin": "/",
    "home": "/",
    "chat": "/",
    "首页": "/",
    "主页": "/",
    "设置": "/settings",
    "settings": "/settings",
    "tracking": "/tracking",
    "跟踪": "/tracking",
    "追踪": "/tracking",
    "diary": "/diary",
    "日记": "/diary",
    "focus": "/focus",
    "专注": "/focus",
    "processes": "/processes",
    "进程": "/processes",
}
_MODE_ALIASES = {
    "focus": "focus",
    "专注": "focus",
    "meeting": "meeting",
    "会议": "meeting",
    "sleep": "sleep",
    "睡眠": "sleep",
    "normal": "normal",
    "恢复": "normal",
    "正常": "normal",
    "default": "normal",
}


class RemoteControlParseError(ValueError):
    def __init__(self, reply_text: str) -> None:
        super().__init__(reply_text)
        self.reply_text = reply_text.strip()


@dataclass(slots=True)
class RemoteCommandSource:
    source: str = "manual"
    open_id: str = ""
    chat_id: str = ""
    message_id: str = ""
    user_name: str = ""


@dataclass(slots=True)
class ParsedRemoteCommand:
    command_type: str
    normalized_text: str
    args: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"


@dataclass(slots=True)
class RemoteExecutionResult:
    ok: bool
    status: str
    summary: str
    reply_text: str
    result: dict[str, Any] = field(default_factory=dict)
    error_detail: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if isinstance(dt, datetime) else ""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_help_text(*, prefix: str = "") -> str:
    prefix_hint = f"{prefix} " if prefix else ""
    return "\n".join(
        [
            "可用指令：",
            f"- {prefix_hint}帮助",
            f"- {prefix_hint}状态",
            f"- {prefix_hint}截图",
            f"- {prefix_hint}进程 cpu 5",
            f"- {prefix_hint}进程 内存 8",
            f"- {prefix_hint}模式 focus",
            f"- {prefix_hint}模式 normal",
            f"- {prefix_hint}打开 Aelin",
            f"- {prefix_hint}打开网址 https://example.com",
        ]
    ).strip()


def supported_commands() -> list[str]:
    return list(_SUPPORTED_COMMANDS)


def normalize_incoming_text(text: str) -> str:
    cleaned = _AT_TAG_RE.sub(" ", str(text or ""))
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def parse_remote_command(
    text: str,
    *,
    prefix: str = "",
    allow_without_prefix: bool = True,
) -> ParsedRemoteCommand:
    normalized = normalize_incoming_text(text)
    if not normalized:
        raise RemoteControlParseError(build_help_text(prefix=prefix))

    candidate = normalized
    prefix_clean = str(prefix or "").strip()
    used_prefix = False
    if prefix_clean and candidate.lower().startswith(prefix_clean.lower()):
        candidate = candidate[len(prefix_clean) :].strip()
        used_prefix = True
    if prefix_clean and not allow_without_prefix and not used_prefix:
        raise RemoteControlParseError(f"群聊中请使用 {prefix_clean} 作为指令前缀。\n{build_help_text(prefix=prefix_clean)}")
    if not candidate:
        raise RemoteControlParseError(build_help_text(prefix=prefix_clean))

    lowered = candidate.lower()
    if lowered in {"help", "帮助", "命令", "菜单"}:
        return ParsedRemoteCommand("help", normalized, {})
    if lowered in {"status", "状态", "电脑状态", "健康检查"}:
        return ParsedRemoteCommand("status", normalized, {})
    if lowered in {"截图", "截屏", "screenshot", "screen"}:
        return ParsedRemoteCommand("screenshot", normalized, {})

    process_match = re.match(
        r"^(?:进程|process(?:es)?|top)(?:\s+(cpu|memory|mem|内存))?(?:\s+(\d{1,3}))?$",
        lowered,
        re.IGNORECASE,
    )
    if process_match:
        sort_raw = str(process_match.group(1) or "cpu").lower()
        sort_by = "memory" if sort_raw in {"memory", "mem", "内存"} else "cpu"
        limit = max(1, min(20, int(process_match.group(2) or 5)))
        return ParsedRemoteCommand("processes", normalized, {"sort_by": sort_by, "limit": limit})

    mode_match = re.match(r"^(?:模式|mode|切换|切换到|设为)\s+(.+)$", candidate, re.IGNORECASE)
    if mode_match:
        mode_raw = normalize_incoming_text(mode_match.group(1)).lower()
        mode = _MODE_ALIASES.get(mode_raw, "")
        if mode:
            return ParsedRemoteCommand("mode", normalized, {"mode": mode})
    if lowered.endswith("模式"):
        mode = _MODE_ALIASES.get(lowered[:-2], "")
        if mode:
            return ParsedRemoteCommand("mode", normalized, {"mode": mode})

    url_match = re.match(r"^(?:打开(?:网址|链接|网页)?|open(?:\s+url)?)\s+(\S+)$", candidate, re.IGNORECASE)
    if url_match:
        url = str(url_match.group(1) or "").strip()
        if not _URL_RE.match(url):
            raise RemoteControlParseError("只支持 http/https 链接。")
        return ParsedRemoteCommand("open_url", normalized, {"url": url}, risk_level="medium")

    module_match = re.match(r"^(?:打开(?:应用|页面)?|open)\s+(.+)$", candidate, re.IGNORECASE)
    if module_match:
        module_raw = normalize_incoming_text(module_match.group(1)).lower()
        route = _MODULE_ROUTE_ALIASES.get(module_raw, "")
        if route:
            return ParsedRemoteCommand("open_aelin", normalized, {"route": route})

    raise RemoteControlParseError(f"未识别的指令：{candidate}\n{build_help_text(prefix=prefix_clean)}")


def resolve_remote_control_user(db: Session) -> User:
    configured_email = str(getattr(settings, "feishu_bot_bind_user_email", "") or "").strip().lower()
    if configured_email:
        bound = db.scalar(select(User).where(User.email == configured_email))
        if bound is not None:
            return bound
    user = db.scalar(select(User).order_by(User.id.asc()))
    if user is not None:
        return user
    return crud.create_user(
        db,
        email=configured_email or "local@aelin.local",
        password=f"local-{uuid4().hex}-{uuid4().hex}",
    )


def build_remote_command_item(row: RemoteCommand) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "workspace": str(row.workspace or "default"),
        "source": str(row.source or "manual"),
        "source_user_name": str(row.source_user_name or ""),
        "source_open_id": str(row.source_open_id or ""),
        "source_chat_id": str(row.source_chat_id or ""),
        "source_message_id": str(row.source_message_id or ""),
        "raw_text": str(row.raw_text or ""),
        "normalized_text": str(row.normalized_text or ""),
        "command_type": str(row.command_type or ""),
        "risk_level": str(row.risk_level or "low"),
        "status": str(row.status or "pending"),
        "summary": str(row.summary or ""),
        "result": _json_loads(row.result_json),
        "error_detail": str(row.error_detail or ""),
        "created_at": _iso(row.created_at),
        "started_at": _iso(row.started_at),
        "completed_at": _iso(row.completed_at),
    }


def list_remote_commands(
    db: Session,
    *,
    user_id: int,
    workspace: str = "",
    limit: int = 30,
) -> list[RemoteCommand]:
    cap = max(1, min(100, int(limit or 30)))
    query = select(RemoteCommand).where(RemoteCommand.user_id == user_id)
    workspace_clean = str(workspace or "").strip()
    if workspace_clean:
        query = query.where(RemoteCommand.workspace == workspace_clean)
    query = query.order_by(RemoteCommand.created_at.desc(), RemoteCommand.id.desc()).limit(cap)
    return list(db.scalars(query).all())


def _format_process_reply(items: list[Any], *, sort_by: str) -> str:
    if not items:
        return "当前没有可用的进程数据。"
    title = "内存" if sort_by == "memory" else "CPU"
    lines = [f"{title} Top {len(items)}："]
    for index, item in enumerate(items[:10], start=1):
        cpu = float(getattr(item, "cpu_percent", 0.0) or 0.0)
        memory_mb = float(getattr(item, "memory_mb", 0.0) or 0.0)
        lines.append(
            f"{index}. {getattr(item, 'name', 'unknown')} PID {getattr(item, 'pid', 0)} "
            f"CPU {cpu:.1f}% MEM {memory_mb:.1f}MB"
        )
    return "\n".join(lines)


def _execute_parsed_command(parsed: ParsedRemoteCommand) -> RemoteExecutionResult:
    if parsed.command_type == "help":
        reply = build_help_text(prefix=str(getattr(settings, "feishu_bot_command_prefix", "") or "").strip())
        return RemoteExecutionResult(True, "succeeded", "已返回帮助指令", reply, {"commands": supported_commands()})

    if parsed.command_type == "status":
        platform_name, capabilities, notes = device_capabilities()
        plugin_ok = desktop_plugin_health()
        lines = [
            f"平台：{platform_name}",
            f"桌面插件：{'在线' if plugin_ok else '不可达'}",
            f"Windows 运行时：{'是' if device_is_windows() else '否'}",
            "支持能力：" + ", ".join(sorted([key for key, enabled in capabilities.items() if enabled])),
        ]
        if notes:
            lines.append("备注：" + "；".join(notes[:2]))
        reply = "\n".join(lines)
        return RemoteExecutionResult(
            True,
            "succeeded",
            "已返回电脑状态",
            reply,
            {"platform": platform_name, "capabilities": capabilities, "plugin_reachable": plugin_ok},
        )

    if parsed.command_type == "screenshot":
        shot = capture_device_screen(max_edge=1600, image_format="jpeg", quality=78)
        saved_path = str(shot.get("saved_path") or "").strip()
        reply = "截图完成。"
        if saved_path:
            reply = f"截图完成，已保存到：{saved_path}"
        return RemoteExecutionResult(
            True,
            "succeeded",
            "已完成截图",
            reply,
            {
                "captured_at": str(shot.get("captured_at") or ""),
                "width": int(shot.get("width") or 0),
                "height": int(shot.get("height") or 0),
                "saved_path": saved_path,
                "name": str(shot.get("name") or ""),
            },
        )

    if parsed.command_type == "processes":
        sort_by = str(parsed.args.get("sort_by") or "cpu")
        limit = max(1, min(20, int(parsed.args.get("limit") or 5)))
        items = collect_device_process_items(sort_by=sort_by, limit=limit)
        reply = _format_process_reply(items, sort_by=sort_by)
        return RemoteExecutionResult(
            True,
            "succeeded",
            f"已返回 {sort_by} 进程列表",
            reply,
            {
                "sort_by": sort_by,
                "items": [item.model_dump() for item in items],
            },
        )

    if parsed.command_type == "mode":
        mode = str(parsed.args.get("mode") or "normal")
        applied_mode, status, summary, steps, warnings = apply_device_mode(mode)
        lines = [summary]
        if steps:
            lines.append("步骤：" + "；".join(steps[:3]))
        if warnings:
            lines.append("警告：" + "；".join(warnings[:3]))
        return RemoteExecutionResult(
            True,
            "succeeded",
            f"已切换到 {applied_mode} 模式",
            "\n".join(lines),
            {
                "mode": applied_mode,
                "status": status,
                "steps": steps,
                "warnings": warnings,
            },
        )

    if parsed.command_type == "open_url":
        url = str(parsed.args.get("url") or "").strip()
        payload = open_desktop_external_url(url)
        return RemoteExecutionResult(
            True,
            "succeeded",
            "已在电脑上打开网址",
            f"已在电脑上打开：{url}",
            payload,
        )

    if parsed.command_type == "open_aelin":
        route = str(parsed.args.get("route") or "/").strip() or "/"
        payload = activate_desktop_module(route)
        return RemoteExecutionResult(
            True,
            "succeeded",
            "已唤起 Aelin 窗口",
            f"Aelin 已切换到 {payload.get('route') or route}",
            payload,
        )

    raise RuntimeError(f"unsupported_command:{parsed.command_type}")


def execute_remote_command(
    db: Session,
    *,
    user: User,
    text: str,
    workspace: str = "",
    source: RemoteCommandSource | None = None,
    prefix: str = "",
    allow_without_prefix: bool = True,
) -> tuple[RemoteCommand, RemoteExecutionResult]:
    source_info = source or RemoteCommandSource()
    workspace_clean = str(workspace or getattr(settings, "feishu_bot_workspace", "default") or "default").strip() or "default"
    normalized_text = normalize_incoming_text(text)
    now = _now()

    row = RemoteCommand(
        user_id=int(user.id),
        workspace=workspace_clean,
        source=str(source_info.source or "manual")[:32],
        source_open_id=str(source_info.open_id or "")[:128] or None,
        source_chat_id=str(source_info.chat_id or "")[:128] or None,
        source_message_id=str(source_info.message_id or "")[:128] or None,
        source_user_name=str(source_info.user_name or "")[:255] or None,
        raw_text=str(text or "")[:4000],
        normalized_text=normalized_text[:4000],
        command_type="unknown",
        args_json="{}",
        risk_level="low",
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()

    try:
        parsed = parse_remote_command(normalized_text, prefix=prefix, allow_without_prefix=allow_without_prefix)
    except RemoteControlParseError as exc:
        result = RemoteExecutionResult(
            ok=False,
            status="rejected",
            summary="未识别的远程指令",
            reply_text=exc.reply_text,
            result={"commands": supported_commands(), "help": build_help_text(prefix=prefix)},
            error_detail=exc.reply_text,
        )
        row.status = result.status
        row.summary = result.summary
        row.error_detail = result.error_detail
        row.result_json = _json_dumps(result.result)
        row.completed_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row, result

    row.command_type = parsed.command_type
    row.args_json = _json_dumps(parsed.args)
    row.risk_level = parsed.risk_level
    row.status = "running"
    row.started_at = _now()
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        result = _execute_parsed_command(parsed)
    except (DeviceScreenCaptureError, DesktopPluginActionError) as exc:
        result = RemoteExecutionResult(
            ok=False,
            status="failed",
            summary="远程命令执行失败",
            reply_text=str(exc),
            result={},
            error_detail=str(exc),
        )
    except Exception as exc:
        result = RemoteExecutionResult(
            ok=False,
            status="failed",
            summary="远程命令执行异常",
            reply_text=f"执行失败：{str(exc)[:180]}",
            result={},
            error_detail=str(exc)[:500],
        )

    row.status = result.status
    row.summary = result.summary
    row.result_json = _json_dumps(result.result)
    row.error_detail = result.error_detail or None
    row.completed_at = _now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, result

