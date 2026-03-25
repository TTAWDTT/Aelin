from __future__ import annotations

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
from app.services.deepagents.output_utils import message_to_text
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.tool_runtime import (
    ToolCallLimiter,
    build_tool_runtime_context,
)
from app.settings import settings


router = APIRouter(prefix="/deepagents", tags=["deepagents"])
_LOG = logging.getLogger(__name__)


def _compact_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}…"


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summarize_scalar(value: Any, limit: int = 220) -> Any:
    if isinstance(value, str):
        return _compact_text(value, limit)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return None


def _summarize_unknown(value: Any, depth: int = 0) -> Any:
    scalar = _summarize_scalar(value)
    if scalar is not None:
        return scalar

    if depth >= 2:
        if isinstance(value, list):
            return f"items={len(value)}"
        if isinstance(value, dict):
            return f"keys={len(value)}"
        return _compact_text(value, 120)

    if isinstance(value, list):
        return [_summarize_unknown(item, depth + 1) for item in value[:4]]

    record = _as_record(value)
    if record:
        out: dict[str, Any] = {}
        for key in list(record.keys())[:8]:
            out[str(key)] = _summarize_unknown(record.get(key), depth + 1)
        if len(record) > 8:
            out["__truncated"] = True
        return out

    return _compact_text(value, 120)


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


def _normalize_message_type(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.endswith("messagechunk"):
        lowered = lowered[: -len("messagechunk")]
    if lowered.endswith("message"):
        lowered = lowered[: -len("message")]
    if lowered == "human":
        return "human"
    if lowered == "user":
        return "human"
    if lowered == "ai":
        return "ai"
    if lowered == "assistant":
        return "ai"
    if lowered in {"system", "tool", "function", "remove"}:
        return lowered
    return lowered


def _serialize_langgraph_message(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        payload = {str(k): _json_safe(v) for k, v in value.items()}
        message_type = _normalize_message_type(payload.get("type"))
        if message_type:
            payload["type"] = message_type
        return payload

    message_type = _normalize_message_type(getattr(value, "type", None))
    payload: dict[str, Any] = {}
    if message_type:
        payload["type"] = message_type

    message_id = getattr(value, "id", None)
    if message_id:
        payload["id"] = str(message_id)

    name = getattr(value, "name", None)
    if name:
        payload["name"] = str(name)

    content = getattr(value, "content", None)
    if content is not None:
        payload["content"] = _json_safe(content)

    additional_kwargs = getattr(value, "additional_kwargs", None)
    if additional_kwargs:
        payload["additional_kwargs"] = _json_safe(additional_kwargs)

    response_metadata = getattr(value, "response_metadata", None)
    if response_metadata:
        payload["response_metadata"] = _json_safe(response_metadata)

    usage_metadata = getattr(value, "usage_metadata", None)
    if usage_metadata:
        payload["usage_metadata"] = _json_safe(usage_metadata)

    tool_calls = getattr(value, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = _json_safe(tool_calls)

    invalid_tool_calls = getattr(value, "invalid_tool_calls", None)
    if invalid_tool_calls:
        payload["invalid_tool_calls"] = _json_safe(invalid_tool_calls)

    tool_call_id = getattr(value, "tool_call_id", None)
    if tool_call_id:
        payload["tool_call_id"] = str(tool_call_id)

    status = getattr(value, "status", None)
    if status:
        payload["status"] = str(status)

    return payload


def _message_chunk_parts(data: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(data, (tuple, list)) and len(data) == 2:
        message, metadata = data
        if isinstance(metadata, dict):
            return message, metadata
        return message, {}
    return data, {}


def _summarize_tool_call(value: Any) -> dict[str, Any]:
    record = _as_record(value)
    if not record:
        return {}
    out: dict[str, Any] = {}
    name = _compact_text(record.get("name"), 80)
    if name:
        out["name"] = name
    call_id = _compact_text(record.get("id"), 120)
    if call_id:
        out["id"] = call_id
    args = record.get("args")
    if isinstance(args, dict) and args:
        out["args"] = _summarize_unknown(args, 1)
    return out


def _extract_task_tool_info(data: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {}

    input_record = _as_record(data.get("input"))
    tool_call = _as_record(input_record.get("tool_call"))
    if tool_call:
        tool = _summarize_tool_call(tool_call)
        if tool:
            info["tool_call"] = tool
            if tool.get("name"):
                info["tool_name"] = tool["name"]
        return info

    result_record = _as_record(data.get("result"))
    messages = result_record.get("messages")
    if not isinstance(messages, list):
        return info

    for message in messages:
        message_record = _as_record(message)
        tool_calls = message_record.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue
        summarized = [
            tool
            for tool in (_summarize_tool_call(item) for item in tool_calls)
            if tool
        ]
        if summarized:
            info["tool_calls"] = summarized
            first = summarized[0]
            if first.get("name"):
                info["tool_name"] = first["name"]
            return info

    return info


def _summarize_task_payload(data: Any) -> dict[str, Any]:
    record = _as_record(data)
    if not record:
        return {}

    out: dict[str, Any] = {}
    for key in ("id", "name", "status"):
        value = _summarize_scalar(record.get(key), 120)
        if value not in (None, ""):
            out[key] = value

    interrupts = record.get("interrupts")
    if isinstance(interrupts, list):
        out["interrupts"] = len(interrupts)

    triggers = record.get("triggers")
    if isinstance(triggers, list):
        out["triggers"] = len(triggers)

    error = record.get("error")
    if error is not None:
        out["error"] = _summarize_unknown(error, 0)

    out.update(_extract_task_tool_info(record))

    result_record = _as_record(record.get("result"))
    if result_record:
        summary_bits: list[str] = []
        ok = result_record.get("ok")
        if isinstance(ok, bool):
            summary_bits.append("ok" if ok else "failed")
        total = result_record.get("total")
        if isinstance(total, int):
            summary_bits.append(f"total={total}")
        query = _compact_text(result_record.get("query"), 120)
        if query:
            summary_bits.append(f"query={query}")
        summary = _compact_text(" · ".join(summary_bits), 220)
        if summary:
            out["result_summary"] = summary

    return out


def _summarize_values_payload(data: Any) -> dict[str, Any]:
    record = _as_record(data)
    if not record:
        return {}

    todos = record.get("todos")
    todos_list = todos if isinstance(todos, list) else []
    messages = record.get("messages")
    messages_list = messages if isinstance(messages, list) else []
    answer = ""
    for message in reversed(messages_list):
        message_record = _as_record(message)
        role = str(
            message_record.get("role")
            or message_record.get("type")
            or ""
        ).strip().lower()
        if role not in {"assistant", "ai"}:
            continue
        text = _compact_text(message_to_text(message_record), 800)
        if text:
            answer = text
            break

    out: dict[str, Any] = {
        "messages_count": len(messages_list),
        "todos_count": len(todos_list),
    }
    if answer:
        out["answer"] = answer
    if todos_list:
        out["todos"] = [_summarize_unknown(item, 1) for item in todos_list[:6]]
    plan = record.get("plan")
    if plan is not None:
        out["plan"] = _summarize_unknown(plan, 0)
    return out


def _summarize_updates_payload(data: Any) -> dict[str, Any]:
    summary = _summarize_unknown(data, 0)
    if isinstance(summary, dict):
        return summary
    return {"summary": summary}


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
        metadata_payload = _json_safe(metadata)
        metadata_record = (
            metadata_payload if isinstance(metadata_payload, dict) else {}
        )
        if ns:
            checkpoint_ns = "|".join(ns)
            metadata_record.setdefault("langgraph_checkpoint_ns", checkpoint_ns)
            metadata_record.setdefault("checkpoint_ns", checkpoint_ns)
        return (
            event_type,
            [_serialize_langgraph_message(message), metadata_record],
            ns,
        )

    if event_type == "tasks":
        return (event_type, _summarize_task_payload(data), ns)

    if event_type == "values":
        return (event_type, _summarize_values_payload(data), ns)

    if event_type == "updates":
        return (event_type, _summarize_updates_payload(data), ns)

    return (
        event_type,
        _json_safe(data),
        ns,
    )


def _classify_topology_node(node_id: str, name: str) -> str:
    node_id_norm = str(node_id or "").strip().lower()
    name_norm = str(name or "").strip().lower()
    if node_id_norm == "__start__":
        return "start"
    if node_id_norm == "__end__":
        return "end"
    if name_norm == "model":
        return "model"
    if name_norm == "tools":
        return "tools"
    if "middleware" in name_norm:
        return "middleware"
    return "node"


def _serialize_agent_topology(agent: Any) -> dict[str, Any] | None:
    get_graph = getattr(agent, "get_graph", None)
    if not callable(get_graph):
        return None

    try:
        graph = get_graph()
    except Exception:
        return None

    raw_nodes = getattr(graph, "nodes", None)
    raw_edges = getattr(graph, "edges", None)
    if not isinstance(raw_nodes, dict) or not isinstance(raw_edges, list):
        return None

    nodes: list[dict[str, Any]] = []
    for node_id, node in raw_nodes.items():
        safe_id = str(node_id or "").strip()
        if not safe_id:
            continue
        name = str(getattr(node, "name", None) or safe_id).strip() or safe_id
        nodes.append(
            {
                "id": safe_id,
                "name": name,
                "kind": _classify_topology_node(safe_id, name),
            }
        )

    edges: list[dict[str, Any]] = []
    for edge in raw_edges:
        source = str(getattr(edge, "source", "") or "").strip()
        target = str(getattr(edge, "target", "") or "").strip()
        if not source or not target:
            continue
        edges.append(
            {
                "source": source,
                "target": target,
                "conditional": bool(getattr(edge, "conditional", False)),
            }
        )

    if not nodes:
        return None

    mermaid = ""
    draw_mermaid = getattr(graph, "draw_mermaid", None)
    if callable(draw_mermaid):
        try:
            mermaid = str(draw_mermaid() or "")
        except Exception:
            mermaid = ""

    payload: dict[str, Any] = {
        "nodes": nodes,
        "edges": edges,
    }
    if mermaid:
        payload["mermaid"] = mermaid
    return payload


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
        event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        done_token = "__done__"

        class _CancelToken:
            cancelled: bool = False

        cancel_token = _CancelToken()

        def _event_name(event: str, ns: list[str] | None = None) -> str:
            clean_ns = [str(item) for item in (ns or []) if str(item)]
            return f"{event}|{'|'.join(clean_ns)}" if clean_ns else event

        def _push(event: str, data: Any = None, *, ns: list[str] | None = None) -> None:
            event_name = _event_name(event, ns)
            payload = _json_safe(data) if data is not None else {}
            _LOG.debug(
                "deepagents_stream event req=%s uid=%s event=%s keys=%s",
                req_id,
                int(current_user.id),
                event_name,
                ",".join(
                    sorted([str(k) for k in list(payload.keys())[:8] if str(k)])
                    if isinstance(payload, dict)
                    else []
                )
                or "-",
            )
            event_queue.put((event_name, payload))

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

                _push("metadata", {"run_id": req_id})

                topology = _serialize_agent_topology(agent)
                if topology is not None:
                    _push("custom", {"kind": "topology", "topology": topology})

                # 构造 DeepAgents 期望的消息格式。
                invoke_payload = build_invoke_payload(
                    query=payload.query,
                    history_turns=history_turns,
                    images=images,
                    files_mapping=files_mapping,
                )

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
                    yield _sse_event("ping", {"hb": heartbeat_count})
                    if (not worker.is_alive()) and event_queue.empty():
                        yield _sse_event("done", {"status": done_token})
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
