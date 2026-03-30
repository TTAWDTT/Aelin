from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Callable, Awaitable

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from deepagents.middleware._utils import append_to_system_message


_LOG = logging.getLogger(__name__)


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


def _tool_name_preview(request: ModelRequest[Any], limit: int = 6) -> str:
    names: list[str] = []
    for tool in list(getattr(request, "tools", []) or []):
        name = str(getattr(tool, "name", "") or "").strip()
        if name:
            names.append(name)
    if not names:
        return ""
    preview = names[:limit]
    if len(names) > limit:
        preview.append(f"+{len(names) - limit} more")
    return ",".join(preview)


def _last_human_message_chars(request: ModelRequest[Any]) -> int:
    for message in reversed(list(getattr(request, "messages", []) or [])):
        if isinstance(message, HumanMessage):
            content = getattr(message, "content", "")
            return len(str(content or ""))
    return 0


def _format_timeout_seconds(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return str(rounded)


def _append_system_message_text(system_message: Any, text: str) -> SystemMessage:
    if isinstance(system_message, SystemMessage):
        return append_to_system_message(system_message, text)
    if system_message is None:
        return append_to_system_message(None, text)
    return append_to_system_message(
        SystemMessage(content=str(system_message or "")),
        text,
    )


class DeepAgentsModelTimeoutMiddleware(AgentMiddleware[Any, Any, Any]):
    """Enforce a hard wall-clock timeout around each async model node call."""

    def __init__(self, *, timeout_seconds: float) -> None:
        super().__init__()
        self.timeout_seconds = max(0.0, float(timeout_seconds or 0.0))

    def _timeout_message(self) -> AIMessage:
        timeout_label = _format_timeout_seconds(self.timeout_seconds)
        return AIMessage(
            content=(
                f"模型生成超时（{timeout_label}s）。"
                "本次运行已在模型完成下一步输出前被终止，可能仍停留在回复生成或工具参数生成阶段。"
                "请缩小任务范围后重试。"
            )
        )

    def _log_timeout(self, request: ModelRequest[Any], elapsed_ms: int) -> None:
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        _LOG.warning(
            (
                "deepagents_model_timeout "
                "elapsed_ms=%s timeout_seconds=%s model=%s user_id=%s workspace=%s "
                "message_count=%s tool_count=%s tool_names=%s last_human_chars=%s"
            ),
            elapsed_ms,
            _format_timeout_seconds(self.timeout_seconds),
            _model_name_from_request(request),
            _context_field(context, "user_id", 0),
            _context_field(context, "workspace", "default"),
            len(list(getattr(request, "messages", []) or [])),
            len(list(getattr(request, "tools", []) or [])),
            _tool_name_preview(request),
            _last_human_message_chars(request),
        )

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        # The production graph path is async (`astream` / `ainvoke`).
        # Keep the legacy sync bridge compatible without introducing thread-based
        # cancellation complexity here.
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        if self.timeout_seconds <= 0:
            return await handler(request)

        started = perf_counter()
        try:
            return await asyncio.wait_for(handler(request), timeout=self.timeout_seconds)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            elapsed_ms = int((perf_counter() - started) * 1000)
            self._log_timeout(request, elapsed_ms)
            return self._timeout_message()


class DeepAgentsToolAvailabilityMiddleware(AgentMiddleware[Any, Any, Any]):
    """Re-expose selected custom tools after DeepAgents builtin middleware mutates the tool list."""

    def __init__(self, *, preserved_tools: list[Any] | tuple[Any, ...]) -> None:
        super().__init__()
        self._preserved_tools = tuple(
            tool
            for tool in list(preserved_tools or [])
            if str(getattr(tool, "name", "") or "").strip()
        )

    @staticmethod
    def _tool_name(tool: Any) -> str:
        return str(getattr(tool, "name", "") or "").strip()

    def _availability_note(self, missing_names: list[str]) -> str:
        formatted = ", ".join(f"`{name}`" for name in missing_names)
        lines = [
            "Runtime note:",
            f"- The following custom tools are available in this run even if earlier filesystem instructions did not list them: {formatted}.",
            "- Do not claim these tools are unavailable unless a call in this run actually failed.",
        ]
        if "execute" in missing_names:
            lines.append(
                "- `execute` runs short, non-interactive local desktop commands via the Aelin runtime. Use it for tests, builds, inspections, and small file-generation commands."
            )
        return "\n".join(lines)

    def _restore_request(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        if not self._preserved_tools:
            return request

        current_tools = list(getattr(request, "tools", []) or [])
        existing_names = {
            self._tool_name(tool)
            for tool in current_tools
            if self._tool_name(tool)
        }
        missing_tools = [
            tool
            for tool in self._preserved_tools
            if self._tool_name(tool) and self._tool_name(tool) not in existing_names
        ]
        if not missing_tools:
            return request

        missing_names = [self._tool_name(tool) for tool in missing_tools]
        _LOG.warning(
            "deepagents_restore_custom_tools restored=%s tool_count_before=%s tool_count_after=%s",
            ",".join(missing_names),
            len(current_tools),
            len(current_tools) + len(missing_tools),
        )
        new_system_message = _append_system_message_text(
            request.system_message,
            self._availability_note(missing_names),
        )
        return request.override(
            tools=[*current_tools, *missing_tools],
            system_message=new_system_message,
        )

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        return handler(self._restore_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        return await handler(self._restore_request(request))


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
