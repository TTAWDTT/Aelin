from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MAX_HISTORY_TURNS = 12
MAX_IMAGES = 4
MAX_IMAGE_DATA_URL_LENGTH = 3_000_000


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
