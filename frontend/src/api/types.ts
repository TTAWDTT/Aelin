export type IsoDateTime = string;

export type AelinToolStep = {
  stage: string;
  status: "completed" | "failed" | "skipped" | string;
  detail?: string;
  count?: number;
  ts?: number;
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
  detail?: string;
  payload?: Record<string, string>;
};

export type AelinChatRequest = {
  query: string;
  use_memory?: boolean;
  max_citations?: number;
  workspace?: string;
  search_mode?: "auto" | "local" | "web" | string;
  history?: { role: "user" | "assistant"; content: string }[];
  images?: { data_url: string; name?: string }[];
};

export type AelinChatResponse = {
  answer: string;
  expression: string;
  citations: AelinCitation[];
  actions: AelinAction[];
  tool_trace: AelinToolStep[];
  memory_summary: string;
  generated_at: IsoDateTime;
};

export type Contact = {
  id: number;
  display_name: string;
  handle: string;
  avatar_url?: string | null;
  unread_count: number;
  latest_subject?: string | null;
  latest_preview?: string | null;
  latest_source?: string | null;
  latest_received_at?: string | null;
};

export type MessageOut = {
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

export type ModelCatalogProvider = {
  id: string;
  label?: string;
  api?: string;
  models: { id: string; label?: string }[];
};

export type ModelCatalogResponse = {
  providers: ModelCatalogProvider[];
  generated_at?: string;
};

export type AelinContextResponse = {
  workspace: string;
  summary: string;
  notes_count: number;
  generated_at: string;
  notifications: { id: string; title: string; detail?: string; kind?: string; created_at?: string }[];
  focus_items: { message_id: number; title: string; source_label: string; sender: string; received_at: string; score: number }[];
  todos: { id: number; title: string; done: boolean; updated_at: string }[];
  pin_recommendations: { contact_id: number; display_name: string; score: number; unread_count: number; reasons: string[] }[];
  memory_layers: any;
};

export type TrackingListResponse = {
  total: number;
  items: TrackingItem[];
  generated_at: string;
};

export type TrackingItem = {
  target_id?: number | null;
  target: string;
  source: string;
  query?: string;
  workspace: string;
  status: string;
  unread_changes: number;
  next_run_at?: string | null;
  last_run_at?: string | null;
  updated_at: string;
  notify_level?: string;
};

