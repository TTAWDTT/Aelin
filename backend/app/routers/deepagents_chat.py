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

from app.db import create_session, get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AelinChatRequest
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
from app.services.deepagents.cancel_utils import is_cancelled
from app.settings import settings


router = APIRouter(prefix="/deepagents", tags=["deepagents"])
_LOG = logging.getLogger(__name__)


def _normalize_history(raw_turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Lightweight history normalizer for DeepAgents-native shell.

    We intentionally keep this independent from the legacy Aelin core helpers
    so that the DeepAgents 路由不会再隐式依赖旧的 agent loop 实现。
    """
    out: list[dict[str, str]] = []
    for item in raw_turns[-12:]:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system"}:
            continue
        if not content:
            continue
        out.append({"role": role, "content": content[:3000]})
    return out


def _normalize_images(raw_images: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw_images[:4]:
        data_url = str(getattr(item, "data_url", "") or "").strip()
        name = str(getattr(item, "name", "") or "").strip()[:120]
        if not data_url.startswith("data:image/"):
            continue
        if ";base64," not in data_url:
            continue
        out.append({"data_url": data_url, "name": name})
    return out


@router.post("/chat/stream")
def deepagents_chat_stream(
    payload: AelinChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    DeepAgents-native streaming endpoint.

    与旧的 `/aelin/chat/stream` 不同，这里直接将 DeepAgents / LangGraph
    的 streaming chunk 通过 SSE 透出，不再重新包装为 Aelin 自定义的
    stop_reason / tool_trace 结构。
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

                agent, _usage, _tool_runs, files_mapping = build_chat_agent(
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
                history_turns = _normalize_history(getattr(payload, "history", []))
                images = _normalize_images(getattr(payload, "images", []))

                messages: list[dict[str, Any]] = []
                for turn in history_turns:
                    messages.append(
                        {
                            "role": turn["role"],
                            "content": turn["content"],
                        }
                    )

                latest_query = str(payload.query or "").strip()
                if latest_query:
                    if images:
                        content_blocks: list[dict[str, Any]] = [
                            {"type": "text", "text": latest_query}
                        ]
                        for image in images:
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
                                "content": content_blocks
                                if len(content_blocks) > 1
                                else latest_query,
                            }
                        )
                    else:
                        messages.append({"role": "user", "content": latest_query})

                invoke_payload: dict[str, Any] = {"messages": messages}
                if files_mapping:
                    invoke_payload["files"] = files_mapping

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
                "search_mode": str(
                    getattr(payload, "search_mode", "auto") or "auto"
                )[:16],
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

