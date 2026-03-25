from __future__ import annotations

from typing import Any


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = content_to_text(item)
            if text:
                parts.append(text)
        return "".join(parts)

    if isinstance(content, dict):
        for key in ("text", "content", "value"):
            if key not in content:
                continue
            value = content.get(key)
            if isinstance(value, str):
                return value
            nested = content_to_text(value)
            if nested:
                return nested

    return ""


def message_to_text(message: Any) -> str:
    try:
        text_attr = getattr(message, "text", None)
        if isinstance(text_attr, str) and text_attr:
            return text_attr
        if callable(text_attr):
            text_value = text_attr()
            if isinstance(text_value, str) and text_value:
                return text_value
    except Exception:
        pass

    if hasattr(message, "content"):
        return content_to_text(getattr(message, "content", ""))

    if isinstance(message, dict):
        if "content" in message:
            return content_to_text(message.get("content"))
        if "text" in message:
            return str(message.get("text") or "")

    return ""


def extract_answer(response: Any) -> str:
    try:
        text = message_to_text(response)
        if text:
            return text

        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            for key in ("answer", "output", "content"):
                if key not in response:
                    continue
                value_text = content_to_text(response.get(key))
                if value_text:
                    return value_text

            messages = response.get("messages") or []
            if isinstance(messages, list) and messages:
                return message_to_text(messages[-1])

            return ""

        return str(response or "")
    except Exception:
        return ""
