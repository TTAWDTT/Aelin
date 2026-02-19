export type TokenResponse = { access_token: string; token_type: string };

export type User = {
  id: number;
  email: string;
  avatar_url?: string | null;
  created_at: string;
};

export type ConnectedAccount = {
  id: number;
  provider: string;
  identifier: string;
  last_synced_at?: string | null;
  created_at: string;
};

export type Contact = {
  id: number;
  display_name: string;
  handle: string;
  avatar_url?: string | null;
  last_message_at?: string | null;
  unread_count: number;
  latest_subject?: string | null;
  latest_preview?: string | null;
  latest_source?: string | null;
  latest_received_at?: string | null;
};

export type Message = {
  id: number;
  contact_id: number;
  source: string;
  sender: string;
  subject: string;
  body_preview: string;
  received_at: string;
  is_read: boolean;
  summary?: string | null;
};

export type MessageDetail = {
  id: number;
  contact_id: number;
  source: string;
  sender: string;
  subject: string;
  body: string;
  received_at: string;
  is_read: boolean;
  summary?: string | null;
};

export type AgentConfig = {
  provider: string;
  base_url: string;
  model: string;
  temperature: number;
  has_api_key: boolean;
};

export type ModelInfo = {
  id: string;
  name: string;
  family?: string | null;
  reasoning?: boolean | null;
  tool_call?: boolean | null;
  temperature?: boolean | null;
};

export type ModelProviderInfo = {
  id: string;
  name: string;
  api?: string | null;
  doc?: string | null;
  env: string[];
  model_count: number;
  models: ModelInfo[];
};

export type ModelCatalogResponse = {
  source_url: string;
  fetched_at: string;
  providers: ModelProviderInfo[];
};

export type AgentMemoryNote = {
  id: number;
  kind: string;
  content: string;
  source?: string | null;
  updated_at: string;
};

export type AgentFocusItem = {
  message_id: number;
  source: string;
  source_label: string;
  sender: string;
  sender_avatar_url?: string | null;
  title: string;
  received_at: string;
  score: number;
};

export type AgentMemorySnapshot = {
  summary: string;
  notes: AgentMemoryNote[];
  focus_items: AgentFocusItem[];
};

export type AelinCitation = {
  message_id: number;
  source: string;
  source_label: string;
  sender: string;
  sender_avatar_url?: string | null;
  title: string;
  received_at: string;
  score: number;
};

export type AelinAction = {
  kind: string;
  title: string;
  detail: string;
  payload: Record<string, string>;
};

export type AelinToolStep = {
  stage: string;
  status: string;
  detail?: string;
  count?: number;
  ts?: number;
};

export type AelinSearchMode = "auto" | "local_only" | "web_only";

export type AelinImageInput = {
  data_url: string;
  name?: string;
};

export type AelinChatHistoryTurn = {
  role: "user" | "assistant";
  content: string;
};

export type AelinContextResponse = {
  workspace: string;
  summary: string;
  focus_items: AgentFocusItem[];
  notes: AgentMemoryNote[];
  notes_count: number;
  todos: AgentTodoItem[];
  pin_recommendations: AgentPinRecommendationItem[];
  daily_brief?: AgentDailyBrief | null;
  layout_cards: AgentCardLayoutItem[];
  memory_layers: AelinMemoryLayers;
  notifications: AelinNotificationItem[];
  generated_at: string;
};

export type AelinMemoryLayerItem = {
  id: string;
  layer: string;
  title: string;
  detail?: string;
  source?: string;
  confidence?: number;
  updated_at?: string;
  meta?: Record<string, string>;
};

export type AelinMemoryLayers = {
  facts: AelinMemoryLayerItem[];
  preferences: AelinMemoryLayerItem[];
  in_progress: AelinMemoryLayerItem[];
  generated_at: string;
};

export type AelinNotificationItem = {
  id: string;
  level: "info" | "warning" | "success" | "error" | "default" | string;
  title: string;
  detail?: string;
  source?: string;
  ts?: string;
  action_kind?: string | null;
  action_payload?: Record<string, string>;
};

export type AelinNotificationResponse = {
  total: number;
  items: AelinNotificationItem[];
  generated_at: string;
};

export type AelinProactivePollResponse = {
  workspace: string;
  total: number;
  items: AelinNotificationItem[];
  generated_at: string;
};

export type AelinDeviceProcessItem = {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_mb: number;
  status: string;
  username: string;
  create_time?: string | null;
  anomaly_score: number;
  anomaly_reasons: string[];
  safe_to_terminate: boolean;
};

export type AelinDeviceProcessResponse = {
  sort_by: string;
  total: number;
  items: AelinDeviceProcessItem[];
  platform: string;
  filter_context: Record<string, string>;
  empty_reason: string;
  generated_at: string;
};

export type AelinDeviceCapabilitiesResponse = {
  platform: string;
  capabilities: Record<string, boolean>;
  notes: string[];
  generated_at: string;
};

export type AelinDeviceProcessActionResponse = {
  pid: number;
  action: string;
  ok: boolean;
  detail: string;
  generated_at: string;
};

export type AelinDeviceModeApplyResponse = {
  mode: string;
  status: string;
  summary: string;
  steps: string[];
  warnings: string[];
  generated_at: string;
};

export type AelinDeviceOptimizeResponse = {
  optimized_count: number;
  affected_pids: number[];
  steps: string[];
  warnings: string[];
  generated_at: string;
};

export type AelinChatResponse = {
  answer: string;
  expression: string;
  citations: AelinCitation[];
  actions: AelinAction[];
  tool_trace: AelinToolStep[];
  memory_summary: string;
  generated_at: string;
};

export type AelinChatStreamEvent =
  | { type: "start"; payload: Record<string, unknown> }
  | { type: "trace"; step: AelinToolStep }
  | {
      type: "evidence";
      citation: AelinCitation;
      snippet?: string;
      query?: string;
      provider?: string;
      fetch_mode?: string;
      progress?: { query_index?: number; query_total?: number; evidence_count?: number };
    }
  | { type: "confirmed"; items: string[]; source_count?: number; sources?: string[] }
  | { type: "final"; result: AelinChatResponse }
  | { type: "error"; message: string }
  | { type: "done"; payload: Record<string, unknown> };

export type AelinTrackConfirmResponse = {
  status: string;
  message: string;
  provider?: string | null;
  target_id?: number | null;
  next_run_at?: string | null;
  actions: AelinAction[];
  generated_at: string;
};

export type AelinTrackingItem = {
  note_id?: number | null;
  message_id?: number | null;
  target_id?: number | null;
  target: string;
  source: string;
  query: string;
  workspace?: string;
  track_type?: string;
  description?: string;
  tags?: string[];
  status: string;
  interval_seconds?: number;
  notify_level?: string;
  unread_changes?: number;
  error_count?: number;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_checked_at?: string | null;
  last_change_at?: string | null;
  mute_until?: string | null;
  is_temporary?: boolean;
  expires_at?: string | null;
  updated_at: string;
  status_updated_at?: string | null;
};

export type AelinTrackingListResponse = {
  total: number;
  items: AelinTrackingItem[];
  generated_at: string;
};

export type AelinTrackingTargetUpdateRequest = {
  status?: "active" | "paused" | "error" | "deleted";
  interval_seconds?: number;
  notify_level?: "all" | "important" | "critical";
  mute_until?: string | null;
  description?: string;
  tags?: string[];
};

export type AelinTrackingRunResponse = {
  ok: boolean;
  message: string;
  generated_at: string;
};

export type AelinTrackingChangeItem = {
  id: number;
  target_id: number;
  change_type: string;
  severity: string;
  title: string;
  summary: string;
  diff_json: Record<string, unknown>;
  dedupe_key: string;
  notified: boolean;
  acked: boolean;
  created_at: string;
};

export type AelinTrackingChangeListResponse = {
  total: number;
  items: AelinTrackingChangeItem[];
  generated_at: string;
};

export type AelinTrackingSnapshotItem = {
  id: number;
  target_id: number;
  version_no: number;
  content_hash: string;
  fetch_status: string;
  fetch_error: string;
  fetched_at: string;
  normalized_payload_json: Record<string, unknown>;
};

export type AelinTrackingSnapshotListResponse = {
  total: number;
  items: AelinTrackingSnapshotItem[];
  generated_at: string;
};

export type AgentCardLayoutItem = {
  contact_id: number;
  display_name: string;
  pinned: boolean;
  order: number;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type AgentPinRecommendationItem = {
  contact_id: number;
  display_name: string;
  score: number;
  reasons: string[];
  unread_count: number;
  last_message_at?: string | null;
};

export type AgentPinRecommendationResponse = {
  generated_at: string;
  items: AgentPinRecommendationItem[];
};

export type AgentTodoItem = {
  id: number;
  title: string;
  detail: string;
  done: boolean;
  due_at?: string | null;
  priority: string;
  contact_id?: number | null;
  message_id?: number | null;
  updated_at: string;
};

export type AgentDailyBriefAction = {
  kind: string;
  title: string;
  detail: string;
  contact_id?: number | null;
  message_id?: number | null;
  priority: string;
};

export type AgentDailyBrief = {
  generated_at: string;
  summary: string;
  top_updates: AgentFocusItem[];
  actions: AgentDailyBriefAction[];
};

export type AgentAdvancedSearchItem = {
  message_id: number;
  contact_id: number;
  sender: string;
  subject: string;
  source: string;
  received_at: string;
  preview: string;
  is_read: boolean;
  score: number;
  reason: string;
};

export type AgentAdvancedSearchResponse = {
  total: number;
  items: AgentAdvancedSearchItem[];
};

export type AccountOAuthStart = {
  provider: string;
  auth_url: string;
};

export type OAuthProviderConfig = {
  provider: string;
  configured: boolean;
  client_id_hint?: string | null;
};

export type OAuthProvider = "gmail" | "outlook" | "github";

export type ForwardAccountInfo = {
  account_id: number;
  provider: string;
  identifier: string;
  source_email: string;
  forward_address: string;
  inbound_url: string;
};

const TOKEN_KEY = "mercurydesk_token";
const API_BASE_URL = String(import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");
const MOBILE_API_BASE_URL = String(import.meta.env.VITE_MOBILE_API_BASE_URL || "http://10.0.2.2:8000")
  .trim()
  .replace(/\/+$/, "");
let tokenCache: string | null | undefined;

function isNativeMobileShellRuntime(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return Boolean((window as any)?.Capacitor?.isNativePlatform?.());
  } catch {
    return false;
  }
}

function resolveApiUrl(path: string): string {
  const raw = String(path || "").trim();
  if (!raw) return raw;
  if (/^https?:\/\//i.test(raw)) return raw;
  const normalized = raw.startsWith("/") ? raw : `/${raw}`;
  if (API_BASE_URL) return `${API_BASE_URL}${normalized}`;
  if (isNativeMobileShellRuntime()) return `${MOBILE_API_BASE_URL}${normalized}`;
  return normalized;
}

export function getToken(): string | null {
  if (tokenCache === undefined) tokenCache = localStorage.getItem(TOKEN_KEY);
  return tokenCache;
}

export function setToken(token: string | null) {
  tokenCache = token;
  if (!token) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(resolveApiUrl(path), { ...init, headers });
  if (resp.status === 401) {
    setToken(null);
    if (typeof window !== "undefined") window.dispatchEvent(new Event("mercurydesk:unauthorized"));
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    let message = text || `HTTP ${resp.status}`;
    if (text) {
      try {
        const parsed = JSON.parse(text) as any;
        const detail = parsed?.detail;
        if (typeof detail === "string" && detail.trim()) message = detail;
      } catch {
        // ignore JSON parse errors
      }
    }
    throw new ApiError(message, resp.status);
  }
  return resp;
}

export async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await apiFetch(path, init);
  const text = await resp.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    const bodyStart = text.trimStart().slice(0, 80).toLowerCase();
    const contentType = (resp.headers.get("content-type") || "").toLowerCase();
    const resolved = resolveApiUrl(path);
    const maybeHtml = contentType.includes("text/html") || bodyStart.startsWith("<!doctype") || bodyStart.startsWith("<html");
    if (maybeHtml) {
      throw new ApiError(
        `API 返回了 HTML 而不是 JSON，请检查移动端接口地址配置（当前请求: ${resolved}）`,
        resp.status || 500
      );
    }
    throw new ApiError(`接口返回了无法解析的 JSON（请求: ${resolved}）`, resp.status || 500);
  }
}

export async function register(email: string, password: string) {
  await fetchJson("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  return await fetchJson<TokenResponse>("/api/v1/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
}

export async function listAccounts(): Promise<ConnectedAccount[]> {
  return await fetchJson<ConnectedAccount[]>("/api/v1/accounts");
}

export async function createAccount(payload: {
  provider: string;
  identifier: string;
  access_token?: string | null;
  refresh_token?: string | null;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_use_ssl?: boolean | null;
  imap_username?: string | null;
  imap_password?: string | null;
  imap_mailbox?: string | null;
  feed_url?: string | null;
  feed_homepage_url?: string | null;
  feed_display_name?: string | null;
  bilibili_uid?: string | null;
  x_username?: string | null;
  forward_display_name?: string | null;
  forward_source_email?: string | null;
}): Promise<ConnectedAccount> {
  return await fetchJson<ConnectedAccount>("/api/v1/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function deleteAccount(accountId: number): Promise<void> {
  await apiFetch(`/api/v1/accounts/${accountId}`, { method: "DELETE" });
}

export async function startAccountOAuth(provider: OAuthProvider): Promise<AccountOAuthStart> {
  return await fetchJson<AccountOAuthStart>(`/api/v1/accounts/oauth/${provider}/start`);
}

export async function getOAuthProviderConfig(provider: OAuthProvider): Promise<OAuthProviderConfig> {
  return await fetchJson<OAuthProviderConfig>(`/api/v1/accounts/oauth/${provider}/config`);
}

export async function updateOAuthProviderConfig(
  provider: OAuthProvider,
  payload: { client_id: string; client_secret: string }
): Promise<OAuthProviderConfig> {
  return await fetchJson<OAuthProviderConfig>(`/api/v1/accounts/oauth/${provider}/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function getForwardAccountInfo(accountId: number): Promise<ForwardAccountInfo> {
  return await fetchJson<ForwardAccountInfo>(`/api/v1/accounts/${accountId}/forward-info`);
}

export async function getProfile(): Promise<User> {
  return await fetchJson<User>("/api/v1/auth/me");
}

export async function updateProfile(payload: {
  email?: string;
  password?: string;
  avatar_url?: string;
}): Promise<User> {
  return await fetchJson<User>("/api/v1/auth/me", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function uploadAvatar(file: File): Promise<User> {
  const body = new FormData();
  body.set("file", file);
  const resp = await apiFetch("/api/v1/auth/me/avatar", { method: "POST", body });
  return (await resp.json()) as User;
}

type SyncJobStart = {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  account_id: number;
};

type SyncJobStatus = {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  account_id: number;
  inserted?: number | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

const waitFor = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForSyncJob(jobId: string, timeoutMs = 180_000): Promise<{ inserted: number; account_id: number }> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await fetchJson<SyncJobStatus>(`/api/v1/accounts/sync-jobs/${jobId}`);
    if (job.status === "succeeded") {
      return { inserted: Number(job.inserted || 0), account_id: job.account_id };
    }
    if (job.status === "failed") {
      throw new ApiError(job.error?.trim() || "同步失败", 500);
    }
    await waitFor(900);
  }
  throw new ApiError("同步超时，请稍后重试", 408);
}

export async function syncAccount(accountId: number, forceFull = false) {
  const qs = forceFull ? '?force_full=true' : '';
  const result = await fetchJson<{ inserted: number; account_id: number } | SyncJobStart>(`/api/v1/accounts/${accountId}/sync${qs}`, {
    method: "POST"
  });
  if ("inserted" in result) return result;
  return waitForSyncJob(result.job_id);
}

export async function listContacts(params?: { q?: string; limit?: number; offset?: number }): Promise<Contact[]> {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return await fetchJson<Contact[]>(`/api/v1/contacts${suffix}`);
}

export async function listMessages(params: {
  contactId: number;
  limit?: number;
  before_id?: number;
}): Promise<Message[]> {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.before_id) qs.set("before_id", String(params.before_id));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return await fetchJson<Message[]>(`/api/v1/contacts/${params.contactId}/messages${suffix}`);
}

export async function getMessage(messageId: number): Promise<MessageDetail> {
  return await fetchJson<MessageDetail>(`/api/v1/messages/${messageId}`);
}

export async function markContactRead(contactId: number): Promise<{ marked: number; contact_id: number }> {
  return await fetchJson<{ marked: number; contact_id: number }>(`/api/v1/contacts/${contactId}/mark-read`, {
    method: "POST"
  });
}

export async function agentSummarize(text: string): Promise<{ summary: string }> {
  return await fetchJson<{ summary: string }>("/api/v1/agent/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
}

export async function agentDraftReply(text: string, tone: string): Promise<{ draft: string }> {
  return await fetchJson<{ draft: string }>("/api/v1/agent/draft-reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, tone })
  });
}

export async function getAgentConfig(): Promise<AgentConfig> {
  return await fetchJson<AgentConfig>("/api/v1/agent/config");
}

export async function updateAgentConfig(payload: {
  provider?: string;
  base_url?: string;
  model?: string;
  temperature?: number;
  api_key?: string;
}): Promise<AgentConfig> {
  return await fetchJson<AgentConfig>("/api/v1/agent/config", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function testAgent(): Promise<{ ok: boolean; provider: string; message: string }> {
  return await fetchJson<{ ok: boolean; provider: string; message: string }>("/api/v1/agent/test", {
    method: "POST"
  });
}

async function* streamFetch(path: string, init: RequestInit = {}, signal?: AbortSignal): AsyncGenerator<string, void, unknown> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(resolveApiUrl(path), { ...init, headers, signal });
  if (!response.ok) {
      const text = await response.text();
      let msg = text;
      try {
          const json = JSON.parse(text);
          if (json.detail) msg = json.detail;
      } catch {}
      throw new Error(msg || response.statusText);
  }
  if (!response.body) return;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}

async function* streamSSE(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal
): AsyncGenerator<{ event: string; data: string }, void, unknown> {
  let buffer = "";
  for await (const chunk of streamFetch(path, init, signal)) {
    buffer += chunk.replace(/\r\n/g, "\n");
    while (true) {
      const sep = buffer.indexOf("\n\n");
      if (sep < 0) break;
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (!block.trim()) continue;
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) {
          event = line.slice(6).trim() || "message";
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      yield { event, data: dataLines.join("\n") };
    }
  }
}

export async function* agentSummarizeStream(text: string, signal?: AbortSignal): AsyncGenerator<string, void, unknown> {
  yield* streamFetch("/api/v1/agent/summarize/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  }, signal);
}

export async function* agentDraftReplyStream(text: string, tone: string, signal?: AbortSignal): AsyncGenerator<string, void, unknown> {
  yield* streamFetch("/api/v1/agent/draft-reply/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, tone })
  }, signal);
}

export async function getAgentCatalog(forceRefresh = false): Promise<ModelCatalogResponse> {
  const qs = forceRefresh ? "?force_refresh=true" : "";
  return await fetchJson<ModelCatalogResponse>(`/api/v1/agent/catalog${qs}`);
}

export async function* agentChatStream(
  messages: { role: string; content: string }[],
  contextContactId?: number,
  signal?: AbortSignal,
  options?: { tools?: string[]; use_memory?: boolean }
): AsyncGenerator<string, void, unknown> {
  yield* streamFetch("/api/v1/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      context_contact_id: contextContactId,
      tools: options?.tools ?? [],
      use_memory: options?.use_memory ?? true,
    })
  }, signal);
}

export async function getAelinContext(workspace = "default", query = ""): Promise<AelinContextResponse> {
  const qs = new URLSearchParams();
  if (workspace.trim()) qs.set("workspace", workspace.trim());
  if (query.trim()) qs.set("query", query.trim());
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return await fetchJson<AelinContextResponse>(`/api/v1/aelin/context${suffix}`);
}

export async function aelinChat(
  query: string,
  options?: {
    use_memory?: boolean;
    max_citations?: number;
    workspace?: string;
    images?: AelinImageInput[];
    history?: AelinChatHistoryTurn[];
    search_mode?: AelinSearchMode;
  }
): Promise<AelinChatResponse> {
  return await fetchJson<AelinChatResponse>("/api/v1/aelin/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      use_memory: options?.use_memory ?? true,
      max_citations: options?.max_citations ?? 6,
      workspace: options?.workspace?.trim() || "default",
      images: (options?.images || []).slice(0, 4).map((item) => ({
        data_url: item.data_url,
        name: item.name || "",
      })),
      history: (options?.history || [])
        .filter((item) => item && (item.role === "user" || item.role === "assistant") && String(item.content || "").trim())
        .slice(-12)
        .map((item) => ({
          role: item.role,
          content: String(item.content || "").trim(),
        })),
      search_mode: options?.search_mode || "auto",
    }),
  });
}

export async function* aelinChatStream(
  query: string,
  options?: {
    use_memory?: boolean;
    max_citations?: number;
    workspace?: string;
    images?: AelinImageInput[];
    history?: AelinChatHistoryTurn[];
    search_mode?: AelinSearchMode;
  },
  signal?: AbortSignal
): AsyncGenerator<AelinChatStreamEvent, void, unknown> {
  const body = JSON.stringify({
    query,
    use_memory: options?.use_memory ?? true,
    max_citations: options?.max_citations ?? 6,
    workspace: options?.workspace?.trim() || "default",
    images: (options?.images || []).slice(0, 4).map((item) => ({
      data_url: item.data_url,
      name: item.name || "",
    })),
    history: (options?.history || [])
      .filter((item) => item && (item.role === "user" || item.role === "assistant") && String(item.content || "").trim())
      .slice(-12)
      .map((item) => ({
        role: item.role,
        content: String(item.content || "").trim(),
      })),
    search_mode: options?.search_mode || "auto",
  });

  for await (const packet of streamSSE(
    "/api/v1/aelin/chat/stream",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    },
    signal
  )) {
    let parsed: any = {};
    if ((packet.data || "").trim()) {
      try {
        parsed = JSON.parse(packet.data);
      } catch {
        parsed = {};
      }
    }
    if (packet.event === "start") {
      yield { type: "start", payload: (parsed || {}) as Record<string, unknown> };
      continue;
    }
    if (packet.event === "trace") {
      const step = parsed?.step;
      if (step && typeof step === "object" && typeof step.stage === "string") {
        yield { type: "trace", step: step as AelinToolStep };
      }
      continue;
    }
    if (packet.event === "evidence") {
      const citation = parsed?.citation;
      if (citation && typeof citation === "object" && typeof citation.source === "string") {
        yield {
          type: "evidence",
          citation: citation as AelinCitation,
          snippet: typeof parsed?.snippet === "string" ? parsed.snippet : "",
          query: typeof parsed?.query === "string" ? parsed.query : "",
          provider: typeof parsed?.provider === "string" ? parsed.provider : "",
          fetch_mode: typeof parsed?.fetch_mode === "string" ? parsed.fetch_mode : "",
          progress: (parsed?.progress && typeof parsed.progress === "object")
            ? (parsed.progress as { query_index?: number; query_total?: number; evidence_count?: number })
            : undefined,
        };
      }
      continue;
    }
    if (packet.event === "confirmed") {
      const items = Array.isArray(parsed?.items) ? parsed.items.filter((x: unknown) => typeof x === "string") as string[] : [];
      yield {
        type: "confirmed",
        items,
        source_count: Number(parsed?.source_count || 0) || 0,
        sources: Array.isArray(parsed?.sources) ? parsed.sources.filter((x: unknown) => typeof x === "string") as string[] : [],
      };
      continue;
    }
    if (packet.event === "final") {
      const result = parsed?.result;
      if (result && typeof result === "object" && typeof result.answer === "string") {
        yield { type: "final", result: result as AelinChatResponse };
      }
      continue;
    }
    if (packet.event === "error") {
      const message = String(parsed?.message || "stream error").trim() || "stream error";
      yield { type: "error", message };
      continue;
    }
    if (packet.event === "done") {
      yield { type: "done", payload: (parsed || {}) as Record<string, unknown> };
      continue;
    }
  }
}

export async function aelinConfirmTrack(payload: {
  target: string;
  source?: string;
  query?: string;
  workspace?: string;
  description?: string;
  tags?: string[];
  track_type?: "term" | "url";
  interval_seconds?: number;
  notify_level?: "all" | "important" | "critical";
  is_temporary?: boolean;
  temporary_days?: number;
}): Promise<AelinTrackConfirmResponse> {
  return await fetchJson<AelinTrackConfirmResponse>("/api/v1/aelin/track/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: payload.target,
      source: payload.source || "auto",
      query: payload.query || "",
      workspace: payload.workspace || "default",
      description: payload.description || "",
      tags: (payload.tags || []).filter((tag) => String(tag || "").trim()).slice(0, 20),
      track_type: payload.track_type,
      interval_seconds: payload.interval_seconds,
      notify_level: payload.notify_level || "all",
      is_temporary: Boolean(payload.is_temporary),
      temporary_days: payload.temporary_days,
    }),
  });
}

export async function getAelinTracking(
  limitOrOptions:
    | number
    | {
        limit?: number;
        workspace?: string;
        status?: string;
      } = 80
): Promise<AelinTrackingListResponse> {
  const opts =
    typeof limitOrOptions === "number"
      ? { limit: limitOrOptions }
      : (limitOrOptions || {});
  const safeLimit = Number.isFinite(opts.limit || 0)
    ? Math.max(1, Math.min(300, Math.floor(Number(opts.limit || 80))))
    : 80;
  const qs = new URLSearchParams();
  qs.set("limit", String(safeLimit));
  if (String(opts.workspace || "").trim()) qs.set("workspace", String(opts.workspace).trim());
  if (String(opts.status || "").trim()) qs.set("status", String(opts.status).trim());
  return await fetchJson<AelinTrackingListResponse>(`/api/v1/aelin/tracking?${qs.toString()}`);
}

export async function updateAelinTrackingTarget(
  targetId: number,
  payload: AelinTrackingTargetUpdateRequest
): Promise<AelinTrackingItem> {
  return await fetchJson<AelinTrackingItem>(`/api/v1/aelin/tracking/targets/${targetId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function runAelinTrackingTarget(targetId: number): Promise<AelinTrackingRunResponse> {
  return await fetchJson<AelinTrackingRunResponse>(`/api/v1/aelin/tracking/targets/${targetId}/run`, {
    method: "POST",
  });
}

export async function listAelinTrackingChanges(
  targetId: number,
  options?: { limit?: number; severity?: string; change_type?: string; acked?: boolean }
): Promise<AelinTrackingChangeListResponse> {
  const qs = new URLSearchParams();
  const safeLimit = Number.isFinite(options?.limit || 0)
    ? Math.max(1, Math.min(300, Math.floor(Number(options?.limit || 80))))
    : 80;
  qs.set("limit", String(safeLimit));
  if (String(options?.severity || "").trim()) qs.set("severity", String(options?.severity || "").trim());
  if (String(options?.change_type || "").trim()) qs.set("change_type", String(options?.change_type || "").trim());
  if (typeof options?.acked === "boolean") qs.set("acked", options.acked ? "true" : "false");
  return await fetchJson<AelinTrackingChangeListResponse>(
    `/api/v1/aelin/tracking/targets/${targetId}/changes?${qs.toString()}`
  );
}

export async function ackAelinTrackingChange(changeId: number): Promise<AelinTrackingRunResponse> {
  return await fetchJson<AelinTrackingRunResponse>(`/api/v1/aelin/tracking/changes/${changeId}/ack`, {
    method: "POST",
  });
}

export async function listAelinTrackingSnapshots(
  targetId: number,
  limit = 80
): Promise<AelinTrackingSnapshotListResponse> {
  const safeLimit = Number.isFinite(limit) ? Math.max(1, Math.min(300, Math.floor(limit))) : 80;
  return await fetchJson<AelinTrackingSnapshotListResponse>(
    `/api/v1/aelin/tracking/targets/${targetId}/snapshots?limit=${safeLimit}`
  );
}

export async function getAelinNotifications(limit = 24): Promise<AelinNotificationResponse> {
  const safeLimit = Number.isFinite(limit) ? Math.max(1, Math.min(100, Math.floor(limit))) : 24;
  return await fetchJson<AelinNotificationResponse>(`/api/v1/aelin/notifications?limit=${safeLimit}`);
}

export async function getAelinProactivePoll(workspace = "default", limit = 8): Promise<AelinProactivePollResponse> {
  const safeLimit = Number.isFinite(limit) ? Math.max(1, Math.min(24, Math.floor(limit))) : 8;
  const qs = new URLSearchParams();
  if (workspace.trim()) qs.set("workspace", workspace.trim());
  qs.set("limit", String(safeLimit));
  return await fetchJson<AelinProactivePollResponse>(`/api/v1/aelin/proactive/poll?${qs.toString()}`);
}

export async function getAelinDeviceProcesses(
  sortBy: "cpu" | "memory" = "cpu",
  limit = 40
): Promise<AelinDeviceProcessResponse> {
  const safeLimit = Number.isFinite(limit) ? Math.max(1, Math.min(200, Math.floor(limit))) : 40;
  const sort = sortBy === "memory" ? "memory" : "cpu";
  return await fetchJson<AelinDeviceProcessResponse>(
    `/api/v1/aelin/device/processes?sort_by=${sort}&limit=${safeLimit}`
  );
}

export async function runAelinDeviceProcessAction(
  pid: number,
  action: "terminate" | "set_low_priority" | "set_high_priority"
): Promise<AelinDeviceProcessActionResponse> {
  return await fetchJson<AelinDeviceProcessActionResponse>(`/api/v1/aelin/device/processes/${pid}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
}

export async function optimizeAelinDeviceProcesses(): Promise<AelinDeviceOptimizeResponse> {
  return await fetchJson<AelinDeviceOptimizeResponse>("/api/v1/aelin/device/processes/optimize", {
    method: "POST",
  });
}

export async function getAelinDeviceCapabilities(): Promise<AelinDeviceCapabilitiesResponse> {
  return await fetchJson<AelinDeviceCapabilitiesResponse>("/api/v1/aelin/device/capabilities");
}

export async function getAelinDeviceMode(): Promise<AelinDeviceModeApplyResponse> {
  return await fetchJson<AelinDeviceModeApplyResponse>("/api/v1/aelin/device/mode");
}

export async function applyAelinDeviceMode(
  mode: "meeting" | "focus" | "sleep" | "normal"
): Promise<AelinDeviceModeApplyResponse> {
  return await fetchJson<AelinDeviceModeApplyResponse>("/api/v1/aelin/device/mode/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
}

export async function getAgentMemory(query = ""): Promise<AgentMemorySnapshot> {
  const qs = query.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
  return await fetchJson<AgentMemorySnapshot>(`/api/v1/agent/memory${qs}`);
}

export async function addAgentMemoryNote(content: string, kind = "note"): Promise<AgentMemoryNote> {
  return await fetchJson<AgentMemoryNote>("/api/v1/agent/memory/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, kind }),
  });
}

export async function deleteAgentMemoryNote(noteId: number): Promise<{ deleted: boolean; note_id: number }> {
  return await fetchJson<{ deleted: boolean; note_id: number }>(`/api/v1/agent/memory/notes/${noteId}`, {
    method: "DELETE",
  });
}

export async function syncAgentCardLayout(
  cards: AgentCardLayoutItem[],
  workspace = "default"
): Promise<{ ok: boolean; note_id: number; count: number }> {
  return await fetchJson<{ ok: boolean; note_id: number; count: number }>("/api/v1/agent/memory/layout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cards, workspace }),
  });
}

export async function getPinRecommendations(limit = 6): Promise<AgentPinRecommendationResponse> {
  return await fetchJson<AgentPinRecommendationResponse>(`/api/v1/agent/pin-recommendations?limit=${Math.max(1, Math.min(20, limit))}`);
}

export async function getDailyBrief(): Promise<AgentDailyBrief> {
  return await fetchJson<AgentDailyBrief>("/api/v1/agent/daily-brief");
}

export async function listAgentTodos(includeDone = true): Promise<AgentTodoItem[]> {
  const qs = includeDone ? "" : "?include_done=false";
  return await fetchJson<AgentTodoItem[]>(`/api/v1/agent/todos${qs}`);
}

export async function createAgentTodo(payload: {
  title: string;
  detail?: string;
  due_at?: string;
  priority?: string;
  contact_id?: number;
  message_id?: number;
}): Promise<AgentTodoItem> {
  return await fetchJson<AgentTodoItem>("/api/v1/agent/todos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateAgentTodo(
  todoId: number,
  payload: { done?: boolean; title?: string; detail?: string; due_at?: string; priority?: string }
): Promise<AgentTodoItem> {
  return await fetchJson<AgentTodoItem>(`/api/v1/agent/todos/${todoId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteAgentTodo(todoId: number): Promise<{ deleted: boolean; todo_id: number }> {
  return await fetchJson<{ deleted: boolean; todo_id: number }>(`/api/v1/agent/todos/${todoId}`, {
    method: "DELETE",
  });
}

export async function advancedSearch(payload: {
  query?: string;
  source?: string;
  unread_only?: boolean;
  days?: number;
  limit?: number;
}): Promise<AgentAdvancedSearchResponse> {
  return await fetchJson<AgentAdvancedSearchResponse>("/api/v1/agent/search/advanced", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// X API Configuration
export type XApiConfig = {
  configured: boolean;
  token_hint?: string | null;
  cookies_configured?: boolean;
  message?: string | null;
};

export async function getXApiConfig(): Promise<XApiConfig> {
  return await fetchJson<XApiConfig>("/api/v1/accounts/x/config");
}

export async function updateXApiConfig(bearerToken: string): Promise<XApiConfig> {
  return await fetchJson<XApiConfig>("/api/v1/accounts/x/config", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bearer_token: bearerToken }),
  });
}

export async function updateXAuthCookies(authToken: string, ct0: string): Promise<{ cookies_configured: boolean; message: string }> {
  return await fetchJson("/api/v1/accounts/x/cookies", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auth_token: authToken, ct0 }),
  });
}

export async function deleteXAuthCookies(): Promise<{ cookies_configured: boolean; message: string }> {
  return await fetchJson("/api/v1/accounts/x/cookies", {
    method: "DELETE",
  });
}
