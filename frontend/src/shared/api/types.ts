/* ─── Auth ─── */
export interface Token { access_token: string; token_type: string }
export interface UserCreate { email: string; password: string }
export interface UserUpdate { email?: string; password?: string; avatar_url?: string }
export interface UserOut { id: number; email: string; avatar_url?: string; created_at: string }

/* ─── Chat ─── */
export interface ChatRequest {
  query: string; use_memory?: boolean
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
export interface ChatCitation {
  message_id: number; source: string; source_label: string; sender: string
  sender_avatar_url?: string; title: string; received_at: string; score: number
}
export interface ChatAction {
  kind: string; title: string; detail?: string
  payload?: Record<string, string>
}

export type DeepAgentsExecutionEventKind =
  | 'system'
  | 'model'
  | 'task'
  | 'tool'
  | 'state'
  | 'final'
  | 'error'

export interface DeepAgentsExecutionEvent {
  id: string
  type: string
  kind: DeepAgentsExecutionEventKind
  title: string
  summary?: string
  status?: string
  node?: string
  ns?: string[]
  ts: number
  metadata?: Record<string, unknown>
}

export type AelinChatRequest = ChatRequest
export type AelinCitation = ChatCitation
export type AelinAction = ChatAction

/* ─── Aelin Context ─── */
export interface AgentMemoryNoteOut { id: number; kind: string; content: string; source?: string; updated_at: string }
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
export interface AelinContextResponse {
  workspace: string; summary: string
  notes: AgentMemoryNoteOut[]; notes_count: number
  todos: AelinTodoItem[]
  memory_layers: AelinMemoryLayers
  generated_at: string
}

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

/* ─── Device Center ─── */
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
