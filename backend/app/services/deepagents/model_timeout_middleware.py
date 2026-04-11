from __future__ import annotations

import asyncio
import logging
import time
from time import perf_counter
from typing import Any, Awaitable, Callable, Generic, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

try:
    from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
except Exception:  # pragma: no cover - fallback for stripped test environments
    _RequestT = TypeVar("_RequestT")
    _ResponseT = TypeVar("_ResponseT")
    _StateT = TypeVar("_StateT")

    class ModelRequest(Generic[_RequestT]):
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

        def override(self, **kwargs: Any) -> "ModelRequest[Any]":
            payload = dict(getattr(self, "__dict__", {}))
            payload.update(kwargs)
            return ModelRequest(**payload)

    class ModelResponse(Generic[_ResponseT]):
        pass

    class AgentMiddleware(Generic[_RequestT, _ResponseT, _StateT]):
        def __init__(self) -> None:
            super().__init__()


_LOG = logging.getLogger(__name__)
_RETRYABLE_ERROR_FRAGMENTS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remoteprotocolerror",
    "server disconnected",
    "temporarily unavailable",
    "rate limit",
    "too many requests",
    "502",
    "503",
    "504",
    "transport",
    "connecterror",
    "readerror",
)


def _context_field(context: Any, key: str, default: Any = None) -> Any:
    if context is None:
        return default
    if isinstance(context, dict):
        return context.get(key, default)
    return getattr(context, key, default)


def _model_name_from_request(request: ModelRequest[Any]) -> str:
    model = getattr(request, "model", None)
    for attr in ("model_name", "model"):
        value = getattr(model, attr, None)
        if str(value or "").strip():
            return str(value)
    return type(model).__name__ if model is not None else "unknown"


def _format_timeout_seconds(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return str(rounded)


def _max_attempts(retry_attempts: int) -> int:
    return max(1, 1 + int(retry_attempts or 0))


def _backoff_seconds(base_seconds: float, *, attempt_index: int) -> float:
    return max(0.0, float(base_seconds or 0.0)) * max(1, int(attempt_index))


def _exception_name(exc: BaseException) -> str:
    return type(exc).__name__


def _is_retryable_model_exception(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.TimeoutError | TimeoutError):
        return True
    message = " ".join(
        [
            _exception_name(exc).lower(),
            str(exc or "").strip().lower(),
        ]
    )
    return any(fragment in message for fragment in _RETRYABLE_ERROR_FRAGMENTS)


class DeepAgentsModelTimeoutMiddleware(AgentMiddleware[Any, Any, Any]):
    """Retry transient model failures and enforce a hard async timeout per attempt."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        retry_attempts: int = 0,
        retry_backoff_seconds: float = 0.0,
    ) -> None:
        super().__init__()
        self.timeout_seconds = max(0.0, float(timeout_seconds or 0.0))
        self.retry_attempts = max(0, int(retry_attempts or 0))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds or 0.0))

    def _timeout_message(self) -> AIMessage:
        timeout_label = _format_timeout_seconds(self.timeout_seconds)
        return AIMessage(
            content=(
                f"\u6a21\u578b\u751f\u6210\u8d85\u65f6\uff08{timeout_label}s\uff09\u3002"
                "\u672c\u6b21\u8fd0\u884c\u5df2\u5728\u6a21\u578b\u8f93\u51fa\u5b8c\u6210\u524d\u88ab\u7ec8\u6b62\uff0c"
                "\u8bf7\u7f29\u5c0f\u4efb\u52a1\u8303\u56f4\u540e\u91cd\u8bd5\u3002"
            )
        )

    def _transient_failure_message(self, exc: BaseException) -> AIMessage:
        error_name = _exception_name(exc)
        return AIMessage(
            content=(
                "\u6a21\u578b\u8c03\u7528\u5728\u591a\u6b21\u91cd\u8bd5\u540e\u4ecd\u5931\u8d25\u3002"
                f"\u6700\u540e\u4e00\u6b21\u9519\u8bef\uff1a{error_name}\u3002"
                "\u8bf7\u7a0d\u540e\u518d\u8bd5\uff0c\u6216\u7f29\u5c0f\u672c\u6b21\u8bf7\u6c42\u3002"
            )
        )

    def _log_timeout(self, request: ModelRequest[Any], *, elapsed_ms: int, attempts: int) -> None:
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        _LOG.warning(
            (
                "deepagents_model_timeout "
                "elapsed_ms=%s timeout_seconds=%s attempts=%s model=%s user_id=%s workspace=%s "
                "message_count=%s tool_count=%s"
            ),
            elapsed_ms,
            _format_timeout_seconds(self.timeout_seconds),
            attempts,
            _model_name_from_request(request),
            _context_field(context, "user_id", 0),
            _context_field(context, "workspace", "default"),
            len(list(getattr(request, "messages", []) or [])),
            len(list(getattr(request, "tools", []) or [])),
        )

    def _log_retry(
        self,
        request: ModelRequest[Any],
        *,
        attempt_number: int,
        max_attempts: int,
        reason: str,
        elapsed_ms: int,
        backoff_seconds: float,
    ) -> None:
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        _LOG.warning(
            (
                "deepagents_model_retry "
                "attempt=%s max_attempts=%s reason=%s elapsed_ms=%s backoff_seconds=%s "
                "model=%s user_id=%s workspace=%s"
            ),
            attempt_number,
            max_attempts,
            reason,
            elapsed_ms,
            round(backoff_seconds, 3),
            _model_name_from_request(request),
            _context_field(context, "user_id", 0),
            _context_field(context, "workspace", "default"),
        )

    def _sleep_backoff(self, *, attempt_number: int) -> None:
        delay = _backoff_seconds(self.retry_backoff_seconds, attempt_index=attempt_number)
        if delay > 0:
            time.sleep(delay)

    async def _asleep_backoff(self, *, attempt_number: int) -> None:
        delay = _backoff_seconds(self.retry_backoff_seconds, attempt_index=attempt_number)
        if delay > 0:
            await asyncio.sleep(delay)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        max_attempts = _max_attempts(self.retry_attempts)
        last_retryable_error: Exception | None = None

        for attempt_number in range(1, max_attempts + 1):
            started = perf_counter()
            try:
                return handler(request)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable_model_exception(exc):
                    raise
                last_retryable_error = exc
                elapsed_ms = int((perf_counter() - started) * 1000)
                if attempt_number >= max_attempts:
                    break
                self._log_retry(
                    request,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                    reason=_exception_name(exc),
                    elapsed_ms=elapsed_ms,
                    backoff_seconds=_backoff_seconds(
                        self.retry_backoff_seconds,
                        attempt_index=attempt_number,
                    ),
                )
                self._sleep_backoff(attempt_number=attempt_number)

        if isinstance(last_retryable_error, asyncio.TimeoutError | TimeoutError):
            self._log_timeout(
                request,
                elapsed_ms=0,
                attempts=max_attempts,
            )
            return self._timeout_message()
        if last_retryable_error is not None:
            return self._transient_failure_message(last_retryable_error)
        return self._timeout_message()

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        max_attempts = _max_attempts(self.retry_attempts)
        last_retryable_error: Exception | None = None

        for attempt_number in range(1, max_attempts + 1):
            started = perf_counter()
            try:
                if self.timeout_seconds <= 0:
                    return await handler(request)
                return await asyncio.wait_for(handler(request), timeout=self.timeout_seconds)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError as exc:
                last_retryable_error = exc
                elapsed_ms = int((perf_counter() - started) * 1000)
                if attempt_number >= max_attempts:
                    self._log_timeout(
                        request,
                        elapsed_ms=elapsed_ms,
                        attempts=max_attempts,
                    )
                    return self._timeout_message()
                self._log_retry(
                    request,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                    reason="timeout",
                    elapsed_ms=elapsed_ms,
                    backoff_seconds=_backoff_seconds(
                        self.retry_backoff_seconds,
                        attempt_index=attempt_number,
                    ),
                )
                await self._asleep_backoff(attempt_number=attempt_number)
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable_model_exception(exc):
                    raise
                last_retryable_error = exc
                elapsed_ms = int((perf_counter() - started) * 1000)
                if attempt_number >= max_attempts:
                    break
                self._log_retry(
                    request,
                    attempt_number=attempt_number,
                    max_attempts=max_attempts,
                    reason=_exception_name(exc),
                    elapsed_ms=elapsed_ms,
                    backoff_seconds=_backoff_seconds(
                        self.retry_backoff_seconds,
                        attempt_index=attempt_number,
                    ),
                )
                await self._asleep_backoff(attempt_number=attempt_number)

        if isinstance(last_retryable_error, asyncio.TimeoutError | TimeoutError):
            self._log_timeout(
                request,
                elapsed_ms=0,
                attempts=max_attempts,
            )
            return self._timeout_message()
        if last_retryable_error is not None:
            return self._transient_failure_message(last_retryable_error)
        return self._timeout_message()


def _infer_tool_name(message: ToolMessage) -> str:
    explicit_name = str(getattr(message, "name", "") or "").strip()
    if explicit_name:
        return explicit_name
    tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
    if ":" in tool_call_id:
        prefix = tool_call_id.split(":", 1)[0].strip()
        if prefix:
            return prefix
    return "unknown_tool"


def sanitize_orphan_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    sanitized: list[BaseMessage] = []
    seen_tool_call_ids: set[str] = set()

    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in list(getattr(message, "tool_calls", []) or []):
                tool_call_id = str(tool_call.get("id") or "").strip()
                if tool_call_id:
                    seen_tool_call_ids.add(tool_call_id)
            sanitized.append(message)
            continue

        if isinstance(message, ToolMessage):
            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if tool_call_id and tool_call_id not in seen_tool_call_ids:
                tool_name = _infer_tool_name(message)
                sanitized.append(
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": tool_call_id,
                                "name": tool_name,
                                "args": {},
                                "type": "tool_call",
                            }
                        ],
                    )
                )
                _LOG.warning(
                    "deepagents_orphan_tool_message_patched tool_call_id=%s tool_name=%s",
                    tool_call_id,
                    tool_name,
                )
                seen_tool_call_ids.add(tool_call_id)
            sanitized.append(message)
            continue

        sanitized.append(message)

    return sanitized


class DeepAgentsToolMessageSanitizerMiddleware(AgentMiddleware[Any, Any, Any]):
    """Patch orphan ToolMessages before sending history to OpenAI-compatible providers."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        sanitized_messages = sanitize_orphan_tool_messages(list(getattr(request, "messages", []) or []))
        return handler(request.override(messages=sanitized_messages))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        sanitized_messages = sanitize_orphan_tool_messages(list(getattr(request, "messages", []) or []))
        return await handler(request.override(messages=sanitized_messages))
