import { fetchJson, patchJson, postJson } from "./client";
import { fetchEventStream } from "./sse";
import type {
  AelinChatRequest,
  AelinChatResponse,
  AelinContextResponse,
  AgentConfig,
  Contact,
  MessageDetail,
  MessageOut,
  ModelCatalogResponse,
  TrackingListResponse,
} from "./types";

export function getAelinContext(workspace: string) {
  const qs = new URLSearchParams();
  qs.set("workspace", workspace);
  return fetchJson<AelinContextResponse>(`/api/v1/aelin/context?${qs.toString()}`);
}

export async function aelinChatStream(
  payload: AelinChatRequest,
  onEvent: (evt: { event: string; data: any }) => void,
  signal?: AbortSignal,
) {
  await fetchEventStream(
    "/api/v1/aelin/chat/stream",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
    onEvent,
  );
}

export function aelinChat(payload: AelinChatRequest) {
  return postJson<AelinChatResponse>("/api/v1/aelin/chat", payload);
}

export function aelinConfirmTrack(payload: {
  target: string;
  source?: string;
  query?: string;
  workspace?: string;
  description?: string;
  tags?: string[];
  track_type?: string | null;
  interval_seconds?: number | null;
  notify_level?: string;
  is_temporary?: boolean;
  temporary_days?: number;
}) {
  return postJson<any>("/api/v1/aelin/track/confirm", payload);
}

export function listContacts(q?: string) {
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  qs.set("limit", "200");
  return fetchJson<Contact[]>(`/api/v1/contacts?${qs.toString()}`);
}

export function listContactMessages(contactId: number, beforeId?: number) {
  const qs = new URLSearchParams();
  qs.set("limit", "60");
  if (beforeId) qs.set("before_id", String(beforeId));
  return fetchJson<MessageOut[]>(`/api/v1/contacts/${contactId}/messages?${qs.toString()}`);
}

export function markContactRead(contactId: number) {
  return postJson<{ marked: number; contact_id: number }>(`/api/v1/contacts/${contactId}/mark-read`, {});
}

export function getMessage(messageId: number) {
  return fetchJson<MessageDetail>(`/api/v1/messages/${messageId}`);
}

export function listTrackings(workspace?: string, status?: string) {
  const qs = new URLSearchParams();
  qs.set("limit", "120");
  if (workspace) qs.set("workspace", workspace);
  if (status) qs.set("status", status);
  return fetchJson<TrackingListResponse>(`/api/v1/aelin/tracking?${qs.toString()}`);
}

export function getAgentConfig() {
  return fetchJson<AgentConfig>("/api/v1/agent/config");
}

export function getAgentCatalog(refresh: boolean) {
  const qs = new URLSearchParams();
  if (refresh) qs.set("refresh", "1");
  return fetchJson<ModelCatalogResponse>(`/api/v1/agent/catalog?${qs.toString()}`);
}

export function updateAgentConfig(payload: { provider: string; base_url?: string; model?: string; api_key?: string; temperature: number }) {
  return patchJson<AgentConfig>("/api/v1/agent/config", payload);
}

export function testAgent() {
  return postJson<{ ok: boolean; provider: string; message: string }>("/api/v1/agent/test", {});
}

