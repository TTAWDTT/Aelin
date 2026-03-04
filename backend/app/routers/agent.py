from __future__ import annotations

from typing import Iterator, Literal
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import (
    AgentAdvancedSearchRequest,
    AgentAdvancedSearchResponse,
    AgentChatRequest,
    AgentCardLayoutUpdate,
    AgentConfigOut,
    AgentConfigUpdate,
    AgentDailyBriefResponse,
    AgentFocusItemOut,
    AgentMemoryNoteCreate,
    AgentMemoryNoteOut,
    AgentMemorySnapshot,
    AgentPinRecommendationItem,
    AgentPinRecommendationResponse,
    AgentSummarizeRequest,
    AgentSummarizeResponse,
    AgentTodoCreate,
    AgentTodoOut,
    AgentTodoUpdate,
    AgentTestResponse,
    DraftReplyRequest,
    DraftReplyResponse,
    ModelCatalogResponse,
)
from app.services.agent_memory import AgentMemoryService
from app.services.agent_tools import TOOLS_DEFINITIONS, ToolExecutor, filter_tool_definitions
from app.services.encryption import decrypt_optional
from app.services.llm import LLMService
from app.services.model_catalog import get_model_catalog
from app.services.summarizer import RuleBasedSummarizer

router = APIRouter(prefix="/agent", tags=["agent"])

_summarizer = RuleBasedSummarizer()
_memory = AgentMemoryService()

# ... (Previous helper functions: _default_config, _config_out, _get_llm_service) ...
def _default_config() -> AgentConfigOut:
    return AgentConfigOut(
        provider="rule_based",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        temperature=0.2,
        has_api_key=False,
        web_search_proxy_url="",
    )


def _config_out(db: Session, user_id: int) -> AgentConfigOut:
    config = crud.get_agent_config(db, user_id=user_id)
    if config is None:
        return _default_config()

    api_key = decrypt_optional(config.api_key)
    return AgentConfigOut(
        provider=(config.provider or "rule_based").lower(),
        base_url=config.base_url or "https://api.openai.com/v1",
        model=config.model or "gpt-4o-mini",
        temperature=float(config.temperature or 0.2),
        has_api_key=bool(api_key),
        web_search_proxy_url=str(config.web_search_proxy_url or ""),
    )


def _get_llm_service(db: Session, user: User) -> tuple[LLMService, str]:
    """Returns (service, provider_type)"""
    config = _config_out(db, user.id)
    provider = (config.provider or "rule_based").lower()

    if provider in {"rule_based", "rule-based", "builtin", "local"}:
        return LLMService(config, None), "rule_based"

    stored = crud.get_agent_config(db, user_id=user.id)
    api_key = decrypt_optional(stored.api_key if stored else None) if stored else None

    if not api_key:
        raise HTTPException(status_code=400, detail="请先在设置里配置 Agent API Key")
    if not (config.base_url or "").strip():
        raise HTTPException(status_code=400, detail="请先在设置里配置 Agent Base URL")

    return LLMService(config, api_key), "openai"


@router.post("/chat")
def chat_stream(
    payload: AgentChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    incoming_messages = [
        {
            "role": str(m.get("role") or "").strip(),
            "content": str(m.get("content") or ""),
        }
        for m in payload.messages
        if isinstance(m, dict)
    ]

    if provider == "rule_based":
        def _iter_simple():
            yield "目前仅支持在配置 OpenAI 兼容接口后使用对话功能。"
        return StreamingResponse(_iter_simple(), media_type="text/event-stream")

    messages = list(incoming_messages)

    # Inject Context if needed
    if payload.context_contact_id:
        contact = crud.get_contact_by_id(db, user_id=current_user.id, contact_id=payload.context_contact_id)
        if contact:
            # Fetch recent messages for context
            recent_msgs = crud.list_messages(db, user_id=current_user.id, contact_id=contact.id, limit=10)
            context_str = f"Current Contact Context:\nName: {contact.display_name}\nHandle: {contact.handle}\n"
            if recent_msgs:
                context_str += "Recent Interactions:\n"
                for m in reversed(recent_msgs):
                    context_str += f"- [{m.received_at.strftime('%Y-%m-%d %H:%M')}] {m.sender}: {m.body_preview[:200]}\n"
            else:
                context_str += "No recent messages.\n"

            # Insert context as a system message at the beginning
            messages.insert(0, {"role": "system", "content": context_str})

    # Initialize memory context
    user_query = ""
    for m in reversed(incoming_messages):
        if m["role"] == "user":
            user_query = m["content"]
            break
    if payload.use_memory:
        memory_prompt = _memory.build_system_memory_prompt(db, current_user.id, query=user_query)
        if memory_prompt:
            messages.insert(0, {"role": "system", "content": memory_prompt})

    # Initialize Tool Executor with optional per-message allowlist
    tool_allowlist = {t.strip() for t in payload.tools if isinstance(t, str) and t.strip()} if payload.tools else None
    executor = ToolExecutor(db, current_user.id, allowlist=tool_allowlist)
    active_tool_defs = filter_tool_definitions(executor.available_tools) if tool_allowlist else TOOLS_DEFINITIONS

    # Core System Prompt
    system_prompt = """You are MercuryDesk AI, an intelligent assistant for a unified messaging platform.
Your goal is to help the user manage their communications efficiently.

Capabilities:
1.  **Search**: You can search through the user's message history (emails, DMs, etc.) using the `search_messages` tool.
2.  **Contact Info**: You can look up details about contacts using `get_contact_info`.
3.  **Drafting**: You can help draft replies.
4.  **Summarization**: You can summarize long conversation threads.

Guidelines:
-   **Be Concise**: Users are busy. Keep responses brief and to the point unless asked for details.
-   **Context Aware**: Use the provided contact context to answer questions like "What was the last thing he sent?" or "Summarize our chat".
-   **Proactive**: If a user asks a vague question like "Any updates from John?", use your tools to find out.
-   **Tone**: Professional yet helpful and friendly.

Current Time: {current_time}
""".format(current_time=datetime.now().strftime("%Y-%m-%d %H:%M"))

    messages.insert(0, {"role": "system", "content": system_prompt})

    try:
        def _stream():
            chunks: list[str] = []
            generator = service.chat_stream(
                messages=messages,
                tools=active_tool_defs,
                tool_executor=executor,
                max_rounds=3,
                max_calls_per_round=6,
            )
            for chunk in generator:
                chunks.append(chunk)
                yield chunk

            if payload.use_memory:
                assistant_reply = "".join(chunks).strip()
                if assistant_reply:
                    _memory.update_after_turn(db, current_user.id, incoming_messages, assistant_reply)
                    db.commit()

        return StreamingResponse(_stream(), media_type="text/event-stream")
    except ValueError as e:
         def _iter_err():
            yield f"Error: {str(e)}"
         return StreamingResponse(_iter_err(), media_type="text/event-stream")

# ... (Rest of the router: catalog, summarize, draft-reply, config, test) ...
@router.get("/catalog", response_model=ModelCatalogResponse)
def model_catalog(force_refresh: bool = Query(default=False)):
    return get_model_catalog(force_refresh=force_refresh)


@router.post("/summarize", response_model=AgentSummarizeResponse)
def summarize(
    payload: AgentSummarizeRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    if provider == "rule_based":
        return AgentSummarizeResponse(summary=_summarizer.summarize(payload.text))

    try:
        summary = service.summarize(payload.text, stream=False)
        return AgentSummarizeResponse(summary=str(summary))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/summarize/stream")
def summarize_stream(
    payload: AgentSummarizeRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    if provider == "rule_based":
        # Simulate stream for rule-based
        def _iter():
            yield _summarizer.summarize(payload.text)
        return StreamingResponse(_iter(), media_type="text/event-stream")

    try:
        generator = service.summarize(payload.text, stream=True)
        return StreamingResponse(generator, media_type="text/event-stream")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/draft-reply", response_model=DraftReplyResponse)
def draft_reply(
    payload: DraftReplyRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    if provider == "rule_based":
        return DraftReplyResponse(draft=_summarizer.draft_reply(payload.text, tone=payload.tone))

    try:
        draft = service.draft_reply(payload.text, tone=payload.tone, stream=False)
        return DraftReplyResponse(draft=str(draft))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/draft-reply/stream")
def draft_reply_stream(
    payload: DraftReplyRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    if provider == "rule_based":
        def _iter():
            yield _summarizer.draft_reply(payload.text, tone=payload.tone)
        return StreamingResponse(_iter(), media_type="text/event-stream")

    try:
        generator = service.draft_reply(payload.text, tone=payload.tone, stream=True)
        return StreamingResponse(generator, media_type="text/event-stream")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config", response_model=AgentConfigOut)
def get_agent_config(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return _config_out(db, current_user.id)


@router.patch("/config", response_model=AgentConfigOut)
def update_agent_config(
    payload: AgentConfigUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    provider = None
    if payload.provider is not None:
        provider = payload.provider.strip().lower()
        if not provider:
            raise HTTPException(status_code=400, detail="provider 不能为空")
    config = crud.upsert_agent_config(
        db,
        user_id=current_user.id,
        provider=provider,
        base_url=payload.base_url,
        model=payload.model,
        temperature=payload.temperature,
        api_key=payload.api_key,
        web_search_proxy_url=payload.web_search_proxy_url,
    )
    api_key = decrypt_optional(config.api_key)
    return AgentConfigOut(
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        temperature=float(config.temperature),
        has_api_key=bool(api_key),
        web_search_proxy_url=str(config.web_search_proxy_url or ""),
    )


@router.get("/memory", response_model=AgentMemorySnapshot)
def get_agent_memory(
    query: str = Query(default=""),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    snapshot = _memory.snapshot(db, current_user.id, query=query)
    return AgentMemorySnapshot(
        summary=snapshot["summary"],
        notes=[AgentMemoryNoteOut(**n) for n in snapshot["notes"]],
        focus_items=[AgentFocusItemOut(**it) for it in snapshot["focus_items"]],
    )


@router.post("/memory/notes", response_model=AgentMemoryNoteOut)
def add_agent_memory_note(
    payload: AgentMemoryNoteCreate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = _memory.add_note(db, current_user.id, payload.content, kind=payload.kind, source="manual")
    db.commit()
    db.refresh(row)
    return AgentMemoryNoteOut(
        id=row.id,
        kind=row.kind,
        content=row.content,
        source=row.source,
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


@router.delete("/memory/notes/{note_id}")
def delete_agent_memory_note(
    note_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    deleted = _memory.delete_note(db, current_user.id, note_id)
    if deleted:
        db.commit()
    return {"deleted": deleted, "note_id": note_id}


@router.post("/memory/layout")
def upsert_agent_card_layout(
    payload: AgentCardLayoutUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = _memory.upsert_card_layout(
        db,
        current_user.id,
        cards=[item.model_dump() for item in payload.cards],
        workspace=payload.workspace,
    )
    db.flush()
    db.commit()
    return {"ok": True, "note_id": row.id, "count": len(payload.cards)}


@router.get("/pin-recommendations", response_model=AgentPinRecommendationResponse)
def get_pin_recommendations(
    limit: int = Query(default=6, ge=1, le=20),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = _memory.recommend_pins(db, current_user.id, limit=limit)
    return AgentPinRecommendationResponse(
        generated_at=datetime.now(timezone.utc),
        items=[AgentPinRecommendationItem(**row) for row in rows],
    )


@router.get("/daily-brief", response_model=AgentDailyBriefResponse)
def get_daily_brief(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = _memory.build_daily_brief(db, current_user.id)
    return AgentDailyBriefResponse(**data)


@router.get("/todos", response_model=list[AgentTodoOut])
def list_todos(
    include_done: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = _memory.list_todos(db, current_user.id, include_done=include_done, limit=limit)
    return [AgentTodoOut(**row) for row in rows]


@router.post("/todos", response_model=AgentTodoOut)
def create_todo(
    payload: AgentTodoCreate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = _memory.create_todo(
        db,
        current_user.id,
        title=payload.title,
        detail=payload.detail,
        due_at=payload.due_at,
        priority=payload.priority,
        contact_id=payload.contact_id,
        message_id=payload.message_id,
    )
    db.commit()
    db.refresh(row)
    parsed = _memory.list_todos(db, current_user.id, include_done=True, limit=200)
    found = next((x for x in parsed if int(x["id"]) == int(row.id)), None)
    if found is None:
        raise HTTPException(status_code=500, detail="todo create failed")
    return AgentTodoOut(**found)


@router.patch("/todos/{todo_id}", response_model=AgentTodoOut)
def update_todo(
    todo_id: int,
    payload: AgentTodoUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = _memory.update_todo(
        db,
        current_user.id,
        todo_id,
        done=payload.done,
        title=payload.title,
        detail=payload.detail,
        due_at=payload.due_at,
        priority=payload.priority,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.commit()
    rows = _memory.list_todos(db, current_user.id, include_done=True, limit=200)
    found = next((x for x in rows if int(x["id"]) == int(todo_id)), None)
    if found is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return AgentTodoOut(**found)


@router.delete("/todos/{todo_id}")
def delete_todo(
    todo_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    deleted = _memory.delete_todo(db, current_user.id, todo_id)
    if deleted:
        db.commit()
    return {"deleted": deleted, "todo_id": todo_id}


@router.post("/search/advanced", response_model=AgentAdvancedSearchResponse)
def advanced_search(
    payload: AgentAdvancedSearchRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = _memory.advanced_search(
        db,
        current_user.id,
        query=payload.query,
        source=payload.source,
        unread_only=payload.unread_only,
        days=payload.days,
        limit=payload.limit,
    )
    return AgentAdvancedSearchResponse(**data)


@router.post("/test", response_model=AgentTestResponse)
def test_agent(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    service, provider = _get_llm_service(db, current_user)

    if provider == "rule_based":
        return AgentTestResponse(ok=True, provider="rule_based", message="内置规则引擎已就绪")

    try:
        out = service._chat(
            messages=[
                {"role": "system", "content": "你是一个健康检查器。只回复 OK。"},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=30,
            stream=False
        )
        return AgentTestResponse(ok=True, provider=service.config.provider, message=str(out) or "OK")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
