from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.services.aelin.utils import normalize_positive_ints


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)
    avatar_url: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    avatar_url: Optional[str] = None
    created_at: datetime


class AgentMemoryNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="note", min_length=1, max_length=32)


class AgentMemoryNoteOut(BaseModel):
    id: int
    kind: str
    content: str
    source: Optional[str] = None
    updated_at: str


class AgentFocusItemOut(BaseModel):
    message_id: int
    source: str
    source_label: str
    sender: str
    sender_avatar_url: Optional[str] = None
    title: str
    received_at: str
    score: float


class ChatRequest(BaseModel):
    query: str = Field(default="", max_length=1200)
    use_memory: bool = True
    workspace: str = Field(default="default", min_length=1, max_length=64)
    source: str = Field(default="chat_ui", min_length=1, max_length=32)
    source_metadata: dict[str, str] = Field(default_factory=dict)
    images: list["ImageInput"] = Field(default_factory=list, max_length=4)
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)
    history: list["ChatHistoryTurn"] = Field(default_factory=list, max_length=20)

    @field_validator("query", mode="before")
    @classmethod
    def _normalize_query(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("images", mode="before")
    @classmethod
    def _normalize_images(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return []

    @field_validator("history", mode="before")
    @classmethod
    def _normalize_history(cls, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in value[:20]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant", "system"}:
                continue
            if not content:
                continue
            normalized.append({"role": role[:16], "content": content[:3000]})
        return normalized

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value: Any) -> str:
        clean = str(value or "chat_ui").strip().lower()
        return clean[:32] or "chat_ui"

    @field_validator("source_metadata", mode="before")
    @classmethod
    def _normalize_source_metadata(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, str] = {}
        for raw_key, raw_val in list(value.items())[:12]:
            key = str(raw_key or "").strip().lower()[:40]
            if not key:
                continue
            text = str(raw_val or "").strip()
            if not text:
                continue
            out[key] = text[:240]
        return out

    @field_validator("attachment_ids", mode="before")
    @classmethod
    def _normalize_attachment_ids(cls, value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        return normalize_positive_ints(value, cap=20)

    @model_validator(mode="after")
    def _finalize_query(self) -> "ChatRequest":
        if self.query:
            return self
        if self.images:
            self.query = "请结合这些图片给我一个简短说明。"
            return self
        if self.attachment_ids:
            self.query = "请先基于我上传的附件内容给出结论和建议。"
            return self
        raise ValueError("query is empty")


class ChatHistoryTurn(BaseModel):
    role: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=3000)


class ImageInput(BaseModel):
    data_url: str = Field(min_length=20, max_length=3_000_000)
    name: str = Field(default="", max_length=120)


class AelinAttachmentUploadResponse(BaseModel):
    attachment_id: int
    file_name: str
    mime_type: str
    size_bytes: int
    workspace: str
    session_id: str = ""
    status: str = "ready"
    chunk_count: int = 0
    summary: str = ""
    deduplicated: bool = False


class ChatCitation(BaseModel):
    message_id: int
    source: str
    source_label: str
    sender: str
    sender_avatar_url: Optional[str] = None
    title: str
    received_at: str
    score: float


class ChatAction(BaseModel):
    kind: str
    title: str
    detail: str = ""
    payload: dict[str, str] = Field(default_factory=dict)


class ChatToolStep(BaseModel):
    stage: str
    status: str = "completed"
    detail: str = ""
    count: int = 0
    ts: int = 0


class AelinTodoItem(BaseModel):
    id: int
    title: str
    detail: str = ""
    done: bool = False
    due_at: Optional[str] = None
    priority: str = "normal"
    contact_id: Optional[int] = None
    message_id: Optional[int] = None
    updated_at: str


class AelinMemoryLayerItem(BaseModel):
    id: str
    layer: str
    title: str
    detail: str = ""
    source: str = ""
    confidence: float = 0.5
    updated_at: str = ""
    meta: dict[str, str] = Field(default_factory=dict)


class AelinMemoryLayers(BaseModel):
    facts: list[AelinMemoryLayerItem] = Field(default_factory=list)
    preferences: list[AelinMemoryLayerItem] = Field(default_factory=list)
    in_progress: list[AelinMemoryLayerItem] = Field(default_factory=list)
    generated_at: datetime


class AelinContextResponse(BaseModel):
    workspace: str = "default"
    summary: str = ""
    notes: list[AgentMemoryNoteOut] = Field(default_factory=list)
    notes_count: int = 0
    todos: list[AelinTodoItem] = Field(default_factory=list)
    memory_layers: AelinMemoryLayers
    generated_at: datetime


class ChatResponse(BaseModel):
    answer: str
    expression: str = "exp-04"
    citations: list[ChatCitation] = Field(default_factory=list)
    actions: list[ChatAction] = Field(default_factory=list)
    tool_trace: list[ChatToolStep] = Field(default_factory=list)
    memory_summary: str = ""
    generated_at: datetime


AelinChatRequest = ChatRequest
AelinChatHistoryTurn = ChatHistoryTurn
AelinImageInput = ImageInput
AelinCitation = ChatCitation
AelinAction = ChatAction
AelinToolStep = ChatToolStep
AelinChatResponse = ChatResponse


class RemoteControlExecuteRequest(BaseModel):
    text: str = Field(default="", max_length=1200)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    source: str = Field(default="manual_remote", min_length=1, max_length=32)
    source_user_name: str = Field(default="", max_length=255)
    source_open_id: str = Field(default="", max_length=128)
    source_chat_id: str = Field(default="", max_length=128)
    source_message_id: str = Field(default="", max_length=128)
    history: list["ChatHistoryTurn"] = Field(default_factory=list, max_length=20)
    images: list["ImageInput"] = Field(default_factory=list, max_length=4)
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)


class RemoteControlExecuteResponse(BaseModel):
    ok: bool
    status: str = "completed"
    source: str = "remote_control"
    response: ChatResponse
    generated_at: datetime


class RemoteControlStatusResponse(BaseModel):
    enabled: bool = True
    source: str = "remote_control"
    capabilities: dict[str, bool] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    supported_tools: list[str] = Field(default_factory=list)
    supported_device_actions: list[str] = Field(default_factory=list)
    desktop_plugin_reachable: bool = False
    generated_at: datetime


class AelinFileMemoryItem(BaseModel):
    path: str
    title: str = ""
    preview: str = ""
    score: float = 0.0
    updated_at: str = ""
    canonical_id: str = ""
    target: str = ""
    source: str = ""
    kind: str = ""
    topic_path: str = ""
    entry_kind: str = ""


class AelinFileMemorySearchResponse(BaseModel):
    workspace: str = "default"
    total: int = 0
    items: list[AelinFileMemoryItem] = Field(default_factory=list)
    generated_at: datetime


class AelinFileMemoryContentResponse(BaseModel):
    workspace: str = "default"
    path: str
    title: str = ""
    source: str = ""
    kind: str = ""
    topic_path: str = ""
    entry_kind: str = ""
    updated_at: str = ""
    content: str = ""
    generated_at: datetime


class AelinDeviceCapabilitiesResponse(BaseModel):
    platform: str = "unknown"
    capabilities: dict[str, bool] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime


class AelinDeviceScreenCaptureResponse(BaseModel):
    data_url: str
    name: str = ""
    width: int = 0
    height: int = 0
    source_display: str = ""
    captured_at: str = ""
    generated_at: datetime


class AelinDeviceScreenCaptureRequest(BaseModel):
    mode: str = Field(default="fullscreen", min_length=1, max_length=32)
    display_id: str = Field(default="", max_length=64)
    max_edge: int = Field(default=1280, ge=640, le=4096)
    image_format: str = Field(default="jpeg", min_length=3, max_length=8)
    quality: int = Field(default=72, ge=35, le=95)
    selection_timeout_ms: int = Field(default=45000, ge=5000, le=180000)


class AgentTodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    detail: str = Field(default="", max_length=2000)
    due_at: Optional[str] = None
    priority: str = Field(default="normal", min_length=1, max_length=16)
    contact_id: Optional[int] = None
    message_id: Optional[int] = None


class AgentTodoUpdate(BaseModel):
    done: Optional[bool] = None
    title: Optional[str] = Field(None, min_length=1, max_length=240)
    detail: Optional[str] = Field(None, max_length=2000)
    due_at: Optional[str] = None
    priority: Optional[str] = Field(None, min_length=1, max_length=16)


class AgentTodoOut(BaseModel):
    id: int
    title: str
    detail: str = ""
    done: bool = False
    due_at: Optional[str] = None
    priority: str = "normal"
    contact_id: Optional[int] = None
    message_id: Optional[int] = None
    updated_at: str


class AgentConfigOut(BaseModel):
    provider: str
    base_url: str
    model: str
    temperature: float
    verify_ssl: bool = True
    has_api_key: bool = False
    web_search_proxy_url: str = ""


class AgentConfigUpdate(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = Field(None, min_length=1, max_length=2048)
    model: Optional[str] = Field(None, min_length=1, max_length=255)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    verify_ssl: Optional[bool] = None
    api_key: Optional[str] = Field(None, min_length=1, max_length=4096)
    web_search_proxy_url: Optional[str] = Field(None, max_length=2048)


class AgentTestResponse(BaseModel):
    ok: bool
    provider: str
    message: str


class ModelInfo(BaseModel):
    id: str
    name: str
    family: Optional[str] = None
    reasoning: Optional[bool] = None
    tool_call: Optional[bool] = None
    temperature: Optional[bool] = None


class ModelProviderInfo(BaseModel):
    id: str
    name: str
    api: Optional[str] = None
    doc: Optional[str] = None
    env: list[str] = Field(default_factory=list)
    model_count: int = 0
    models: list[ModelInfo] = Field(default_factory=list)


class ModelCatalogResponse(BaseModel):
    source_url: str
    fetched_at: datetime
    providers: list[ModelProviderInfo]


