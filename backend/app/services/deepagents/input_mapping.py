from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MAX_HISTORY_TURNS = 12
MAX_IMAGES = 4
MAX_IMAGE_DATA_URL_LENGTH = 3_000_000
MAX_STREAM_MESSAGES = 40


def _field(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def normalize_history_turns(history_turns: Sequence[Any] | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in list(history_turns or [])[-MAX_HISTORY_TURNS:]:
        role = str(_field(turn, "role") or "").strip().lower()
        content = str(_field(turn, "content") or "").strip()
        message_id = str(_field(turn, "id") or "").strip()
        if role not in {"user", "assistant", "system"}:
            continue
        if not content:
            continue
        row = {"role": role, "content": content[:3000]}
        if message_id:
            row["id"] = message_id[:128]
        messages.append(row)
    return messages


def normalize_image_inputs(images: Sequence[Any] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for image in list(images or [])[:MAX_IMAGES]:
        data_url = str(_field(image, "data_url") or "").strip()
        name = str(_field(image, "name") or "").strip()[:120]
        if not data_url.startswith("data:image/"):
            continue
        if ";base64," not in data_url:
            continue
        if len(data_url) > MAX_IMAGE_DATA_URL_LENGTH:
            continue
        out.append({"data_url": data_url, "name": name})
    return out


def build_chat_messages(
    *,
    query: str,
    query_message_id: str = "",
    history_turns: Sequence[Any] | None = None,
    images: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for turn in normalize_history_turns(history_turns):
        row: dict[str, Any] = {
            "role": turn["role"],
            "content": turn["content"],
        }
        turn_id = str(turn.get("id") or "").strip()
        if turn_id:
            row["id"] = turn_id
        messages.append(row)

    latest_query = str(query or "").strip()
    if not latest_query:
        return messages

    image_inputs = normalize_image_inputs(images)
    if not image_inputs:
        latest_row: dict[str, Any] = {"role": "user", "content": latest_query}
        if query_message_id:
            latest_row["id"] = str(query_message_id).strip()[:128]
        messages.append(latest_row)
        return messages

    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": latest_query}]
    for image in image_inputs:
        data_url = str(image.get("data_url") or "").strip()
        if not data_url:
            continue
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            }
        )
    latest_row = {
        "role": "user",
        "content": content_blocks if len(content_blocks) > 1 else latest_query,
    }
    if query_message_id:
        latest_row["id"] = str(query_message_id).strip()[:128]
    messages.append(latest_row)
    return messages


def build_invoke_payload(
    *,
    query: str,
    query_message_id: str = "",
    history_turns: Sequence[Any] | None = None,
    images: Sequence[Any] | None = None,
    files_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messages": build_chat_messages(
            query=query,
            query_message_id=query_message_id,
            history_turns=history_turns,
            images=images,
        )
    }
    if files_mapping:
        payload["files"] = dict(files_mapping)
    return payload


def _normalize_stream_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role in {"system", "tool"}:
        return role
    return ""


def _normalize_user_content_blocks(content: Any) -> str | list[dict[str, Any]] | None:
    if isinstance(content, str):
        text = content.strip()
        return text[:3000] if text else None
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return None

    blocks: list[dict[str, Any]] = []
    for item in list(content):
        if not isinstance(item, Mapping):
            continue
        block_type = str(item.get("type") or "").strip().lower()
        if block_type == "text":
            text = str(item.get("text") or "").strip()
            if text:
                blocks.append({"type": "text", "text": text[:3000]})
            continue
        if block_type != "image_url":
            continue
        image_url = item.get("image_url")
        url = ""
        if isinstance(image_url, str):
            url = image_url.strip()
        elif isinstance(image_url, Mapping):
            url = str(image_url.get("url") or "").strip()
        if not url.startswith("data:image/") or ";base64," not in url:
            continue
        if len(url) > MAX_IMAGE_DATA_URL_LENGTH:
            continue
        blocks.append({"type": "image_url", "image_url": {"url": url}})

    if not blocks:
        return None
    return blocks if len(blocks) > 1 else blocks[0].get("text") or blocks


def normalize_stream_messages(messages: Sequence[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in list(messages or [])[-MAX_STREAM_MESSAGES:]:
        if not isinstance(message, Mapping):
            continue
        role = _normalize_stream_role(message.get("role") or message.get("type"))
        if not role:
            continue

        content = message.get("content")
        normalized_content: Any = None
        if role == "user":
            normalized_content = _normalize_user_content_blocks(content)
        elif isinstance(content, str):
            text = content.strip()
            normalized_content = text[:3000] if text else None
        if normalized_content is None:
            continue

        row: dict[str, Any] = {
            "role": role,
            "content": normalized_content,
        }
        message_id = str(message.get("id") or "").strip()
        if message_id:
            row["id"] = message_id[:128]
        out.append(row)
    return out


def build_invoke_payload_from_messages(
    *,
    messages: Sequence[Any] | None,
    files_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messages": normalize_stream_messages(messages),
    }
    if files_mapping:
        payload["files"] = dict(files_mapping)
    return payload
