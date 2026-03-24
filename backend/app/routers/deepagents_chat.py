from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import queue
import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends
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
from app.services.aelin.tool_hub import AelinToolHub
from app.services.aelin.tool_policy import AelinToolPolicy
from app.services.aelin.utils import normalize_positive_ints
from app.services.aelin.core_support import (
    _get_memory_summary_for_chat,
    _scoped_web_search_service,
)
from app.services.deepagents.deepagents_graph import build_chat_agent
from app.services.deepagents.input_mapping import build_invoke_payload
from app.services.deepagents.cancel_utils import is_cancelled
from app.settings import settings


router = APIRouter(prefix="/deepagents", tags=["deepagents"])
_LOG = logging.getLogger(__name__)


@router.post("/chat/stream")
def deepagents_chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    DeepAgents-native streaming endpoint.

    直接透出 DeepAgents / LangGraph 的 streaming chunk。

    路由层只负责认证、workspace/provider 归一化以及 SSE 包装，
    不再承担旧聊天壳的 trace/stop-reason 翻译职责。
    """

    def _event_iter():
        req_id = uuid4().hex[:10]
        started = _now_ms()
        heartbeat_count = 0
        event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        done_token = "__done__"

        class _CancelToken:
            cancelled: bool = False

        cancel_token = _CancelToken()

        def _push(event: str, data: dict[str, Any]) -> None:
            _LOG.debug(
                "deepagents_stream event req=%s uid=%s event=%s keys=%s",
                req_id,
                int(current_user.id),
                str(event),
                ",".join(sorted([str(k) for k in list((data or {}).keys())[:8] if str(k)])) or "-",
            )
            event_queue.put((event, data))

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

                # 为 DeepAgents 构造 LLM 服务与工具壳。
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

                memory_summary = _get_memory_summary_for_chat(
                    db,
                    current_user.id,
                    workspace=workspace,
                )

                attachment_ids = normalize_positive_ints(
                    getattr(payload, "attachment_ids", []),
                    cap=20,
                )

                tool_hub = AelinToolHub(
                    db=db,
                    user_id=current_user.id,
                    workspace=workspace,
                    web_search_service=_scoped_web_search_service(
                        getattr(service.config, "web_search_proxy_url", ""),
                    ),
                    available_attachment_ids=attachment_ids,
                )

                allow_write_tools = bool(
                    getattr(settings, "aelin_agent_loop_allow_write_tools", False)
                )
                policy = AelinToolPolicy(
                    max_tool_calls=int(
                        getattr(settings, "aelin_agent_loop_max_tool_calls", 512) or 512
                    ),
                    max_write_calls=int(
                        getattr(settings, "aelin_agent_loop_max_write_calls", 128) or 128
                    ),
                allow_write_tools=allow_write_tools,
                )

                agent, usage, tool_runs, files_mapping = build_chat_agent(
                    service=service,
                    provider=provider,
                    tool_hub=tool_hub,
                    policy=policy,
                    memory_summary=memory_summary,
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
                    history_turns=payload.history,
                    images=payload.images,
                    files_mapping=files_mapping,
                )

                # 透传 DeepAgents streaming chunk。
                for chunk in agent.stream(invoke_payload):
                    if is_cancelled(cancel_token):
                        break
                    try:
                        if hasattr(chunk, "dict"):
                            payload_obj = chunk.dict()  # type: ignore[assignment]
                        elif isinstance(chunk, dict):
                            payload_obj = chunk
                        else:
                            payload_obj = {"data": json.loads(json.dumps(chunk, default=str))}
                    except Exception:
                        payload_obj = {"data": json.loads(json.dumps(chunk, default=str))}
                    _push("chunk", payload_obj)

                _push(
                    "final",
                    {
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "tool_runs": tool_runs,
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
                _push("done", {"ts": _now_ms(), "status": done_token})
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
                "ts": _now_ms(),
                "req_id": req_id,
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
                    yield _sse_event(
                        "ping",
                        {"ts": _now_ms(), "req_id": req_id, "hb": heartbeat_count},
                    )
                    if (not worker.is_alive()) and event_queue.empty():
                        yield _sse_event(
                            "done", {"ts": _now_ms(), "status": done_token}
                        )
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
