from __future__ import annotations

from typing import Any

from langgraph_sdk.runtime import ServerRuntime

from app.services.deepagents.run_context import DeepAgentsRunContext


def _coerce_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def runtime_user_id(
    runtime: ServerRuntime[DeepAgentsRunContext],
    context: DeepAgentsRunContext | dict[str, Any] | None,
) -> int:
    user = getattr(runtime, "user", None)
    candidates: list[Any] = []
    if user is not None:
        for key in ("user_id", "id"):
            try:
                if key in user:
                    candidates.append(user[key])
            except Exception:
                pass
            candidates.append(getattr(user, key, None))
        candidates.append(getattr(user, "identity", None))
    if context is not None:
        candidates.append(getattr(context, "user_id", None))
    for value in candidates:
        user_id = _coerce_positive_int(value)
        if user_id > 0:
            return user_id
    return 0


def context_value(
    context: DeepAgentsRunContext | dict[str, Any] | None,
    key: str,
    default: Any,
) -> Any:
    if context is None:
        return default
    if isinstance(context, dict):
        return context.get(key, default)
    try:
        return getattr(context, key)
    except Exception:
        return default


_runtime_user_id = runtime_user_id
_context_value = context_value
