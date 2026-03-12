from __future__ import annotations

import json
from typing import Any

from app.services.aelin_limits import MAX_IMAGE_DATA_URL_LENGTH
from app.services.aelin_utils import normalize_positive_ints


def safe_json_loads(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() != "text":
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def is_multimodal_unsupported_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    hints = (
        "image_url",
        "image input",
        "vision",
        "multimodal",
        "multi-modal",
        "does not support image",
        "content type",
        "invalid type",
    )
    return any(h in text for h in hints)


def _strip_images_from_message_content(content: Any) -> tuple[Any, bool]:
    if not isinstance(content, list):
        return content, False
    removed = False
    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip().lower()
        if kind == "image_url":
            removed = True
            continue
        if kind == "text":
            text = str(item.get("text") or "").strip()
            if text:
                text_parts.append(text)
    if not removed:
        return content, False
    fallback_text = "\n".join(text_parts).strip() or "请继续，仅使用文本上下文。"
    return fallback_text, True


def strip_images_from_messages(messages: list[dict[str, Any]]) -> bool:
    removed_any = False
    for row in messages:
        if not isinstance(row, dict):
            continue
        new_content, removed = _strip_images_from_message_content(row.get("content"))
        if removed:
            row["content"] = new_content
            removed_any = True
    return removed_any


def prepare_tool_result_payload(
    *,
    tool_name: str,
    status: str,
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    run_result = dict(result or {})
    message_result = dict(result or {})
    image_data_url = ""
    if status != "completed" or tool_name != "screen_get":
        return run_result, message_result, image_data_url

    candidate = str(result.get("data_url") or "").strip()
    if not candidate.startswith("data:image/") or ";base64," not in candidate:
        return run_result, message_result, image_data_url
    if len(candidate) > MAX_IMAGE_DATA_URL_LENGTH:
        return run_result, message_result, image_data_url

    image_data_url = candidate
    message_result.pop("data_url", None)
    message_result["has_image"] = True
    message_result["image_data_url_length"] = len(candidate)
    run_result["data_url"] = f"[omitted:{len(candidate)}]"
    return run_result, message_result, image_data_url


def build_screen_observation_message(image_data_url: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "这是 screen_get 工具刚刚获取的当前屏幕截图，请先观察图像再继续。"},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ],
    }


def _normalize_input_image_data_urls(images: list[dict[str, str]] | None) -> list[str]:
    out: list[str] = []
    for item in list(images or [])[:4]:
        if not isinstance(item, dict):
            continue
        data_url = str(item.get("data_url") or "").strip()
        if not data_url.startswith("data:image/") or ";base64," not in data_url:
            continue
        if len(data_url) > MAX_IMAGE_DATA_URL_LENGTH:
            continue
        out.append(data_url)
    return out


def build_initial_messages(
    *,
    query: str,
    memory_summary: str,
    history_turns: list[dict[str, str]] | None,
    images: list[dict[str, str]] | None,
    attachment_ids: list[int] | None,
    forced_intent: str,
    forced_tool_runs: list[dict[str, Any]] | None,
    tool_skill_bodies: list[str] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are Aelin's tool-using assistant. "
                "Use tools only when needed, keep calls minimal, and provide final Chinese answer once information is enough. "
                "Never expose hidden reasoning."
            ),
        },
        {
            "role": "system",
            "content": (
                "工具使用规则：当用户问题涉及网页内容、网站状态，或需要在浏览器中执行点击、输入、滚动等操作时，"
                "优先考虑使用浏览器相关工具（例如 pinchtab 系列）在本地浏览器中完成这些步骤；对于纯搜索型问题可使用 web_search。"
                "当用户问题涉及电脑状态、截图、进程、模式切换、打开链接或唤起 Aelin 页面时，"
                "优先使用 device 与 screen_get。"
                "其中 device.action=status 用于状态查询，processes 用于进程查看，"
                "mode_apply 用于切换模式，open_url 用于打开网页，open_aelin 用于唤起 Aelin 页面。"
                "较复杂、需要多步导航或登录的网站任务，可以使用更高层的浏览器工具（如 pinchtab_agent 或会话式封装），"
                "具体使用策略由针对这些工具的技能说明（SKILL）指导。"
            ),
        },
        {
            "role": "system",
            "content": f"memory_summary={str(memory_summary or '')[:600]}",
        },
    ]
    for body in list(tool_skill_bodies or [])[:4]:
        text = str(body or "").strip()
        if not text:
            continue
        messages.append(
            {
                "role": "system",
                "content": text,
            }
        )
    if forced_intent:
        messages.append(
            {
                "role": "system",
                "content": f"forced_intent={str(forced_intent).strip()[:120]}",
            }
        )
    normalized_attachment_ids = normalize_positive_ints(attachment_ids, cap=20)
    if normalized_attachment_ids:
        messages.append(
            {
                "role": "system",
                "content": (
                    "available_attachment_ids="
                    + json.dumps(normalized_attachment_ids, ensure_ascii=False)
                    + "; 当用户问题涉及上传附件时，优先调用 attachment_search 工具再回答，并在答案里给出来源定位。"
                ),
            }
        )
    for run in list(forced_tool_runs or [])[:4]:
        name = str(run.get("name") or "").strip().lower()[:64]
        args = run.get("args") if isinstance(run.get("args"), dict) else {}
        result = run.get("result") if isinstance(run.get("result"), dict) else {}
        messages.append(
            {
                "role": "system",
                "content": (
                    f"forced_tool_result[{name}] "
                    + json.dumps({"args": args, "result": result}, ensure_ascii=False)[:5000]
                ),
            }
        )
        if name == "attachment_search" and bool(result.get("ok")):
            hits = list(result.get("hits") or [])
            content = str(result.get("content") or "").strip()
            if content:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "prefetched_attachment_content="
                            + content[:6000]
                            + f"\n(prefetched_hits={len(hits)})"
                        ),
                    }
                )
        if name == "pinchtab_session" and bool(result.get("session_id")):
            sess_id = str(result.get("session_id") or "")[:64]
            inst_id = str(result.get("instance_id") or "")[:64]
            tab_id = str(result.get("tab_id") or "")[:64]
            last_url = str(result.get("last_url") or result.get("url") or "")[:260]
            last_status = str(result.get("last_status") or result.get("status") or "")[:80]
            last_summary = str(result.get("last_summary") or result.get("summary") or "")[:200]
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "已有一个可复用的 PinchTab 浏览会话："
                        f"session_id={sess_id}, instance_id={inst_id}, tab_id={tab_id}, "
                        f"last_url={last_url}, status={last_status}, summary={last_summary}。"
                        "如果当前用户的问题需要继续在网页中操作，应优先调用 pinchtab_session 工具，"
                        f"使用 action=\"step\" 并复用这个 session_id（不要重新 start 或重新 launch_instance），"
                        "并在 goal 中用自然语言描述本轮要完成的下一步子目标。"
                    ),
                }
            )

    if history_turns:
        for row in history_turns[-6:]:
            role = str(row.get("role") or "").strip().lower()
            content = str(row.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content[:1200]})

    query_text = str(query or "").strip()[:1200]
    query_fallback_text = query_text or ("请先分析我上传的图片，再继续执行工具流程。" if not normalized_attachment_ids else "请先检索并分析我上传的附件内容，再继续。")
    normalized_images = _normalize_input_image_data_urls(images)
    if normalized_images:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": query_fallback_text}]
        for data_url in normalized_images:
            user_content.append({"type": "image_url", "image_url": {"url": data_url}})
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": query_text})
    return messages
