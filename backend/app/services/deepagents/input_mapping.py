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
        if role not in {"user", "assistant", "system"}:
            continue
        if not content:
            continue
        messages.append({"role": role, "content": content[:3000]})
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
    history_turns: Sequence[Any] | None = None,
    images: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in normalize_history_turns(history_turns)
    ]

    latest_query = str(query or "").strip()
    if not latest_query:
        return messages

    image_inputs = normalize_image_inputs(images)
    if not image_inputs:
        messages.append({"role": "user", "content": latest_query})
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
    messages.append(
        {
            "role": "user",
            "content": content_blocks if len(content_blocks) > 1 else latest_query,
        }
    )
    return messages


def build_invoke_payload(
    *,
    query: str,
    history_turns: Sequence[Any] | None = None,
    images: Sequence[Any] | None = None,
    files_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messages": build_chat_messages(
            query=query,
            history_turns=history_turns,
            images=images,
        )
    }
    if files_mapping:
        payload["files"] = dict(files_mapping)
    return payload
