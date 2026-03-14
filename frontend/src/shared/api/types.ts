/* ─── Auth ─── */
export interface Token { access_token: string; token_type: string }
export interface UserCreate { email: string; password: string }
export interface UserUpdate { email?: string; password?: string; avatar_url?: string }
export interface UserOut { id: number; email: string; avatar_url?: string; created_at: string }

/* ─── Accounts ─── */
export interface ConnectedAccountCreate {
  provider: string; identifier?: string
  access_token?: string; refresh_token?: string
  imap_host?: string; imap_port?: number; imap_use_ssl?: boolean
  imap_username?: string; imap_password?: string; imap_mailbox?: string
  feed_url?: string; feed_homepage_url?: string; feed_display_name?: string
  bilibili_uid?: string; x_username?: string
  forward_display_name?: string; forward_source_email?: string
}
export interface ConnectedAccountOut {
  id: number; provider: string; identifier: string
  last_synced_at?: string; created_at: string
}
export interface OAuthStartResponse { provider: string; auth_url: string }
export interface OAuthCredentialConfigOut { provider: string; configured: boolean; client_id_hint?: string }
export interface OAuthCredentialConfigUpdate { client_id: string; client_secret: string }
export interface ForwardAccountInfo {
  account_id: number; provider: string; identifier: string
  source_email: string; forward_address: string; inbound_url: string
}
export interface SyncJobStartResponse { job_id: string; status: string; account_id: number }
export interface SyncJobStatusResponse {
  job_id: string; status: string; account_id: number
  inserted?: number; error?: string
  created_at: string; started_at?: string; finished_at?: string
}

/* ─── Aelin Chat ─── */
export interface AelinChatRequest {
  query: string; use_memory?: boolean; max_citations?: number
  source?: string
  source_metadata?: Record<string, string>
  workspace?: string; images?: AelinImageInput[]
  attachment_ids?: number[]
  history?: { role: string; content: string }[]
}
export interface AelinImageInput { data_url: string; name?: string }
export interface AelinAttachmentUploadResponse {
  attachment_id: number
  file_name: string
  mime_type: string
  size_bytes: number
  workspace: string
  session_id?: string
  status: string
  chunk_count: number
  summary?: string
  deduplicated?: boolean
}
export interface AelinCitation {
  message_id: number; source: string; source_label: string; sender: string
  sender_avatar_url?: string; title: string; received_at: string; score: number
}
export interface AelinAction {
  kind: string; title: string; detail?: string
  payload?: Record<string, string>
}
export interface AelinToolStep {
  stage: string; status?: string; detail?: string; count?: number; ts?: number
}
export interface AelinChatResponse {
  answer: string; expression: string
  citations: AelinCitation[]; actions: AelinAction[]
  tool_trace: AelinToolStep[]; memory_summary: string
  generated_at: string
}

/* ─── Aelin Context ─── */
export interface AgentMemoryNoteOut { id: number; kind: string; content: string; source?: string; updated_at: string }
export interface AgentFocusItemOut {
  message_id: number; source: string; source_label: string; sender: string
  sender_avatar_url?: string; title: string; received_at: string; score: number
}
export interface AelinMemoryLayerItem {
  id: string; layer: string; title: string; detail?: string
  source?: string; confidence: number; updated_at?: string
  meta?: Record<string, string>
}
export interface AelinMemoryLayers {
  facts: AelinMemoryLayerItem[]; preferences: AelinMemoryLayerItem[]
  in_progress: AelinMemoryLayerItem[]; generated_at: string
}
export interface AelinTodoItem {
  id: number; title: string; detail?: string; done: boolean
  due_at?: string; priority: string
  contact_id?: number; message_id?: number; updated_at: string
}
export interface AelinDailyBrief {
  generated_at: string; summary: string
  top_updates: AgentFocusItemOut[]
  actions: { kind: string; title: string; detail?: string; priority?: string }[]
}
export interface AelinPinRecommendationItem {
  contact_id: number; display_name: string; score: number
  reasons: string[]; unread_count: number; last_message_at?: string
}
export interface AelinNotificationItem {
  id: string; level: string; title: string; detail?: string; source?: string
  ts?: string; action_kind?: string; action_payload?: Record<string, string>
}
export interface AelinContextResponse {
  workspace: string; summary: string
  focus_items: AgentFocusItemOut[]
  notes: AgentMemoryNoteOut[]; notes_count: number
  todos: AelinTodoItem[]
  pin_recommendations: AelinPinRecommendationItem[]
  daily_brief?: AelinDailyBrief
  layout_cards: { contact_id: number; display_name: string; pinned: boolean }[]
  memory_layers: AelinMemoryLayers
  notifications: AelinNotificationItem[]
  generated_at: string
}
export interface AelinNotificationResponse { total: number; items: AelinNotificationItem[]; generated_at: string }
export interface AelinProactivePollResponse { workspace: string; total: number; items: AelinNotificationItem[]; generated_at: string }

export interface AelinBrowserConfirmRequest {
  workspace?: string
  action_kind?: string
  action?: string
  profile_id?: string
  login_request_id?: string
  resume_request?: Record<string, unknown>
  resume_query?: string
  continue_after_confirm?: boolean
  next_call?: Record<string, unknown>
}
export interface AelinBrowserConfirmResponse {
  ok: boolean
  message: string
  requires_followup: boolean
  profile_id?: string
  login_request_id?: string
  login_state?: Record<string, unknown>
  tool_result: Record<string, unknown>
  continued: boolean
  continuation_error: string
  followup_result: Record<string, unknown>
  generated_at: string
}
export interface AelinBrowserLoginCheckpointItem {
  request_id: string
  profile_id?: string
  workspace?: string
  domain?: string
  reason?: string
  status?: string
  next_call?: Record<string, unknown>
  resume_query?: string
  resume_request?: Record<string, unknown>
  continue_after_confirm?: boolean
  created_at?: number
  updated_at?: number
}
export interface AelinBrowserLoginCheckpointListResponse {
  total: number
  items: AelinBrowserLoginCheckpointItem[]
  generated_at: string
}
export interface AelinFileMemoryItem {
  path: string; title: string; preview: string; score: number
  updated_at: string; canonical_id: string; target: string
  source: string; kind: string; topic_path: string; entry_kind: string
}
export interface AelinFileMemorySearchResponse {
  workspace: string; total: number; items: AelinFileMemoryItem[]; generated_at: string
}
export interface AelinFileMemoryContentResponse {
  workspace: string; path: string; title: string
  source: string; kind: string; topic_path: string; entry_kind: string
  updated_at: string; content: string; generated_at: string
}
export interface AelinDiaryTreeNode {
  name: string
  path: string
  kind: string
  title: string
  preview: string
  updated_at: string
  source: string
  topic_path: string
  entry_kind: string
  children: AelinDiaryTreeNode[]
}
export interface AelinDiaryTreeResponse {
  workspace: string
  total: number
  items: AelinDiaryTreeNode[]
  generated_at: string
}

/* ─── Device Center ─── */
export interface AelinDeviceProcessItem {
  pid: number; name: string; cpu_percent: number; memory_mb: number
  status: string; anomaly_score: number; anomaly_reasons: string[]
  safe_to_terminate: boolean
}
export interface AelinDeviceProcessResponse {
  sort_by: string; total: number; items: AelinDeviceProcessItem[]
  platform: string; generated_at: string
}
export interface AelinDeviceCapabilitiesResponse {
  platform: string; capabilities: Record<string, boolean>
  notes: string[]; generated_at: string
}
export interface AelinDeviceScreenCaptureResponse {
  data_url: string
  name: string
  width: number
  height: number
  source_display: string
  captured_at: string
  generated_at: string
}
export interface AelinDeviceScreenCaptureRequest {
  mode?: 'fullscreen' | 'region'
  display_id?: string
  max_edge?: number
  image_format?: 'jpeg' | 'png'
  quality?: number
  selection_timeout_ms?: number
}
export interface AelinDeviceModeApplyResponse {
  mode: string; status: string; summary: string
  steps: string[]; warnings: string[]; generated_at: string
}
export interface AelinDeviceOptimizeResponse {
  optimized_count: number; affected_pids: number[]
  steps: string[]; warnings: string[]; generated_at: string
}

/* ─── Agent ─── */
export interface AgentConfigOut {
  provider: string; base_url: string; model: string
  temperature: number; has_api_key: boolean
  web_search_proxy_url: string
}
export interface AgentConfigUpdate {
  provider?: string; base_url?: string; model?: string
  temperature?: number; api_key?: string
  web_search_proxy_url?: string
}
export interface AgentTestResponse { ok: boolean; provider: string; message: string }
export interface ModelInfo { id: string; name: string; family?: string; reasoning?: boolean; tool_call?: boolean }
export interface ModelProviderInfo {
  id: string; name: string; api?: string; doc?: string
  env: string[]; model_count: number; models: ModelInfo[]
}
export interface ModelCatalogResponse { source_url: string; fetched_at: string; providers: ModelProviderInfo[] }
export interface AgentTodoCreate { title: string; detail?: string; due_at?: string; priority?: string; contact_id?: number; message_id?: number }
export interface AgentTodoUpdate { done?: boolean; title?: string; detail?: string; due_at?: string; priority?: string }

/* Desk Feed */
export interface DeskFeedItem {
  message_id: number
  contact_id: number
  source: string
  source_label: string
  sender: string
  sender_avatar_url?: string | null
  title: string
  preview: string
  image_url?: string | null
  external_url?: string | null
  received_at: string
  is_read: boolean
  tags: string[]
  primary_tag: string
}

export interface DeskFeedResponse {
  items: DeskFeedItem[]
  next_before_received_at?: string | null
  next_before_id?: number | null
}

export interface DeskTagItem {
  tag: string
  count_7d: number
  last_seen_at?: string | null
  score: number
}

export interface DeskTagResponse {
  followed: DeskTagItem[]
  recommended: DeskTagItem[]
  discover: DeskTagItem[]
}
