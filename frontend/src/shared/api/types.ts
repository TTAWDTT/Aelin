/* ─── Auth ─── */
export interface Token { access_token: string; token_type: string }
export interface UserCreate { email: string; password: string }
export interface UserUpdate { email?: string; password?: string; avatar_url?: string }
export interface UserOut { id: number; email: string; avatar_url?: string; created_at: string }

/* ─── Chat ─── */
export interface ChatRequest {
  query: string; use_memory?: boolean
  query_message_id?: string
  source?: string
  source_metadata?: Record<string, string>
  workspace?: string; images?: ImageInput[]
  attachment_ids?: number[]
  history?: { id?: string; role: string; content: string }[]
}
export interface ImageInput { data_url: string; name?: string }
export interface AttachmentUploadResponse {
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
export interface ChatCitation {
  message_id: number; source: string; source_label: string; sender: string
  sender_avatar_url?: string; title: string; received_at: string; score: number
}
export interface ChatAction {
  kind: string; title: string; detail?: string
  payload?: Record<string, string>
}

export interface TodoItem {
  id: number; title: string; detail?: string; done: boolean
  due_at?: string; priority: string
  contact_id?: number; message_id?: number; updated_at: string
}

export interface BrowserConfirmRequest {
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
export interface BrowserConfirmResponse {
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
export interface BrowserLoginCheckpointItem {
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
export interface BrowserLoginCheckpointListResponse {
  total: number
  items: BrowserLoginCheckpointItem[]
  generated_at: string
}
export interface FileMemoryItem {
  path: string; title: string; preview: string; score: number
  updated_at: string; canonical_id: string; target: string
  source: string; kind: string; topic_path: string; entry_kind: string
}
export interface FileMemorySearchResponse {
  workspace: string; total: number; items: FileMemoryItem[]; generated_at: string
}
export interface FileMemoryContentResponse {
  workspace: string; path: string; title: string
  source: string; kind: string; topic_path: string; entry_kind: string
  updated_at: string; content: string; generated_at: string
}

/* ─── Device Center ─── */
export interface DeviceCapabilitiesResponse {
  platform: string; capabilities: Record<string, boolean>
  notes: string[]; generated_at: string
}
export interface DeviceScreenCaptureResponse {
  data_url: string
  name: string
  width: number
  height: number
  source_display: string
  captured_at: string
  generated_at: string
}
export interface DeviceScreenCaptureRequest {
  mode?: 'fullscreen' | 'region'
  display_id?: string
  max_edge?: number
  image_format?: 'jpeg' | 'png'
  quality?: number
  selection_timeout_ms?: number
}

/* ─── Agent ─── */
export interface AgentConfigOut {
  provider: string; base_url: string; model: string
  temperature: number; verify_ssl: boolean; has_api_key: boolean
  web_search_proxy_url: string
}
export interface AgentConfigUpdate {
  provider?: string; base_url?: string; model?: string
  temperature?: number; verify_ssl?: boolean; api_key?: string
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
