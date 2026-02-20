import React from "react";

import {
  AelinCitation,
  AelinContextResponse,
  AelinToolStep,
} from "../../api";
import {
  AELIN_CHAT_STORAGE_KEY,
  AELIN_SESSIONS_STORAGE_KEY,
  MAX_PERSISTED_IMAGE_DATA_URL,
  MAX_PERSISTED_MESSAGES,
  MAX_PERSISTED_SESSIONS,
} from "./constants";
import {
  nextMessageId,
  normalizeExpressionId,
} from "./helpers";
import {
  ChatMessage,
  ChatSession,
  GroupedMessage,
} from "./types";

export function initialMessages(): ChatMessage[] {
  return [
    {
      id: nextMessageId(),
      role: "assistant",
      content: "我是 Aelin。告诉我你想追踪什么，我会基于你的长期信号来回答。",
      expression: "exp-04",
      ts: Date.now(),
    },
  ];
}

export function deriveSessionTitle(messages: ChatMessage[]): string {
  const user = messages.find((item) => item.role === "user" && item.content.trim());
  if (!user) return "新对话";
  const first = user.content.trim().split("\n")[0] || "新对话";
  return first.length > 22 ? `${first.slice(0, 22)}…` : first;
}

export function newSession(messages?: ChatMessage[]): ChatSession {
  const payload = messages && messages.length ? messages : initialMessages();
  return {
    id: nextMessageId(),
    title: deriveSessionTitle(payload),
    messages: payload,
    updated_at: Date.now(),
  };
}

export function normalizeTraceStep(step: AelinToolStep): AelinToolStep {
  const rawTs = Number(step.ts || 0);
  const safeTs = Number.isFinite(rawTs) && rawTs > 0 ? Math.floor(rawTs) : 0;
  return {
    stage: (step.stage || "stage").toLowerCase(),
    status: (step.status || "completed").toLowerCase(),
    detail: step.detail || "",
    count: Number(step.count || 0),
    ts: safeTs,
  };
}

export function upsertTraceStep(steps: AelinToolStep[], incoming: AelinToolStep): AelinToolStep[] {
  const next = normalizeTraceStep(incoming);
  const base = (steps || []).map(normalizeTraceStep);
  const idx = base.findIndex((item) => item.stage === next.stage);
  if (idx >= 0) {
    const prev = base[idx];
    const prevTs = Number(prev.ts || 0);
    const nextTs = Number(next.ts || 0);
    base[idx] = {
      ...next,
      ts: nextTs > 0 ? nextTs : prevTs > 0 ? prevTs : Date.now(),
    };
  } else {
    const nextTs = Number(next.ts || 0);
    base.push({
      ...next,
      ts: nextTs > 0 ? nextTs : Date.now(),
    });
  }
  base.sort((a, b) => {
    const ta = Number(a.ts || 0);
    const tb = Number(b.ts || 0);
    if (ta > 0 && tb > 0 && ta !== tb) return ta - tb;
    if (ta > 0 && tb <= 0) return -1;
    if (ta <= 0 && tb > 0) return 1;
    return a.stage.localeCompare(b.stage);
  });
  return base.slice(-64);
}

export function mergeCitations(existing: AelinCitation[], incoming: AelinCitation[], limit = 12): AelinCitation[] {
  const out: AelinCitation[] = [];
  const seen = new Set<string>();
  for (const row of [...(existing || []), ...(incoming || [])]) {
    const key = `${row.message_id || 0}:${row.source || ""}:${row.title || ""}`.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
    if (out.length >= limit) break;
  }
  return out;
}

function citationKey(item: Pick<AelinCitation, "message_id" | "source" | "title">): string {
  return `${item.message_id || 0}:${item.source || ""}:${item.title || ""}`.toLowerCase();
}

export function mergeCitationSnippets(
  existing: Record<string, string> | undefined,
  incoming: Array<{ citation: AelinCitation; snippet?: string }>
): Record<string, string> {
  const out: Record<string, string> = { ...(existing || {}) };
  for (const row of incoming) {
    const key = citationKey(row.citation);
    const snippet = String(row.snippet || "").trim();
    if (!key || !snippet) continue;
    out[key] = snippet.slice(0, 300);
  }
  return out;
}

export function buildStoryFromContext(ctx: AelinContextResponse | null): string {
  if (!ctx) return "当前没有足够数据来生成故事模式。先同步一些信号后再试。";
  const now = Date.now();
  const in24h = (ctx.focus_items || []).filter((item) => {
    const ts = Date.parse((item.received_at || "").replace(" ", "T"));
    if (Number.isNaN(ts)) return true;
    return now - ts <= 24 * 60 * 60 * 1000;
  });
  const top = (in24h.length ? in24h : ctx.focus_items || []).slice(0, 6);
  if (!top.length) return "最近24小时没有足够信号，暂时无法生成故事模式。";
  const part1 = top.slice(0, 2).map((x) => `- ${x.title}（${x.source_label}）`).join("\n");
  const part2 = top.slice(2, 4).map((x) => `- ${x.title}（${x.sender}）`).join("\n");
  const part3 = top.slice(4, 6).map((x) => `- ${x.title}`).join("\n");
  return [
    "### 24h 故事模式",
    "第一幕：发生了什么",
    part1 || "- 暂无",
    "",
    "第二幕：为什么值得关注",
    part2 || "- 暂无",
    "",
    "第三幕：接下来你可以做什么",
    part3 || "- 建议继续观察",
  ].join("\n");
}

export function loadPersistedMessages(): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(AELIN_CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { messages?: unknown } | unknown;
    const list =
      parsed && typeof parsed === "object" && "messages" in parsed
        ? (parsed as { messages?: unknown }).messages
        : parsed;
    if (!Array.isArray(list)) return [];
    const restored: ChatMessage[] = [];
    for (const item of list) {
      if (!item || typeof item !== "object") continue;
      const rawMessage = item as Partial<ChatMessage>;
      if (rawMessage.role !== "user" && rawMessage.role !== "assistant") continue;
      if (typeof rawMessage.content !== "string") continue;
      if (typeof rawMessage.ts !== "number" || Number.isNaN(rawMessage.ts)) continue;
      const images = Array.isArray(rawMessage.images)
        ? rawMessage.images
            .filter((img) => !!img && typeof img === "object" && typeof img.data_url === "string")
            .slice(0, 4)
            .map((img) => ({ data_url: img.data_url, name: img.name }))
        : undefined;
      const toolTrace = Array.isArray(rawMessage.tool_trace)
        ? rawMessage.tool_trace
            .filter((step) => !!step && typeof step === "object" && typeof (step as AelinToolStep).stage === "string")
            .map((step) => normalizeTraceStep(step as AelinToolStep))
            .slice(0, 8)
        : undefined;
      const citationSnippets =
        rawMessage.citation_snippets && typeof rawMessage.citation_snippets === "object"
          ? Object.fromEntries(
              Object.entries(rawMessage.citation_snippets as Record<string, unknown>)
                .filter(([k, v]) => !!k && typeof v === "string")
                .slice(0, 24)
                .map(([k, v]) => [k, String(v).slice(0, 300)])
            )
          : undefined;
      restored.push({
        id: typeof rawMessage.id === "string" && rawMessage.id ? rawMessage.id : nextMessageId(),
        role: rawMessage.role,
        content: rawMessage.content,
        ts: rawMessage.ts,
        expression: normalizeExpressionId(typeof rawMessage.expression === "string" ? rawMessage.expression : ""),
        citations: Array.isArray(rawMessage.citations) ? rawMessage.citations : undefined,
        citation_snippets: citationSnippets,
        actions: Array.isArray(rawMessage.actions) ? rawMessage.actions : undefined,
        images,
        tool_trace: toolTrace,
      });
    }
    return restored.slice(-MAX_PERSISTED_MESSAGES);
  } catch {
    return [];
  }
}

export function toPersistedMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .filter((item) => !item.pending)
    .slice(-MAX_PERSISTED_MESSAGES)
    .map((item) => {
      const images = Array.isArray(item.images)
        ? item.images
            .filter((img) => img.data_url.length <= MAX_PERSISTED_IMAGE_DATA_URL)
            .slice(0, 4)
            .map((img) => ({ data_url: img.data_url, name: img.name }))
        : undefined;
      return {
        id: item.id,
        role: item.role,
        content: item.content,
        ts: item.ts,
        expression: normalizeExpressionId(item.expression),
        citations: item.citations,
        citation_snippets: item.citation_snippets,
        actions: item.actions,
        images,
        tool_trace: item.tool_trace,
      };
    });
}

export function loadPersistedSessions(): { sessions: ChatSession[]; activeId: string } {
  if (typeof window === "undefined") {
    const session = newSession();
    return { sessions: [session], activeId: session.id };
  }
  try {
    const raw = window.localStorage.getItem(AELIN_SESSIONS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { sessions?: unknown; active_id?: unknown };
      const sessionRows = Array.isArray(parsed.sessions) ? parsed.sessions : [];
      const sessions: ChatSession[] = [];
      for (const row of sessionRows) {
        if (!row || typeof row !== "object") continue;
        const r = row as Partial<ChatSession>;
        const restoredMsgs = Array.isArray(r.messages) ? toPersistedMessages(r.messages as ChatMessage[]) : [];
        if (!restoredMsgs.length) continue;
        sessions.push({
          id: typeof r.id === "string" && r.id ? r.id : nextMessageId(),
          title: typeof r.title === "string" && r.title.trim() ? r.title.trim().slice(0, 80) : deriveSessionTitle(restoredMsgs),
          messages: restoredMsgs,
          updated_at: typeof r.updated_at === "number" && !Number.isNaN(r.updated_at) ? r.updated_at : Date.now(),
        });
      }
      if (sessions.length) {
        sessions.sort((a, b) => b.updated_at - a.updated_at);
        const activeCandidate = typeof parsed.active_id === "string" ? parsed.active_id : "";
        const activeId = sessions.some((it) => it.id === activeCandidate) ? activeCandidate : sessions[0].id;
        return { sessions: sessions.slice(0, MAX_PERSISTED_SESSIONS), activeId };
      }
    }
  } catch {
    // ignore and fallback
  }

  const migrated = loadPersistedMessages();
  const session = newSession(migrated.length ? migrated : initialMessages());
  return { sessions: [session], activeId: session.id };
}

export function useGroupedMessages(messages: ChatMessage[]): GroupedMessage[] {
  return React.useMemo(() => {
    let lastRole: ChatMessage["role"] | null = null;
    let lastTs = 0;
    return messages.map((message) => {
      const isGroupStart = lastRole !== message.role || message.ts - lastTs > 2 * 60 * 1000;
      lastRole = message.role;
      lastTs = message.ts;
      return { message, isGroupStart };
    });
  }, [messages]);
}
