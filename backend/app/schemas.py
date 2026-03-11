from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.services.aelin_utils import normalize_positive_ints


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


class ConnectedAccountCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    identifier: str = Field(default="", max_length=255)
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

    # Optional provider-specific fields (used when provider == "imap").
    imap_host: Optional[str] = Field(None, min_length=1, max_length=255)
    imap_port: Optional[int] = Field(None, ge=1, le=65535)
    imap_use_ssl: Optional[bool] = None
    imap_username: Optional[str] = Field(None, min_length=1, max_length=255)
    imap_password: Optional[str] = Field(None, min_length=1, max_length=2048)
    imap_mailbox: Optional[str] = Field(None, min_length=1, max_length=255)

    # Optional provider-specific fields (used when provider in {"rss", "bilibili", "x"}).
    feed_url: Optional[str] = Field(None, max_length=2048)
    feed_homepage_url: Optional[str] = Field(None, max_length=2048)
    feed_display_name: Optional[str] = Field(None, max_length=255)
    bilibili_uid: Optional[str] = Field(None, min_length=1, max_length=64)
    x_username: Optional[str] = Field(None, min_length=1, max_length=64)
    forward_display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    forward_source_email: Optional[EmailStr] = None


class ConnectedAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    identifier: str
    last_synced_at: Optional[datetime] = None
    created_at: datetime


class AccountOAuthStartResponse(BaseModel):
    provider: str
    auth_url: str


class OAuthCredentialConfigOut(BaseModel):
    provider: str
    configured: bool
    client_id_hint: Optional[str] = None


class OAuthCredentialConfigUpdate(BaseModel):
    client_id: str = Field(min_length=1, max_length=512)
    client_secret: str = Field(min_length=1, max_length=4096)


class ForwardAccountInfo(BaseModel):
    account_id: int
    provider: str
    identifier: str
    source_email: EmailStr
    forward_address: str
    inbound_url: str


class ContactOut(BaseModel):
    id: int
    display_name: str
    handle: str
    avatar_url: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    latest_subject: Optional[str] = None
    latest_preview: Optional[str] = None
    latest_source: Optional[str] = None
    latest_received_at: Optional[datetime] = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    source: str
    sender: str
    subject: str
    body_preview: str
    received_at: datetime
    is_read: bool
    summary: Optional[str] = None


class MessageDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    source: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    is_read: bool
    summary: Optional[str] = None


class AgentChatRequest(BaseModel):
    messages: list[dict[str, str]]
    context_contact_id: Optional[int] = None
    tools: list[str] = Field(default_factory=list)
    use_memory: bool = True
    stream: bool = True


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


class AelinChatRequest(BaseModel):
    query: str = Field(default="", max_length=1200)
    use_memory: bool = True
    max_citations: int = Field(default=6, ge=1, le=20)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    source: str = Field(default="chat_ui", min_length=1, max_length=32)
    source_metadata: dict[str, str] = Field(default_factory=dict)
    images: list["AelinImageInput"] = Field(default_factory=list, max_length=4)
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)
    history: list["AelinChatHistoryTurn"] = Field(default_factory=list, max_length=20)
    search_mode: str = Field(default="auto", min_length=1, max_length=16)

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
    def _finalize_query(self) -> "AelinChatRequest":
        if self.query:
            return self
        if self.images:
            self.query = "请结合这些图片给我一个简短说明。"
            return self
        if self.attachment_ids:
            self.query = "请先基于我上传的附件内容给出结论和建议。"
            return self
        raise ValueError("query is empty")


class AelinChatHistoryTurn(BaseModel):
    role: str = Field(min_length=1, max_length=16)
    content: str = Field(min_length=1, max_length=3000)


class AelinImageInput(BaseModel):
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


class AelinCitation(BaseModel):
    message_id: int
    source: str
    source_label: str
    sender: str
    sender_avatar_url: Optional[str] = None
    title: str
    received_at: str
    score: float


class AelinAction(BaseModel):
    kind: str
    title: str
    detail: str = ""
    payload: dict[str, str] = Field(default_factory=dict)


class AelinToolStep(BaseModel):
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


class AelinPinRecommendationItem(BaseModel):
    contact_id: int
    display_name: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    unread_count: int = 0
    last_message_at: Optional[datetime] = None


class AelinDailyBriefAction(BaseModel):
    kind: str
    title: str
    detail: str = ""
    contact_id: Optional[int] = None
    message_id: Optional[int] = None
    priority: str = "normal"


class AelinDailyBrief(BaseModel):
    generated_at: datetime
    summary: str
    top_updates: list[AgentFocusItemOut] = Field(default_factory=list)
    actions: list[AelinDailyBriefAction] = Field(default_factory=list)


class AelinLayoutCard(BaseModel):
    contact_id: int
    display_name: str
    pinned: bool = False
    order: int = Field(default=0, ge=0)
    x: float = Field(default=0, ge=0)
    y: float = Field(default=0, ge=0)
    width: float = Field(default=312, ge=120, le=2400)
    height: float = Field(default=316, ge=120, le=2400)


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


class AelinNotificationItem(BaseModel):
    id: str
    level: str = "info"
    title: str
    detail: str = ""
    source: str = ""
    ts: str = ""
    action_kind: Optional[str] = None
    action_payload: dict[str, str] = Field(default_factory=dict)


class AelinNotificationResponse(BaseModel):
    total: int = 0
    items: list[AelinNotificationItem] = Field(default_factory=list)
    generated_at: datetime


class AelinProactivePollResponse(BaseModel):
    workspace: str = "default"
    total: int = 0
    items: list[AelinNotificationItem] = Field(default_factory=list)
    generated_at: datetime


class AgentMemorySnapshot(BaseModel):
    summary: str = ""
    notes: list[AgentMemoryNoteOut] = Field(default_factory=list)
    focus_items: list[AgentFocusItemOut] = Field(default_factory=list)


class AelinContextResponse(BaseModel):
    workspace: str = "default"
    summary: str = ""
    focus_items: list[AgentFocusItemOut] = Field(default_factory=list)
    notes: list[AgentMemoryNoteOut] = Field(default_factory=list)
    notes_count: int = 0
    todos: list[AelinTodoItem] = Field(default_factory=list)
    pin_recommendations: list[AelinPinRecommendationItem] = Field(default_factory=list)
    daily_brief: Optional[AelinDailyBrief] = None
    layout_cards: list[AelinLayoutCard] = Field(default_factory=list)
    memory_layers: AelinMemoryLayers
    notifications: list[AelinNotificationItem] = Field(default_factory=list)
    generated_at: datetime


class AelinChatResponse(BaseModel):
    answer: str
    expression: str = "exp-04"
    citations: list[AelinCitation] = Field(default_factory=list)
    actions: list[AelinAction] = Field(default_factory=list)
    tool_trace: list[AelinToolStep] = Field(default_factory=list)
    memory_summary: str = ""
    generated_at: datetime


class RemoteControlExecuteRequest(BaseModel):
    text: str = Field(default="", max_length=1200)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    source: str = Field(default="manual_remote", min_length=1, max_length=32)
    source_user_name: str = Field(default="", max_length=255)
    source_open_id: str = Field(default="", max_length=128)
    source_chat_id: str = Field(default="", max_length=128)
    source_message_id: str = Field(default="", max_length=128)
    history: list["AelinChatHistoryTurn"] = Field(default_factory=list, max_length=20)
    images: list["AelinImageInput"] = Field(default_factory=list, max_length=4)
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)
    search_mode: str = Field(default="auto", min_length=1, max_length=16)


class RemoteControlExecuteResponse(BaseModel):
    ok: bool
    status: str = "completed"
    source: str = "remote_control"
    response: AelinChatResponse
    generated_at: datetime


class RemoteControlStatusResponse(BaseModel):
    enabled: bool = True
    source: str = "remote_control"
    capabilities: dict[str, bool] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    supported_atomic_actions: list[str] = Field(default_factory=list)
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


class AelinDiaryTreeNode(BaseModel):
    name: str
    path: str
    kind: str
    title: str = ""
    preview: str = ""
    updated_at: str = ""
    source: str = ""
    topic_path: str = ""
    entry_kind: str = ""
    children: list["AelinDiaryTreeNode"] = Field(default_factory=list)


class AelinDiaryTreeResponse(BaseModel):
    workspace: str = "default"
    total: int = 0
    items: list[AelinDiaryTreeNode] = Field(default_factory=list)
    generated_at: datetime


class AelinMediaIngestRequest(BaseModel):
    url: str = Field(min_length=5, max_length=3000)
    workspace: str = Field(default="default", min_length=1, max_length=64)
    languages: list[str] = Field(default_factory=lambda: ["zh-Hans", "zh-CN", "zh", "en"], max_length=8)
    auto_login_guide: bool = True
    login_wait_seconds: int = Field(default=180, ge=30, le=900)
    force_relogin: bool = False


class AelinMediaIngestResponse(BaseModel):
    status: str
    message: str
    url: str
    platform: str
    title: str = ""
    source_type: str = ""
    summary: str = ""
    summary_overview: str = ""
    information_note: str = ""
    confidence: float = 0.0
    quality_score: float = 0.0
    quality_reason: str = ""
    quality_usable: bool = False
    needs_review: bool = True
    written: bool = False
    diary_path: str = ""
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime


class AelinMediaAuthGuideRequest(BaseModel):
    wait_seconds: int = Field(default=180, ge=30, le=900)
    open_url: str = Field(default="", max_length=3000)
    force_relogin: bool = False


class AelinMediaAuthGuideResponse(BaseModel):
    status: str
    platform: str
    message: str
    login_url: str = ""
    profile_dir: str = ""
    wait_seconds: int = 0
    cookie_count: int = 0
    generated_at: datetime


class AelinDeviceProcessItem(BaseModel):
    pid: int
    name: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    status: str = ""
    username: str = ""
    create_time: Optional[str] = None
    anomaly_score: float = 0.0
    anomaly_reasons: list[str] = Field(default_factory=list)
    safe_to_terminate: bool = False


class AelinDeviceProcessResponse(BaseModel):
    sort_by: str = "cpu"
    total: int = 0
    items: list[AelinDeviceProcessItem] = Field(default_factory=list)
    platform: str = "unknown"
    filter_context: dict[str, str] = Field(default_factory=dict)
    empty_reason: str = ""
    generated_at: datetime


class AelinDeviceProcessActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)


class AelinDeviceProcessActionResponse(BaseModel):
    pid: int
    action: str
    ok: bool
    detail: str = ""
    generated_at: datetime


class AelinDeviceModeApplyRequest(BaseModel):
    mode: str = Field(min_length=1, max_length=32)


class AelinDeviceModeApplyResponse(BaseModel):
    mode: str
    status: str
    summary: str
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime


class AelinDeviceOptimizeResponse(BaseModel):
    optimized_count: int = 0
    affected_pids: list[int] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
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


class AgentCardLayoutItem(BaseModel):
    contact_id: int
    display_name: str = Field(min_length=1, max_length=255)
    pinned: bool = False
    order: int = Field(default=0, ge=0)
    x: float = Field(default=0, ge=0)
    y: float = Field(default=0, ge=0)
    width: float = Field(default=312, ge=120, le=2400)
    height: float = Field(default=316, ge=120, le=2400)


class AgentCardLayoutUpdate(BaseModel):
    cards: list[AgentCardLayoutItem] = Field(default_factory=list)
    workspace: str = Field(default="default", min_length=1, max_length=64)


class AgentPinRecommendationItem(BaseModel):
    contact_id: int
    display_name: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    unread_count: int = 0
    last_message_at: Optional[datetime] = None


class AgentPinRecommendationResponse(BaseModel):
    generated_at: datetime
    items: list[AgentPinRecommendationItem] = Field(default_factory=list)


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


class AgentDailyBriefAction(BaseModel):
    kind: str
    title: str
    detail: str = ""
    contact_id: Optional[int] = None
    message_id: Optional[int] = None
    priority: str = "normal"


class AgentDailyBriefResponse(BaseModel):
    generated_at: datetime
    summary: str
    top_updates: list[AgentFocusItemOut] = Field(default_factory=list)
    actions: list[AgentDailyBriefAction] = Field(default_factory=list)


class AgentAdvancedSearchRequest(BaseModel):
    query: str = Field(default="", max_length=200)
    source: Optional[str] = Field(default=None, max_length=50)
    unread_only: bool = False
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)


class AgentAdvancedSearchItem(BaseModel):
    message_id: int
    contact_id: int
    sender: str
    subject: str
    source: str
    received_at: str
    preview: str
    is_read: bool
    score: float
    reason: str = ""


class AgentAdvancedSearchResponse(BaseModel):
    total: int
    items: list[AgentAdvancedSearchItem] = Field(default_factory=list)


class DeskFeedItem(BaseModel):
    message_id: int
    contact_id: int
    source: str
    source_label: str
    sender: str
    sender_avatar_url: Optional[str] = None
    title: str
    preview: str
    image_url: Optional[str] = None
    external_url: Optional[str] = None
    received_at: str
    is_read: bool
    tags: list[str] = Field(default_factory=list)
    primary_tag: str = ""


class DeskFeedResponse(BaseModel):
    items: list[DeskFeedItem] = Field(default_factory=list)
    next_before_received_at: Optional[str] = None
    next_before_id: Optional[int] = None


class DeskTagItem(BaseModel):
    tag: str
    count_7d: int = 0
    last_seen_at: Optional[str] = None
    score: float = 0.0


class DeskTagResponse(BaseModel):
    followed: list[DeskTagItem] = Field(default_factory=list)
    recommended: list[DeskTagItem] = Field(default_factory=list)
    discover: list[DeskTagItem] = Field(default_factory=list)


class DeskTagFollowRequest(BaseModel):
    tag: str = Field(min_length=1, max_length=64)


class AgentSummarizeRequest(BaseModel):
    text: str


class AgentSummarizeResponse(BaseModel):
    summary: str


class DraftReplyRequest(BaseModel):
    text: str
    tone: str = "friendly"


class DraftReplyResponse(BaseModel):
    draft: str


class AgentConfigOut(BaseModel):
    provider: str
    base_url: str
    model: str
    temperature: float
    has_api_key: bool = False
    web_search_proxy_url: str = ""


class AgentConfigUpdate(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = Field(None, min_length=1, max_length=2048)
    model: Optional[str] = Field(None, min_length=1, max_length=255)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
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


class SyncJobStartResponse(BaseModel):
    job_id: str
    status: str
    account_id: int


class SyncJobStatusResponse(BaseModel):
    job_id: str
    status: str
    account_id: int
    inserted: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
