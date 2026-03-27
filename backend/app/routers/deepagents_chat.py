from __future__ import annotations

from dataclasses import dataclass
import logging
import queue
import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.db import create_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import ChatRequest
from app.services.aelin.streaming import _now_ms, _sse_event
from app.services.deepagents.deepagents_graph import build_chat_agent
from app.services.deepagents.input_mapping import (
    build_invoke_payload,
    build_invoke_payload_from_messages,
    normalize_history_turns,
    normalize_image_inputs,
    normalize_stream_messages,
)
from app.services.deepagents.output_utils import message_to_text
from app.services.deepagents.cancel_utils import is_cancelled
from app.services.deepagents.runtime_resolver import (
    resolve_deepagents_runtime,
)
from app.settings import settings


router = APIRouter(prefix="/deepagents", tags=["deepagents"])
_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class ParsedDeepAgentsStreamRequest:
    source: str
    workspace: str
    attachment_ids: list[int]
    query_preview: str
    invoke_messages: list[dict[str, Any]] | None = None
    query: str = ""
    query_message_id: str = ""
    history_turns: list[dict[str, str]] | None = None
    images: list[dict[str, str]] | None = None


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _sanitize_tool_call(value: Any) -> dict[str, Any] | None:
    record = _as_record(_json_safe(value))
    if not record:
        return None
    tool_id = str(record.get("id") or "").strip()
    name = str(record.get("name") or "").strip()
    args = record.get("args")
    if not tool_id or not name:
        return None
    if isinstance(args, dict) and not args:
        return None
    if isinstance(args, str):
        text = args.strip().lower()
        if not text or text in {"{}", "[]", "null"}:
            return None
    return record


def _sanitize_message_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    safe = {str(key): val for key, val in payload.items()}
    tool_calls_raw = safe.get("tool_calls")
    if isinstance(tool_calls_raw, list):
        cleaned_tool_calls = [
            item
            for raw in tool_calls_raw
            if (item := _sanitize_tool_call(raw)) is not None
        ]
        if cleaned_tool_calls:
            safe["tool_calls"] = cleaned_tool_calls
        else:
            safe.pop("tool_calls", None)

    invalid_tool_calls_raw = safe.get("invalid_tool_calls")
    if isinstance(invalid_tool_calls_raw, list):
        cleaned_invalid_tool_calls = [
            item
            for raw in invalid_tool_calls_raw
            if (item := _as_record(_json_safe(raw))) and str(item.get("name") or "").strip()
        ]
        if cleaned_invalid_tool_calls:
            safe["invalid_tool_calls"] = cleaned_invalid_tool_calls
        else:
            safe.pop("invalid_tool_calls", None)

    message_type = _normalize_message_type(safe.get("type"))
    content = message_to_text(safe)
    if message_type == "ai" and not content.strip() and not safe.get("tool_calls"):
        return None
    return safe


def _message_chunk_parts(data: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(data, (tuple, list)) and len(data) == 2:
        message, metadata = data
        if isinstance(metadata, dict):
            return message, metadata
        return message, {}
    return data, {}


def _strip_files_payload(value: Any) -> Any:
    payload = _json_safe(value)
    if isinstance(payload, dict) and "files" in payload:
        payload = {key: val for key, val in payload.items() if str(key) != "files"}
    return payload


def _normalize_attachment_ids(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for raw in value[:20]:
        try:
            parsed = int(raw)
        except Exception:
            continue
        if parsed <= 0 or parsed in out:
            continue
        out.append(parsed)
    return out


def _preview_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        preview = " ".join(message_to_text(message).split())[:120]
        if preview:
            return preview
    return ""


def _parse_stream_request(raw_payload: Any) -> ParsedDeepAgentsStreamRequest:
    payload_record = _as_record(raw_payload)
    input_record = _as_record(payload_record.get("input"))
    context_record = _as_record(payload_record.get("context"))

    if isinstance(input_record.get("messages"), list):
        invoke_messages = normalize_stream_messages(input_record.get("messages"))
        workspace = str(context_record.get("workspace") or "default").strip() or "default"
        source = str(context_record.get("source") or "chat_ui").strip().lower()[:32] or "chat_ui"
        attachment_ids = _normalize_attachment_ids(context_record.get("attachment_ids"))
        return ParsedDeepAgentsStreamRequest(
            source=source,
            workspace=workspace,
            attachment_ids=attachment_ids,
            query_preview=_preview_from_messages(invoke_messages),
            invoke_messages=invoke_messages,
        )

    payload = ChatRequest.model_validate(payload_record)
    history_turns = normalize_history_turns(getattr(payload, "history", []))
    images = normalize_image_inputs(getattr(payload, "images", []))
    return ParsedDeepAgentsStreamRequest(
        source=str(getattr(payload, "source", "chat_ui") or "chat_ui")[:32],
        workspace=str(getattr(payload, "workspace", "default") or "default"),
        attachment_ids=list(getattr(payload, "attachment_ids", []) or []),
        query_preview=" ".join(str(payload.query or "").split())[:120],
        query=str(payload.query or ""),
        query_message_id=str(getattr(payload, "query_message_id", "") or ""),
        history_turns=history_turns,
        images=images,
    )


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
        message_payload = _sanitize_message_payload(_serialize_langgraph_message(message))
        if message_payload is None:
            return None
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
            [message_payload, metadata_record],
            ns,
        )

    if event_type == "values":
        return (event_type, _strip_files_payload(data), ns)

    return (
        event_type,
        _strip_files_payload(data),
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
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """
    DeepAgents-native streaming endpoint.

    用稳定的 SSE 事件包装 DeepAgents / LangGraph 的 streaming 输出。

    路由层只负责认证、workspace/provider 归一化以及 SSE 包装，
    不再承担旧聊天壳的 trace/stop-reason 翻译职责。
    """

    def _event_iter():
        stream_request = _parse_stream_request(payload)
        req_id = uuid4().hex[:10]
        started = _now_ms()
        heartbeat_count = 0
        event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        done_token = "__done__"
        run_timeout_ms = int(
            max(
                0.1,
                float(getattr(settings, "deepagents_run_timeout_seconds", 75.0) or 75.0),
            )
            * 1000
        )
        forced_stop_emitted = False

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
            worker_db = create_session()
            try:
                resolved = resolve_deepagents_runtime(
                    worker_db,
                    user_id=int(current_user.id),
                    workspace=stream_request.workspace,
                    raw_attachment_ids=stream_request.attachment_ids,
                    cancel_checker=lambda: is_cancelled(cancel_token),
                    session_factory=create_session,
                )
                workspace = resolved.workspace

                _LOG.info(
                    "deepagents_stream worker_start req=%s uid=%s source=%s workspace=%s query=%s",
                    req_id,
                    int(current_user.id),
                    stream_request.source,
                    workspace,
                    stream_request.query_preview,
                )

                if resolved.provider == "rule_based" or not resolved.service.is_configured():
                    _push(
                        "error",
                        {
                            "message": "llm_not_configured",
                            "provider": resolved.provider,
                        },
                    )
                    return

                agent, usage, tool_runs, files_mapping = build_chat_agent(
                    service=resolved.service,
                    provider=resolved.provider,
                    context=resolved.tool_context,
                    limiter=resolved.limiter,
                    memory_text=resolved.memory_text,
                    cancel_token=cancel_token,
                )
                if agent is None:
                    _push(
                        "error",
                        {
                            "message": "llm_not_configured",
                            "provider": resolved.provider,
                        },
                    )
                    return

                topology = _serialize_agent_topology(agent)
                if topology is not None:
                    _push("values", {"topology": topology}, ns=["root"])

                if stream_request.invoke_messages is not None:
                    invoke_payload = build_invoke_payload_from_messages(
                        messages=stream_request.invoke_messages,
                        files_mapping=files_mapping,
                    )
                else:
                    invoke_payload = build_invoke_payload(
                        query=stream_request.query,
                        query_message_id=stream_request.query_message_id,
                        history_turns=stream_request.history_turns,
                        images=stream_request.images,
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
                worker_db.close()
                _push("done", {"status": done_token})
                _LOG.info(
                    "deepagents_stream worker_done req=%s uid=%s duration_ms=%s",
                    req_id,
                    int(current_user.id),
                    max(0, _now_ms() - started),
                )

        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()

        heartbeat_interval_s = 5.0
        poll_interval_s = 0.1
        last_heartbeat_ms = started
        try:
            while True:
                try:
                    event, data = event_queue.get(timeout=poll_interval_s)
                except queue.Empty:
                    now_ms = _now_ms()
                    if worker.is_alive() and now_ms - started >= run_timeout_ms:
                        cancel_token.cancelled = True
                        if not forced_stop_emitted:
                            forced_stop_emitted = True
                            yield _sse_event(
                                "error",
                                {
                                    "message": "deepagents_run_timeout: agent run exceeded the configured time budget",
                                },
                            )
                            yield _sse_event("done", {"status": done_token})
                        break
                    if now_ms - last_heartbeat_ms >= int(heartbeat_interval_s * 1000):
                        heartbeat_count += 1
                        last_heartbeat_ms = now_ms
                        yield _sse_event(
                            "ping",
                            {
                                "hb": heartbeat_count,
                            },
                        )
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
