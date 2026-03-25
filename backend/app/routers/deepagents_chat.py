from __future__ import annotations

from datetime import datetime, timezone
import logging
import queue
import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import ChatRequest
from app.services.aelin.runtime import (
    normalize_workspace as _normalize_workspace,
    resolve_llm_service as _resolve_llm_service,
)
from app.services.aelin.streaming import _now_ms, _sse_event
from app.services.aelin.utils import normalize_positive_ints
from app.services.aelin.core_support import (
    _get_agents_memory_text_for_chat,
    _scoped_web_search_service,
)
from app.services.deepagents.deepagents_graph import build_chat_agent
from app.services.deepagents.input_mapping import (
    build_invoke_payload,
    normalize_history_turns,
    normalize_image_inputs,
)
from app.services.deepagents.output_utils import extract_answer, message_to_text
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    build_tool_runtime_context,
)
from app.settings import settings


router = APIRouter(prefix="/deepagents", tags=["deepagents"])
_LOG = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    try:
        return jsonable_encoder(value)
    except Exception:
        pass

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    for attr in ("model_dump", "dict"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return _json_safe(method())
            except Exception:
                pass

    message_type = getattr(value, "type", None)
    if hasattr(value, "content") or message_type:
        payload: dict[str, Any] = {}
        if message_type:
            payload["message_type"] = str(message_type)
        content = message_to_text(value)
        if content:
            payload["content"] = content
        for extra_key in ("tool_calls", "additional_kwargs", "response_metadata"):
            extra_value = getattr(value, extra_key, None)
            if extra_value:
                payload[extra_key] = _json_safe(extra_value)
        if payload:
            return payload

    return str(value)


def _message_chunk_parts(data: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(data, (tuple, list)) and len(data) == 2:
        message, metadata = data
        if isinstance(metadata, dict):
            return message, metadata
        return message, {}
    return data, {}


def _extract_message_delta(data: Any) -> str:
    if isinstance(data, (tuple, list)) and len(data) == 2:
        message, metadata = _message_chunk_parts(data)
        if isinstance(metadata, dict):
            node_name = str(metadata.get("langgraph_node") or "").strip().lower()
            if node_name != "model":
                return ""
        return message_to_text(message).strip()
    return message_to_text(data).strip()


def _serialize_stream_part(chunk: Any) -> tuple[str, Any, list[str]] | None:
    if not isinstance(chunk, dict):
        return None

    event_type = str(chunk.get("type") or "").strip().lower()
    if not event_type:
        return None

    ns_raw = chunk.get("ns") or ()
    ns = [str(item) for item in ns_raw] if isinstance(ns_raw, (list, tuple)) else []
    data = chunk.get("data")

    if event_type == "messages":
        message, metadata = _message_chunk_parts(data)
        return (
            event_type,
            {
                "content": message_to_text(message),
                "metadata": _json_safe(metadata),
                "message": _json_safe(message),
            },
            ns,
        )

    return (
        event_type,
        _json_safe(data),
        ns,
    )


@router.post("/chat/stream")
def deepagents_chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    DeepAgents-native streaming endpoint.

    用稳定的 SSE 事件包装 DeepAgents / LangGraph 的 streaming 输出。

    路由层只负责认证、workspace/provider 归一化以及 SSE 包装，
    不再承担旧聊天壳的 trace/stop-reason 翻译职责。
    """

    def _event_iter():
        req_id = uuid4().hex[:10]
        started = _now_ms()
        heartbeat_count = 0
        event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        done_token = "__done__"
        event_seq = 0
        event_seq_lock = threading.Lock()

        class _CancelToken:
            cancelled: bool = False

        cancel_token = _CancelToken()

        def _envelope(
            event: str,
            data: Any = None,
            *,
            ns: list[str] | None = None,
        ) -> dict[str, Any]:
            nonlocal event_seq
            with event_seq_lock:
                event_seq += 1
                seq = event_seq
            payload: dict[str, Any] = {
                "type": event,
                "run_id": req_id,
                "seq": seq,
                "ts": _now_ms(),
            }
            if ns:
                payload["ns"] = [str(item) for item in ns]
            if data is not None:
                payload["data"] = _json_safe(data)
            return payload

        def _push(event: str, data: Any = None, *, ns: list[str] | None = None) -> None:
            payload = _envelope(event, data, ns=ns)
            _LOG.debug(
                "deepagents_stream event req=%s uid=%s event=%s keys=%s",
                req_id,
                int(current_user.id),
                str(event),
                ",".join(
                    sorted([str(k) for k in list(payload.keys())[:8] if str(k)])
                )
                or "-",
            )
            event_queue.put((event, payload))

        def _worker() -> None:
            try:
                source = str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32]
                workspace = _normalize_workspace(payload.workspace)
                query_preview = " ".join(str(payload.query or "").split())[:120]

                _LOG.info(
                    "deepagents_stream worker_start req=%s uid=%s source=%s workspace=%s query=%s",
                    req_id,
                    int(current_user.id),
                    source,
                    workspace,
                    query_preview,
                )

                # 为 DeepAgents 构造 LLM 服务与工具运行时上下文。
                service, provider = _resolve_llm_service(db, current_user)
                if provider == "rule_based" or not service.is_configured():
                    _push(
                        "error",
                        {
                            "message": "llm_not_configured",
                            "provider": provider,
                        },
                    )
                    return

                agents_memory_text = _get_agents_memory_text_for_chat(
                    db,
                    current_user.id,
                    workspace=workspace,
                )
                history_turns = normalize_history_turns(getattr(payload, "history", []))
                images = normalize_image_inputs(getattr(payload, "images", []))

                attachment_ids = normalize_positive_ints(
                    getattr(payload, "attachment_ids", []),
                    cap=20,
                )

                tool_context = build_tool_runtime_context(
                    db=db,
                    user_id=current_user.id,
                    workspace=workspace,
                    web_search_service=_scoped_web_search_service(
                        getattr(service.config, "web_search_proxy_url", ""),
                    ),
                    available_attachment_ids=attachment_ids,
                )

                allow_write_tools = bool(
                    getattr(settings, "deepagents_allow_write_tools", False)
                )
                limiter = ToolCallLimiter(
                    max_tool_calls=int(
                        getattr(settings, "deepagents_max_tool_calls", 512) or 512
                    ),
                    max_write_calls=int(
                        getattr(settings, "deepagents_max_write_calls", 128) or 128
                    ),
                allow_write_tools=allow_write_tools,
                )

                agent, usage, tool_runs, files_mapping = build_chat_agent(
                    service=service,
                    provider=provider,
                    context=tool_context,
                    limiter=limiter,
                    memory_text=agents_memory_text,
                    cancel_token=cancel_token,
                )
                if agent is None:
                    _push(
                        "error",
                        {
                            "message": "llm_not_configured",
                            "provider": provider,
                        },
                    )
                    return

                # 构造 DeepAgents 期望的消息格式。
                invoke_payload = build_invoke_payload(
                    query=payload.query,
                    history_turns=history_turns,
                    images=images,
                    files_mapping=files_mapping,
                )

                streamed_text_parts: list[str] = []
                final_answer = ""

                for chunk in agent.stream(
                    invoke_payload,
                    stream_mode=["messages", "updates", "tasks", "values"],
                    version="v2",
                    subgraphs=True,
                ):
                    if is_cancelled(cancel_token):
                        break

                    serialized = _serialize_stream_part(chunk)
                    if serialized is not None:
                        event_name, event_data, event_ns = serialized
                        _push(event_name, event_data, ns=event_ns)

                    if not isinstance(chunk, dict):
                        continue

                    mode = str(chunk.get("type") or "").strip().lower()
                    data = chunk.get("data")

                    if mode == "messages":
                        delta = _extract_message_delta(data)
                        if delta:
                            streamed_text_parts.append(delta)
                        continue

                    if mode == "values":
                        candidate = extract_answer(data).strip()
                        if candidate:
                            final_answer = candidate
                        continue

                    candidate = extract_answer(data).strip()
                    if candidate:
                        final_answer = candidate

                if not final_answer:
                    final_answer = "".join(streamed_text_parts).strip()

                _push(
                    "final",
                    {
                        "answer": final_answer,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "usage": {
                            "total_calls": int(getattr(usage, "total_calls", 0) or 0),
                            "write_calls": int(getattr(usage, "write_calls", 0) or 0),
                        },
                    },
                )
            except Exception as exc:  # noqa: BLE001
                _LOG.exception(
                    "deepagents_stream worker_error req=%s uid=%s error=%s",
                    req_id,
                    int(current_user.id),
                    str(exc)[:220],
                )
                _push(
                    "error",
                    {
                        "message": str(exc)[:500] or "deepagents stream error",
                    },
                )
            finally:
                _push("done", {"status": done_token})
                _LOG.info(
                    "deepagents_stream worker_done req=%s uid=%s duration_ms=%s",
                    req_id,
                    int(current_user.id),
                    max(0, _now_ms() - started),
                )

        # 先发送一个 start 事件，方便前端初始化上下文。
        _push(
            "start",
            {
                "query": payload.query.strip()[:180],
                "source": str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
                "workspace": payload.workspace,
            },
        )

        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()

        heartbeat_interval_s = 5.0
        try:
            while True:
                try:
                    event, data = event_queue.get(timeout=heartbeat_interval_s)
                except queue.Empty:
                    heartbeat_count += 1
                    yield _sse_event("ping", _envelope("ping", {"hb": heartbeat_count}))
                    if (not worker.is_alive()) and event_queue.empty():
                        yield _sse_event("done", _envelope("done", {"status": done_token}))
                        break
                    continue

                yield _sse_event(event, data)
                if event == "done":
                    break
        except BaseException as exc:  # noqa: BLE001
            cancel_token.cancelled = True
            _LOG.warning(
                "deepagents_stream interrupted req=%s uid=%s type=%s msg=%s",
                req_id,
                int(current_user.id),
                type(exc).__name__,
                str(exc)[:180],
            )
            raise
        finally:
            _LOG.info(
                "deepagents_stream closed req=%s uid=%s duration_ms=%s heartbeats=%s",
                req_id,
                int(current_user.id),
                max(0, _now_ms() - started),
                heartbeat_count,
            )

    return StreamingResponse(
        _event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
