import React from "react";
import { motion } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Badge from "@mui/material/Badge";
import FormControl from "@mui/material/FormControl";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputBase from "@mui/material/InputBase";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import Dialog from "@mui/material/Dialog";
import CircularProgress from "@mui/material/CircularProgress";
import Tooltip from "@mui/material/Tooltip";
import Alert from "@mui/material/Alert";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Skeleton from "@mui/material/Skeleton";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import AddIcon from "@mui/icons-material/Add";
import SendIcon from "@mui/icons-material/Send";
import SettingsIcon from "@mui/icons-material/Settings";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ImageIcon from "@mui/icons-material/Image";
import CloseIcon from "@mui/icons-material/Close";
import TimelineIcon from "@mui/icons-material/Timeline";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import BoltIcon from "@mui/icons-material/Bolt";
import RefreshIcon from "@mui/icons-material/Refresh";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import InsightsIcon from "@mui/icons-material/Insights";
import TrackChangesIcon from "@mui/icons-material/TrackChanges";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import LayersIcon from "@mui/icons-material/Layers";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import TuneIcon from "@mui/icons-material/Tune";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import ComputerIcon from "@mui/icons-material/Computer";
import MemoryIcon from "@mui/icons-material/Memory";
import SpeedIcon from "@mui/icons-material/Speed";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import { alpha, useTheme } from "@mui/material/styles";
import {
  AelinAction,
  AelinCitation,
  AelinContextResponse,
  AelinDeviceCapabilitiesResponse,
  AelinDeviceModeApplyResponse,
  AelinDeviceOptimizeResponse,
  AelinDeviceProcessItem,
  AelinMemoryLayerItem,
  AelinNotificationItem,
  AgentConfig,
  ModelCatalogResponse,
  ModelProviderInfo,
  AelinImageInput,
  AelinTrackingChangeItem,
  AelinTrackingItem,
  AelinTrackingSnapshotItem,
  AelinTrackingFileMemoryItem,
  AelinToolStep,
  MessageDetail,
  ackAelinTrackingChange,
  aelinChat,
  aelinChatStream,
  aelinConfirmTrack,
  applyAelinDeviceMode,
  getAgentCatalog,
  getAgentConfig,
  getAelinTracking,
  getAelinDeviceCapabilities,
  getAelinDeviceMode,
  getAelinDeviceProcesses,
  getAelinNotifications,
  getAelinProactivePoll,
  getAelinContext,
  getMessage,
  listAelinTrackingChanges,
  listAelinTrackingSnapshots,
  listAelinTrackingFileMemory,
  optimizeAelinDeviceProcesses,
  runAelinDeviceProcessAction,
  runAelinTrackingTarget,
  testAgent,
  updateAelinTrackingTarget,
  updateAgentConfig,
} from "../api";
import { useConfirmDialog } from "../hooks/useConfirmDialog";
import { useToast } from "../contexts/ToastContext";
import { isNativeMobileShell } from "../mobile/runtime";
import Dashboard from "./Dashboard";
import {
  AELIN_CHAT_STORAGE_KEY,
  AELIN_EXPRESSION_IDS,
  type AelinExpressionId,
  AELIN_EXPRESSION_META,
  AELIN_EXPRESSION_SRC,
  AELIN_LAST_DESK_BRIDGE_KEY,
  AELIN_LAST_SESSION_KEY,
  AELIN_LOGO_SRC,
  AELIN_SESSIONS_STORAGE_KEY,
  CUSTOM_PROVIDER_OPTION,
  DEVICE_MODE_META,
  type DeviceMode,
  type DeviceSortBy,
  type PlatformKey,
  MAX_PERSISTED_IMAGE_DATA_URL,
  MAX_PERSISTED_MESSAGES,
  MAX_PERSISTED_SESSIONS,
  PLATFORM_META,
  PROACTIVE_POLL_MS,
  QUICK_PROMPTS,
  TRACKING_SOURCE_LABEL,
} from "./aelin/constants";
import {
  extractFirstUrl,
  formatIsoTime,
  formatTime,
  formatTrackingStatus,
  hashString,
  initialsFromName,
  looksLikeMarkdown,
  nextMessageId,
  normalizeAutoLinksForMarkdown,
  normalizeAccountKey,
  normalizeExpressionId,
  normalizePlatformName,
  normalizeProviderId,
  resolveCitationPlatform,
  toolStepLabel,
  traceParallelLabel,
  traceParallelLane,
} from "./aelin/helpers";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: number;
  expression?: string;
  pending?: boolean;
  citations?: AelinCitation[];
  citation_snippets?: Record<string, string>;
  actions?: AelinAction[];
  images?: AelinImageInput[];
  tool_trace?: AelinToolStep[];
};

type ChatSession = {
  id: string;
  title: string;
  messages: ChatMessage[];
  updated_at: number;
};

type PendingImage = {
  id: string;
  dataUrl: string;
  name: string;
};

type TrackingSheetState = {
  action: AelinAction;
  messageId: string;
};

type HandoffFXState = {
  title: string;
  detail: string;
};

export type AelinDeskBridgePayload = {
  sessionId: string;
  workspace: string;
  messageId?: number;
  contactId?: number;
  focusQuery?: string;
  highlightSource?: string;
  resumePrompt?: string;
};

type AelinProps = {
  embedded?: boolean;
  workspace?: string;
  onOpenDesk?: (payload: AelinDeskBridgePayload) => void;
  onRequestClose?: () => void;
};

type ResultCard = {
  id: string;
  title: string;
  value: string;
  subtitle?: string;
  accent: string;
  icon: React.ReactNode;
};

type TrackingAckFilter = "all" | "unacked" | "acked";

const TRACKING_CHANGE_TYPE_LABEL: Record<string, string> = {
  new_item: "新增",
  updated_item: "更新",
  removed_item: "移除",
  metric_spike: "波动",
  fetch_error: "抓取失败",
  status_change: "状态变更",
  recovered: "恢复",
};

const TRACKING_SEVERITY_META: Record<
  string,
  { label: string; color: "default" | "info" | "success" | "warning" | "error" }
> = {
  low: { label: "低", color: "default" },
  medium: { label: "中", color: "info" },
  high: { label: "高", color: "warning" },
  critical: { label: "严重", color: "error" },
};

function initialMessages(): ChatMessage[] {
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

function deriveSessionTitle(messages: ChatMessage[]): string {
  const user = messages.find((item) => item.role === "user" && item.content.trim());
  if (!user) return "新对话";
  const first = user.content.trim().split("\n")[0] || "新对话";
  return first.length > 22 ? `${first.slice(0, 22)}…` : first;
}

function newSession(messages?: ChatMessage[]): ChatSession {
  const payload = messages && messages.length ? messages : initialMessages();
  return {
    id: nextMessageId(),
    title: deriveSessionTitle(payload),
    messages: payload,
    updated_at: Date.now(),
  };
}

function loadPersistedMessages(): ChatMessage[] {
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

function toPersistedMessages(messages: ChatMessage[]): ChatMessage[] {
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

function normalizeTraceStep(step: AelinToolStep): AelinToolStep {
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

function upsertTraceStep(steps: AelinToolStep[], incoming: AelinToolStep): AelinToolStep[] {
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

function mergeCitations(existing: AelinCitation[], incoming: AelinCitation[], limit = 12): AelinCitation[] {
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

function mergeCitationSnippets(
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

function parseScoreCards(text: string): ResultCard[] {
  const rows: ResultCard[] = [];
  const seen = new Set<string>();
  const regex = /([A-Za-z\u4e00-\u9fff]{1,24})?\s*(\d{2,3})\s*[-:：]\s*(\d{2,3})\s*([A-Za-z\u4e00-\u9fff]{1,24})?/g;
  let m: RegExpExecArray | null = null;
  while ((m = regex.exec(text)) !== null) {
    const left = (m[1] || "队伍A").trim();
    const right = (m[4] || "队伍B").trim();
    const a = Number(m[2]);
    const b = Number(m[3]);
    if (Number.isNaN(a) || Number.isNaN(b) || a < 40 || b < 40 || a > 200 || b > 200) continue;
    const id = `${left}-${a}-${b}-${right}`.toLowerCase();
    if (seen.has(id)) continue;
    seen.add(id);
    rows.push({
      id,
      title: `${left} vs ${right}`,
      value: `${a} : ${b}`,
      subtitle: a > b ? `${left} 暂时领先` : b > a ? `${right} 暂时领先` : "比分接近",
      accent: a > b ? "#e07a5f" : "#3f88c5",
      icon: <InsightsIcon sx={{ fontSize: 16 }} />,
    });
    if (rows.length >= 3) break;
  }
  return rows;
}

function cardsFromMessage(message: ChatMessage): ResultCard[] {
  const cards: ResultCard[] = [];
  cards.push(...parseScoreCards(message.content || ""));
  for (const c of message.citations || []) {
    if (cards.length >= 6) break;
    cards.push({
      id: `cite-${message.id}-${c.message_id}-${c.source}`,
      title: c.source_label || c.source,
      value: c.title || "证据",
      subtitle: `${c.sender || "unknown"} 路 ${c.received_at.slice(5)}`,
      accent: "#4d6fff",
      icon: <TravelExploreIcon sx={{ fontSize: 16 }} />,
    });
  }
  return cards;
}

function buildStoryFromContext(ctx: AelinContextResponse | null): string {
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

function loadPersistedSessions(): { sessions: ChatSession[]; activeId: string } {
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

function useGroupedMessages(messages: ChatMessage[]) {
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

async function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsDataURL(file);
  });
}

const TypingDots = React.memo(function TypingDots() {
  return (
    <Box
      sx={{
        display: "inline-flex",
        gap: 0.5,
        "@keyframes aelinTypingDot": {
          "0%, 70%, 100%": { opacity: 0.3, transform: "translateY(0)" },
          "35%": { opacity: 1, transform: "translateY(-4px)" },
        },
      }}
    >
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary", animation: "aelinTypingDot 1.2s infinite ease-in-out" }} />
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary", animation: "aelinTypingDot 1.2s 0.14s infinite ease-in-out" }} />
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "text.secondary", animation: "aelinTypingDot 1.2s 0.28s infinite ease-in-out" }} />
    </Box>
  );
});

const AccountAvatar = React.memo(function AccountAvatar({
  name,
  src,
  size = 16,
}: {
  name: string;
  src?: string | null;
  size?: number;
}) {
  const safeName = name || "unknown";
  const initial = initialsFromName(safeName);
  const hue = hashString(safeName) % 360;
  return (
    <Avatar
      src={src || undefined}
      alt={safeName}
      sx={{
        width: size,
        height: size,
        fontSize: Math.max(9, Math.floor(size * 0.5)),
        fontWeight: 700,
        border: "1px solid rgba(255,255,255,0.72)",
        background: src
          ? "transparent"
          : `linear-gradient(135deg, hsla(${hue},78%,58%,0.96), hsla(${(hue + 36) % 360},76%,47%,0.94))`,
        color: "#fff",
        boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
      }}
    >
      {!src ? initial : null}
    </Avatar>
  );
});

const InlineSourceBadge = React.memo(function InlineSourceBadge({
  platform,
  account,
  avatarSrc,
}: {
  platform: PlatformKey;
  account?: string;
  avatarSrc?: string;
}) {
  const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
  const accountLabel = (account || "").trim();
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.42,
        px: 0.72,
        py: 0.2,
        mx: 0.24,
        borderRadius: 999,
        border: "1px solid",
        borderColor: meta.border,
        bgcolor: meta.bg,
        color: meta.color,
        verticalAlign: "middle",
        fontSize: "0.78em",
        fontWeight: 700,
        lineHeight: 1.2,
        transition: "transform 160ms ease, box-shadow 180ms ease",
        "&:hover": {
          transform: "translateY(-1px)",
          boxShadow: `0 6px 14px ${alpha(meta.color, 0.2)}`,
        },
      }}
    >
      <PlatformGlyph platform={platform} size={13} />
      {accountLabel ? <AccountAvatar name={accountLabel} src={avatarSrc} size={15} /> : null}
      <span>{accountLabel || meta.label}</span>
    </Box>
  );
});

const PlatformGlyph = React.memo(function PlatformGlyph({ platform, size = 14 }: { platform: PlatformKey; size?: number }) {
  const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
  if (platform === "bilibili") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="4.2" y="6.7" width="15.6" height="12.2" rx="3" stroke={meta.color} strokeWidth="1.7" />
        <path d="M8.4 4.6L10.4 6.7M15.6 4.6L13.6 6.7" stroke={meta.color} strokeWidth="1.7" strokeLinecap="round" />
        <path d="M9.3 11.4h0.01M14.7 11.4h0.01" stroke={meta.color} strokeWidth="2.3" strokeLinecap="round" />
      </svg>
    );
  }
  if (platform === "douyin") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M13 5.5v8.2a3.8 3.8 0 11-2.2-3.4V6.8c1.9.2 3.4-.2 4.8-1.3" stroke={meta.color} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (platform === "xiaohongshu") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3.4" y="3.4" width="17.2" height="17.2" rx="5" stroke={meta.color} strokeWidth="1.6" />
        <path d="M7.4 15.2l3-3 2.6 2.6 3.5-3.6" stroke={meta.color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (platform === "weibo") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="11.3" cy="13.1" r="4.5" stroke={meta.color} strokeWidth="1.7" />
        <path d="M16.6 7.6c1.4.4 2.6 1.4 3.2 2.8M15 5.4c2.3.3 4.4 1.9 5.3 4" stroke={meta.color} strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10.2" cy="12.7" r="0.8" fill={meta.color} />
      </svg>
    );
  }
  if (platform === "x") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5 5l14 14M18.6 5.3L5.4 18.7" stroke={meta.color} strokeWidth="2.1" strokeLinecap="round" />
      </svg>
    );
  }
  if (platform === "github") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 4.5a7.6 7.6 0 00-2.4 14.9v-2.7c-1.6.4-2.3-.7-2.5-1.3-.2-.5-.7-1.3-1.2-1.6-.4-.2-1-.8 0-.8.9 0 1.5.8 1.7 1.2 1 .1 1.6-.7 1.8-1.1.1-.8.4-1.3.8-1.6-2.8-.3-5.8-1.4-5.8-6.2 0-1.4.5-2.6 1.3-3.5-.1-.3-.6-1.6.1-3.3 0 0 1.1-.3 3.6 1.3a12 12 0 016.6 0c2.5-1.6 3.6-1.3 3.6-1.3.7 1.7.2 3 .1 3.3.8.9 1.3 2.1 1.3 3.5 0 4.8-3 5.9-5.8 6.2.5.4.9 1.2.9 2.4v3.4A7.6 7.6 0 0012 4.5z" fill={meta.color} />
      </svg>
    );
  }
  if (platform === "rss") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="6.2" cy="17.8" r="1.8" fill={meta.color} />
        <path d="M5 11.4a7.7 7.7 0 017.6 7.6M5 6a13 13 0 0113 13" stroke={meta.color} strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  if (platform === "email") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3.8" y="6.2" width="16.4" height="11.6" rx="2.3" stroke={meta.color} strokeWidth="1.6" />
        <path d="M4.8 7.4l7.2 5.3 7.2-5.3" stroke={meta.color} strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    );
  }
  if (platform === "web") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="8.2" stroke={meta.color} strokeWidth="1.6" />
        <path d="M4.8 12h14.4M12 4.8c2.1 2.1 3.2 4.6 3.2 7.2s-1.1 5.1-3.2 7.2m0-14.4C9.9 6.9 8.8 9.4 8.8 12s1.1 5.1 3.2 7.2" stroke={meta.color} strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" stroke={meta.color} strokeWidth="1.7" />
      <path d="M7.7 12h8.6M12 7.7v8.6" stroke={meta.color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
});

const CitationPill = React.memo(function CitationPill({
  item,
  onOpen,
}: {
  item: AelinCitation;
  onOpen?: (item: AelinCitation) => void;
}) {
  const platform = resolveCitationPlatform(item);
  const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
  return (
    <Box
      onClick={() => onOpen?.(item)}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.55,
        px: 0.72,
        py: 0.35,
        borderRadius: 999,
        border: "1px solid",
        borderColor: meta.border,
        bgcolor: meta.bg,
        color: meta.color,
        fontSize: "0.74rem",
        lineHeight: 1.2,
        transition: "transform 160ms ease, box-shadow 180ms ease, filter 180ms ease",
        boxShadow: "0 0 0 rgba(0,0,0,0)",
        cursor: onOpen ? "pointer" : "default",
        "&:hover": {
          transform: "translateY(-1px)",
          boxShadow: `0 8px 18px ${alpha(meta.color, 0.2)}`,
          filter: "saturate(1.08)",
        },
      }}
      title={`${item.source_label} | ${item.title}`}
    >
      <PlatformGlyph platform={platform} size={13} />
      <AccountAvatar name={item.sender || item.source_label} src={item.sender_avatar_url} size={16} />
      <Typography
        component="span"
        sx={{
          fontSize: "0.73rem",
          fontWeight: 700,
          lineHeight: 1,
          maxWidth: 88,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {item.sender || item.source_label}
      </Typography>
      <Typography component="span" sx={{ fontSize: "0.74rem", fontWeight: 700, lineHeight: 1 }}>
        {item.source_label}
      </Typography>
      <Typography component="span" sx={{ fontSize: "0.72rem", opacity: 0.78, lineHeight: 1 }}>
        {item.received_at.slice(5)}
      </Typography>
    </Box>
  );
});

const ToolTraceRow = React.memo(function ToolTraceRow({ steps }: { steps: AelinToolStep[] }) {
  const normalized = React.useMemo(() => {
    const rows = (steps || [])
      .map(normalizeTraceStep)
      .filter((it) => String(it.stage || "").trim().length > 0)
      .sort((a, b) => {
        const ta = Number(a.ts || 0);
        const tb = Number(b.ts || 0);
        if (ta > 0 && tb > 0 && ta !== tb) return ta - tb;
        if (ta > 0 && tb <= 0) return -1;
        if (ta <= 0 && tb > 0) return 1;
        return a.stage.localeCompare(b.stage);
      });
    return rows.slice(-64);
  }, [steps]);
  if (!normalized.length) return null;
  const parallelGroups = React.useMemo(() => {
    const bucket = new Map<string, { total: number; running: number; failed: number }>();
    for (const step of normalized) {
      const lane = traceParallelLane(step.stage);
      if (!lane) continue;
      const prev = bucket.get(lane) || { total: 0, running: 0, failed: 0 };
      prev.total += 1;
      if (step.status === "running") prev.running += 1;
      if (step.status === "failed") prev.failed += 1;
      bucket.set(lane, prev);
    }
    return Array.from(bucket.entries()).map(([lane, info]) => ({ lane, ...info }));
  }, [normalized]);
  return (
    <Stack spacing={0.4} sx={{ mb: 0.58, px: 0.2 }}>
      {parallelGroups.length ? (
        <Stack direction="row" spacing={0.45} flexWrap="wrap" useFlexGap>
          {parallelGroups.map((group) => {
            const busy = group.running > 0;
            const color = group.failed > 0 ? "#d1495b" : busy ? "#f4a261" : "#2a9d8f";
            const suffix = busy ? ` running ${group.running}` : group.failed ? ` failed ${group.failed}` : " done";
            return (
              <Chip
                key={group.lane}
                size="small"
                variant="outlined"
                label={`${traceParallelLabel(group.lane)} x${group.total}${suffix}`}
                sx={{
                  borderColor: alpha(color, 0.45),
                  color,
                  bgcolor: alpha(color, 0.1),
                  "& .MuiChip-label": { px: 0.8, fontSize: "0.66rem", fontWeight: 700 },
                }}
              />
            );
          })}
        </Stack>
      ) : null}

      <Stack spacing={0.34}>
        {normalized.map((step, idx) => {
          const done = step.status === "completed";
          const running = step.status === "running";
          const failed = step.status === "failed";
          const skipped = step.status === "skipped";
          const color = failed ? "#d1495b" : done ? "#2a9d8f" : skipped ? "#7c7c7c" : "#f4a261";
          return (
            <Box
              key={`${step.stage}-${idx}-${Number(step.ts || 0) || 0}`}
              title={failed ? step.detail || "" : ""}
              sx={{
                display: "grid",
                gridTemplateColumns: "10px 1fr",
                alignItems: "flex-start",
                gap: 0.58,
                px: 0.48,
                py: 0.32,
                borderRadius: 1,
                border: "1px solid",
                borderColor: alpha(color, 0.2),
                bgcolor: alpha(color, 0.06),
              }}
            >
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: color,
                  mt: 0.45,
                  ...(running
                    ? {
                        "@keyframes tracePulseDot": {
                          "0%, 100%": { transform: "scale(1)", opacity: 0.7 },
                          "50%": { transform: "scale(1.25)", opacity: 1 },
                        },
                        animation: "tracePulseDot 900ms ease-in-out infinite",
                      }
                    : {}),
                }}
              />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="caption" sx={{ display: "block", fontWeight: 700, fontSize: "0.69rem", lineHeight: 1.2 }}>
                  {toolStepLabel(step.stage)}
                  {step.count ? ` ${step.count}` : ""}
                </Typography>
                {failed && step.detail ? (
                  <Typography
                    variant="caption"
                    color="error.main"
                    sx={{
                      display: "-webkit-box",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      lineHeight: 1.22,
                      fontSize: "0.64rem",
                      mt: 0.08,
                    }}
                  >
                    {step.detail}
                  </Typography>
                ) : null}
              </Box>
            </Box>
          );
        })}
      </Stack>
    </Stack>
  );
});

const ResultDeck = React.memo(function ResultDeck({ cards, pulse }: { cards: ResultCard[]; pulse?: boolean }) {
  if (!cards.length) return null;
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(176px, 1fr))",
        gap: 0.65,
        mb: 0.75,
        "@keyframes deckPulse": {
          "0%, 100%": { transform: "translateY(0)", boxShadow: "0 0 0 rgba(0,0,0,0)" },
          "50%": { transform: "translateY(-1px)", boxShadow: "0 10px 18px rgba(0,0,0,0.08)" },
        },
      }}
    >
      {cards.slice(0, 6).map((card) => (
        <Paper
          key={card.id}
          variant="outlined"
          sx={{
            px: 0.95,
            py: 0.72,
            borderRadius: 1.3,
            borderColor: alpha(card.accent, 0.42),
            bgcolor: alpha(card.accent, 0.08),
            animation: pulse ? "deckPulse 900ms ease-in-out 1" : "none",
          }}
        >
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.3 }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: alpha(card.accent, 0.95), lineHeight: 1.2 }}>
              {card.title}
            </Typography>
            <Box sx={{ color: alpha(card.accent, 0.9), display: "flex", alignItems: "center" }}>{card.icon}</Box>
          </Stack>
          <Typography variant="body2" sx={{ fontWeight: 800, lineHeight: 1.25 }}>
            {card.value}
          </Typography>
          {card.subtitle ? (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block", lineHeight: 1.35 }}>
              {card.subtitle}
            </Typography>
          ) : null}
        </Paper>
      ))}
    </Box>
  );
});

function renderRichMessageContent(content: string, resolveAvatarSrc?: (account: string) => string | undefined) {
  const renderTextWithLinks = (text: string, keyPrefix: string) => {
    const out: React.ReactNode[] = [];
    const mdRegex = /\[([^\]\n]{1,120})\]\((https?:\/\/[^\s)]+)\)/g;
    let mdLast = 0;
    let mdSeg = 0;
    let mdMatch: RegExpExecArray | null = null;

    const pushPlainUrls = (plain: string, plainKey: string) => {
      const urlRegex = /(https?:\/\/[^\s<>"')\]]+)/g;
      let last = 0;
      let seg = 0;
      let m: RegExpExecArray | null = null;
      while ((m = urlRegex.exec(plain)) !== null) {
        const start = m.index;
        const end = start + m[0].length;
        if (start > last) out.push(plain.slice(last, start));
        const href = m[0];
        out.push(
          <Box
            key={`${plainKey}-url-${seg}`}
            component="a"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            sx={{ color: "primary.main", textDecoration: "underline", textUnderlineOffset: "2px" }}
          >
            {href}
          </Box>
        );
        last = end;
        seg += 1;
      }
      if (last < plain.length) out.push(plain.slice(last));
    };

    while ((mdMatch = mdRegex.exec(text)) !== null) {
      const start = mdMatch.index;
      const end = start + mdMatch[0].length;
      if (start > mdLast) pushPlainUrls(text.slice(mdLast, start), `${keyPrefix}-plain-${mdSeg}`);
      const label = mdMatch[1];
      const href = mdMatch[2];
      out.push(
        <Box
          key={`${keyPrefix}-md-${mdSeg}`}
          component="a"
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          sx={{ color: "primary.main", textDecoration: "underline", textUnderlineOffset: "2px" }}
        >
          {label}
        </Box>
      );
      mdLast = end;
      mdSeg += 1;
    }
    if (mdLast < text.length) pushPlainUrls(text.slice(mdLast), `${keyPrefix}-tail`);
    return out;
  };

  const lines = content.split("\n");
  return lines.map((line, lineIdx) => {
    const bulletMatch = line.match(
      /^(\s*[-*]\s*)?\[([^[\]\n]{1,24})\]\s*([^（\n]+?)(?:（([^）\n]{1,40})）)?(?:（([^）\n]{1,32})）)?(.*)$/
    );
    if (bulletMatch) {
      const prefix = bulletMatch[1] || "";
      const platform = normalizePlatformName(bulletMatch[2] || "");
      const title = (bulletMatch[3] || "").trim();
      const sender = (bulletMatch[4] || "").trim();
      const time = (bulletMatch[5] || "").trim();
      const tail = bulletMatch[6] || "";
      if (platform) {
        const avatarSrc = sender ? resolveAvatarSrc?.(sender) : undefined;
        const suffix = `${title ? ` ${title}` : ""}${time ? `（${time}）` : ""}${tail}`;
        return (
          <React.Fragment key={`line-${lineIdx}`}>
            {prefix}
            <InlineSourceBadge platform={platform} account={sender} avatarSrc={avatarSrc} />
            {renderTextWithLinks(suffix, `bullet-${lineIdx}`)}
            {lineIdx < lines.length - 1 ? <br /> : null}
          </React.Fragment>
        );
      }
    }

    const nodes: React.ReactNode[] = [];
    const regex = /\[([^[\]\n]{1,24})\](?:\s*@?([a-zA-Z0-9_\-.\u4e00-\u9fff]{2,40}))?/g;
    let last = 0;
    let match: RegExpExecArray | null = null;
    let seg = 0;
    while ((match = regex.exec(line)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      if (start > last) nodes.push(...renderTextWithLinks(line.slice(last, start), `line-${lineIdx}-seg-${seg}`));
      const platform = normalizePlatformName(match[1] || "");
      if (platform) {
        const account = (match[2] || "").trim();
        const shouldAt = account && match[0].includes("@");
        const label = shouldAt ? `@${account}` : account;
        const avatarSrc = account ? resolveAvatarSrc?.(account) : undefined;
        nodes.push(
          <InlineSourceBadge
            key={`badge-${lineIdx}-${seg}`}
            platform={platform}
            account={label}
            avatarSrc={avatarSrc}
          />
        );
      } else {
        nodes.push(...renderTextWithLinks(match[0], `line-${lineIdx}-raw-${seg}`));
      }
      last = end;
      seg += 1;
    }
    if (last < line.length) nodes.push(...renderTextWithLinks(line.slice(last), `line-${lineIdx}-tail`));
    return (
      <React.Fragment key={`line-${lineIdx}`}>
        {nodes}
        {lineIdx < lines.length - 1 ? <br /> : null}
      </React.Fragment>
    );
  });
}

const MessageRow = React.memo(function MessageRow(props: {
  message: ChatMessage;
  isGroupStart: boolean;
  onActionClick: (action: AelinAction) => void;
  onCopy: (text: string) => void;
  onCitationOpen: (item: AelinCitation) => void;
  pulse?: boolean;
  streamBusy?: boolean;
}) {
  const { message, isGroupStart, onActionClick, onCopy, onCitationOpen, pulse, streamBusy = false } = props;
  const theme = useTheme();
  const isUser = message.role === "user";
  const expressionId = !isUser && !message.pending ? normalizeExpressionId(message.expression) : undefined;
  const [hovered, setHovered] = React.useState(false);
  const cards = React.useMemo(() => cardsFromMessage(message), [message]);
  const accountAvatarMap = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const item of message.citations || []) {
      if (!item.sender_avatar_url) continue;
      const senderKey = normalizeAccountKey(item.sender || "");
      if (senderKey) map.set(senderKey, item.sender_avatar_url);
    }
    return map;
  }, [message.citations]);
  const resolveAvatarSrc = React.useCallback(
    (account: string) => {
      const key = normalizeAccountKey(account);
      if (!key) return undefined;
      return accountAvatarMap.get(key);
    },
    [accountAvatarMap]
  );

  return (
    <Box
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      sx={{
        "@keyframes aelinMessageIn": {
          from: { opacity: 0, transform: "translateY(10px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-start",
        gap: 1.1,
        px: { xs: 1.2, md: 2.4 },
        py: isGroupStart ? 1.1 : 0.4,
        animation: "aelinMessageIn 220ms ease",
      }}
    >
      {!isUser ? (
        <Avatar
          src={AELIN_LOGO_SRC}
          sx={{
            width: 36,
            height: 36,
            borderRadius: 1.2,
            bgcolor: "transparent",
            border: "none",
            boxShadow: "none",
            opacity: isGroupStart ? 1 : 0,
          }}
          imgProps={{ style: { objectFit: "cover", objectPosition: "center 24%" } }}
        />
      ) : (
        <Box sx={{ width: 36, height: 36 }} />
      )}

      <Box sx={{ maxWidth: "78%", minWidth: 58 }}>
        {isGroupStart ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", px: 0.65, mb: 0.5, textAlign: isUser ? "right" : "left", fontSize: "0.8rem" }}
          >
            {formatTime(message.ts)}
          </Typography>
        ) : null}

        <Paper
          variant="outlined"
          sx={{
            px: 1.35,
            py: 1.05,
            borderRadius: 1.75,
            bgcolor: isUser
              ? alpha(theme.palette.text.primary, theme.palette.mode === "light" ? 0.06 : 0.18)
              : "background.paper",
            transition: "transform 180ms ease, box-shadow 200ms ease",
            boxShadow: hovered ? `0 10px 20px ${alpha(theme.palette.text.primary, 0.08)}` : "none",
            transform: hovered ? "translateY(-1px)" : "translateY(0)",
          }}
        >
          {!isUser ? <ToolTraceRow steps={message.tool_trace || []} /> : null}
          {!isUser ? <ResultDeck cards={cards} pulse={pulse} /> : null}
          {!isUser && expressionId ? (
            <Box sx={{ display: "flex", justifyContent: "flex-start", mb: message.content ? 0.72 : 0 }}>
              <Tooltip title={`${AELIN_EXPRESSION_META[expressionId].label} 路 ${AELIN_EXPRESSION_META[expressionId].usage}`}>
                <Box
                  component="img"
                  src={AELIN_EXPRESSION_SRC[expressionId]}
                  alt={AELIN_EXPRESSION_META[expressionId].label}
                  sx={{
                    width: { xs: 140, sm: 168 },
                    maxWidth: "74%",
                    height: "auto",
                    display: "block",
                    filter: "drop-shadow(0 6px 14px rgba(0,0,0,0.12))",
                  }}
                />
              </Tooltip>
            </Box>
          ) : null}
          {message.images?.length ? (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(132px, 1fr))",
                gap: 0.7,
                mb: message.content ? 0.85 : 0,
              }}
            >
              {message.images.map((img, idx) => (
                <Box
                  key={`${message.id}-img-${idx}`}
                  component="img"
                  src={img.data_url}
                  alt={img.name || `image-${idx + 1}`}
                  sx={{
                    width: "100%",
                    maxHeight: 180,
                    objectFit: "cover",
                    borderRadius: 1.1,
                    border: "1px solid",
                    borderColor: "divider",
                  }}
                />
              ))}
            </Box>
          ) : null}

          {message.pending ? (
            <Stack spacing={0.8}>
              <Stack direction="row" spacing={0.9} alignItems="center">
                <TypingDots />
                <Typography variant="body1" color="text.secondary" sx={{ fontSize: "0.98rem" }}>
                  Aelin 正在思考...
                </Typography>
                {streamBusy ? (
                  <Chip
                    size="small"
                    variant="outlined"
                    label="流式更新中"
                    sx={{ "& .MuiChip-label": { px: 0.75, fontSize: "0.66rem", fontWeight: 700 } }}
                  />
                ) : null}
              </Stack>
              <Box>
                <Skeleton variant="text" width="85%" height={20} />
                <Skeleton variant="text" width="92%" height={20} />
                <Skeleton variant="text" width="70%" height={20} />
              </Box>
            </Stack>
          ) : (
            <Box sx={{ wordBreak: "break-word", lineHeight: 1.72, fontSize: "1rem" }}>
              {looksLikeMarkdown(message.content) ? (
                <Box
                  sx={{
                    "& p": { m: 0, mb: 1.05, lineHeight: 1.74 },
                    "& p:last-of-type": { mb: 0 },
                    "& ul, & ol": { mt: 0.25, mb: 1.05, pl: 2.3 },
                    "& li": { mb: 0.4 },
                    "& pre": {
                      m: 0,
                      mt: 0.6,
                      p: 1,
                      borderRadius: 1.2,
                      bgcolor: alpha(theme.palette.text.primary, 0.06),
                      overflowX: "auto",
                    },
                    "& code": {
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                      fontSize: "0.86em",
                    },
                    "& blockquote": {
                      m: 0,
                      my: 0.8,
                      pl: 1.1,
                      borderLeft: "3px solid",
                      borderColor: alpha(theme.palette.primary.main, 0.38),
                      color: "text.secondary",
                    },
                  }}
                >
                  <ReactMarkdown
                    components={{
                      a: ({ ...props }) => (
                        <a
                          {...props}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: theme.palette.primary.main, textDecoration: "underline", textUnderlineOffset: "2px" }}
                        />
                      ),
                    }}
                  >
                    {normalizeAutoLinksForMarkdown(message.content)}
                  </ReactMarkdown>
                </Box>
              ) : (
                <Box sx={{ whiteSpace: "pre-wrap" }}>
                  {renderRichMessageContent(message.content, resolveAvatarSrc)}
                </Box>
              )}
            </Box>
          )}
        </Paper>

        {!!message.citations?.length && (
          <Stack spacing={0.52} sx={{ mt: 0.68, px: 0.3, width: "100%", maxWidth: "100%", overflow: "hidden" }}>
            {message.citations.slice(0, 4).map((item) => {
              const platform = resolveCitationPlatform(item);
              const meta = PLATFORM_META[platform] || PLATFORM_META.generic;
              const snippet = message.citation_snippets?.[citationKey(item)] || "";
              return (
                <Paper
                  key={`${message.id}-${item.message_id}-${item.source}`}
                  variant="outlined"
                  onClick={() => onCitationOpen(item)}
                  sx={{
                    px: 0.62,
                    py: 0.52,
                    borderRadius: 1.05,
                    cursor: "pointer",
                    borderColor: alpha(meta.color, 0.4),
                    bgcolor: alpha(meta.color, 0.05),
                    width: "100%",
                    maxWidth: "100%",
                    overflow: "hidden",
                    transition: "transform 140ms ease, box-shadow 160ms ease",
                    "&:hover": {
                      transform: "translateY(-1px)",
                      boxShadow: `0 6px 12px ${alpha(meta.color, 0.18)}`,
                    },
                  }}
                >
                  <Stack direction="row" spacing={0.62} alignItems="center" sx={{ minWidth: 0 }}>
                    <PlatformGlyph platform={platform} size={13} />
                    <AccountAvatar name={item.sender || item.source_label} src={item.sender_avatar_url} size={16} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography
                        variant="caption"
                        sx={{
                          display: "block",
                          fontWeight: 700,
                          color: meta.color,
                          lineHeight: 1.2,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.title}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          display: "block",
                          lineHeight: 1.2,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.sender} 路 {item.source_label} 路 {item.received_at.slice(5)}
                      </Typography>
                    </Box>
                    <Chip
                      size="small"
                      label={item.score.toFixed(1)}
                      sx={{
                        height: 18,
                        minWidth: 34,
                        flexShrink: 0,
                        border: "1px solid",
                        borderColor: alpha(meta.color, 0.45),
                        bgcolor: alpha(meta.color, 0.08),
                        color: meta.color,
                        "& .MuiChip-label": { px: 0.58, fontSize: "0.62rem", fontWeight: 800 },
                      }}
                    />
                  </Stack>
                  {snippet ? (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        mt: 0.38,
                        pl: 2.95,
                        display: "-webkit-box",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        WebkitLineClamp: 1,
                        WebkitBoxOrient: "vertical",
                        lineHeight: 1.28,
                      }}
                    >
                      {snippet}
                    </Typography>
                  ) : null}
                </Paper>
              );
            })}
          </Stack>
        )}

        {!!message.actions?.length && (
          <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap sx={{ mt: 0.6, px: 0.45 }}>
            {message.actions
              .filter((action) => action.kind !== "confirm_track")
              .slice(0, 3)
              .map((action, idx) => (
              <Button
                key={`${message.id}-${action.kind}-${idx}`}
                size="small"
                variant="outlined"
                onClick={() => onActionClick(action)}
              >
                {action.title}
              </Button>
            ))}
          </Stack>
        )}

        {!message.pending ? (
          <Stack
            direction="row"
            justifyContent={isUser ? "flex-end" : "flex-start"}
            sx={{ mt: 0.2, px: 0.3, opacity: hovered ? 1 : 0, transition: "opacity 140ms ease" }}
          >
            <IconButton size="small" onClick={() => onCopy(message.content)}>
              <ContentCopyIcon sx={{ fontSize: 15 }} />
            </IconButton>
          </Stack>
        ) : null}
      </Box>
    </Box>
  );
});

export default function Aelin({
  embedded = false,
  workspace = "default",
  onOpenDesk,
  onRequestClose,
}: AelinProps) {
  const theme = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { confirm, ConfirmDialog } = useConfirmDialog();
  const boot = React.useMemo(() => loadPersistedSessions(), []);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [storyBusy, setStoryBusy] = React.useState(false);
  const [sessions, setSessions] = React.useState<ChatSession[]>(boot.sessions);
  const [activeSessionId, setActiveSessionId] = React.useState<string>(boot.activeId);
  const [pendingImages, setPendingImages] = React.useState<PendingImage[]>([]);
  const [contextSnapshot, setContextSnapshot] = React.useState<AelinContextResponse | null>(null);
  const [trackingSheet, setTrackingSheet] = React.useState<TrackingSheetState | null>(null);
  const [trackingDialogOpen, setTrackingDialogOpen] = React.useState(false);
  const [trackingItems, setTrackingItems] = React.useState<AelinTrackingItem[]>([]);
  const [trackingBusy, setTrackingBusy] = React.useState(false);
  const [trackingError, setTrackingError] = React.useState("");
  const [trackingStatusFilter, setTrackingStatusFilter] = React.useState("all");
  const [trackingSourceFilter, setTrackingSourceFilter] = React.useState("all");
  const [trackingKeyword, setTrackingKeyword] = React.useState("");
  const [trackingActiveTargetId, setTrackingActiveTargetId] = React.useState<number | null>(null);
  const [trackingChanges, setTrackingChanges] = React.useState<AelinTrackingChangeItem[]>([]);
  const [trackingSnapshots, setTrackingSnapshots] = React.useState<AelinTrackingSnapshotItem[]>([]);
  const [trackingFileMemory, setTrackingFileMemory] = React.useState<AelinTrackingFileMemoryItem[]>([]);
  const [trackingDetailBusy, setTrackingDetailBusy] = React.useState(false);
  const [trackingDetailError, setTrackingDetailError] = React.useState("");
  const [trackingMutationBusy, setTrackingMutationBusy] = React.useState<number | null>(null);
  const [trackingAckBusy, setTrackingAckBusy] = React.useState<number | null>(null);
  const [trackingChangeSeverityFilter, setTrackingChangeSeverityFilter] = React.useState("all");
  const [trackingChangeTypeFilter, setTrackingChangeTypeFilter] = React.useState("all");
  const [trackingAckFilter, setTrackingAckFilter] = React.useState<TrackingAckFilter>("unacked");
  const [memoryDialogOpen, setMemoryDialogOpen] = React.useState(false);
  const [memoryLayerTab, setMemoryLayerTab] = React.useState<"facts" | "preferences" | "in_progress">("facts");
  const [notificationDialogOpen, setNotificationDialogOpen] = React.useState(false);
  const [notificationBusy, setNotificationBusy] = React.useState(false);
  const [notificationItems, setNotificationItems] = React.useState<AelinNotificationItem[]>([]);
  const [deviceDialogOpen, setDeviceDialogOpen] = React.useState(false);
  const [deviceBusy, setDeviceBusy] = React.useState(false);
  const [deviceSortBy, setDeviceSortBy] = React.useState<DeviceSortBy>("cpu");
  const [deviceProcesses, setDeviceProcesses] = React.useState<AelinDeviceProcessItem[]>([]);
  const [deviceProcessMeta, setDeviceProcessMeta] = React.useState<{ emptyReason: string; platform: string; filterContext: Record<string, string> }>({
    emptyReason: "",
    platform: "unknown",
    filterContext: {},
  });
  const [deviceCapabilities, setDeviceCapabilities] = React.useState<AelinDeviceCapabilitiesResponse | null>(null);
  const [deviceModeState, setDeviceModeState] = React.useState<AelinDeviceModeApplyResponse | null>(null);
  const [deviceActionBusyPid, setDeviceActionBusyPid] = React.useState<number | null>(null);
  const [deviceModeApplying, setDeviceModeApplying] = React.useState<DeviceMode | null>(null);
  const [deviceOptimizeBusy, setDeviceOptimizeBusy] = React.useState(false);
  const [deviceOptimizeResult, setDeviceOptimizeResult] = React.useState<AelinDeviceOptimizeResponse | null>(null);
  const [isProgressPending, startProgressTransition] = React.useTransition();
  const [llmDialogOpen, setLlmDialogOpen] = React.useState(false);
  const [llmLoading, setLlmLoading] = React.useState(false);
  const [llmRefreshing, setLlmRefreshing] = React.useState(false);
  const [llmSaving, setLlmSaving] = React.useState(false);
  const [llmTesting, setLlmTesting] = React.useState(false);
  const [llmCatalog, setLlmCatalog] = React.useState<ModelCatalogResponse | null>(null);
  const [llmProvider, setLlmProvider] = React.useState("rule_based");
  const [llmProviderSelectValue, setLlmProviderSelectValue] = React.useState<string>("rule_based");
  const [llmCustomProviderId, setLlmCustomProviderId] = React.useState("");
  const [llmBaseUrl, setLlmBaseUrl] = React.useState("https://api.openai.com/v1");
  const [llmModel, setLlmModel] = React.useState("gpt-4o-mini");
  const [llmTemperature, setLlmTemperature] = React.useState(0.2);
  const [llmApiKey, setLlmApiKey] = React.useState("");
  const [llmHasApiKey, setLlmHasApiKey] = React.useState(false);
  const [deskOpen, setDeskOpen] = React.useState(false);
  const [deskPanelKey, setDeskPanelKey] = React.useState(0);
  const [handoffFX, setHandoffFX] = React.useState<HandoffFXState | null>(null);
  const [latestSparkMessageId, setLatestSparkMessageId] = React.useState<string>("");
  const dismissedTrackTargetsRef = React.useRef<Record<string, true>>({});
  const proactiveSeenRef = React.useRef<Record<string, true>>({});
  const [citationDrawer, setCitationDrawer] = React.useState<{
    open: boolean;
    citation: AelinCitation | null;
    detail: MessageDetail | null;
    loading: boolean;
    error: string;
  }>({ open: false, citation: null, detail: null, loading: false, error: "" });
  const [citationPreview, setCitationPreview] = React.useState<{
    open: boolean;
    citation: AelinCitation | null;
    url: string;
    loading: boolean;
    error: string;
  }>({ open: false, citation: null, url: "", loading: false, error: "" });
  const timelineRef = React.useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = React.useRef(true);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const citationUrlCacheRef = React.useRef<Record<number, string>>({});
  const handledDeskReturnRef = React.useRef<string>("");
  const handoffFXTimerRef = React.useRef<number | null>(null);
  const activeSession = React.useMemo(
    () => sessions.find((item) => item.id === activeSessionId) || sessions[0],
    [activeSessionId, sessions]
  );
  const messages = activeSession?.messages || [];
  const sortedSessions = React.useMemo(
    () => sessions.slice().sort((a, b) => b.updated_at - a.updated_at),
    [sessions]
  );
  const groupedMessages = useGroupedMessages(messages);
  const workspaceScope = React.useMemo(() => (workspace || "default").trim() || "default", [workspace]);
  const nativeMobileShell = React.useMemo(() => isNativeMobileShell(), []);
  const compactMode = React.useMemo(() => {
    if (embedded) return false;
    const qs = new URLSearchParams(location.search || "");
    return nativeMobileShell || (qs.get("compact") || "").trim() === "1";
  }, [embedded, location.search, nativeMobileShell]);
  const compactFramed = compactMode && !nativeMobileShell;
  const mainContainerMaxWidth = embedded ? false : compactMode ? false : "md";
  const llmIsCustomProvider = llmProviderSelectValue === CUSTOM_PROVIDER_OPTION;
  const llmSelectedProvider = React.useMemo<ModelProviderInfo | null>(() => {
    const providerId = normalizeProviderId(llmProvider);
    return llmCatalog?.providers.find((provider) => provider.id === providerId) ?? null;
  }, [llmCatalog, llmProvider]);
  const lastAssistantCitation = React.useMemo(() => {
    const reversed = [...messages].reverse();
    for (const item of reversed) {
      if (item.role !== "assistant") continue;
      const first = (item.citations || [])[0];
      if (first) return first;
    }
    return null;
  }, [messages]);
  const memoryLayers = React.useMemo(
    () => contextSnapshot?.memory_layers || { facts: [], preferences: [], in_progress: [], generated_at: "" },
    [contextSnapshot?.memory_layers]
  );
  const memoryLayerItems = React.useMemo<AelinMemoryLayerItem[]>(() => {
    if (memoryLayerTab === "facts") return memoryLayers.facts || [];
    if (memoryLayerTab === "preferences") return memoryLayers.preferences || [];
    return memoryLayers.in_progress || [];
  }, [memoryLayerTab, memoryLayers.facts, memoryLayers.in_progress, memoryLayers.preferences]);
  const contextNotifications = React.useMemo(() => contextSnapshot?.notifications || [], [contextSnapshot?.notifications]);
  const allNotifications = React.useMemo(() => {
    const merged = [...notificationItems, ...contextNotifications];
    const seen = new Set<string>();
    const out: AelinNotificationItem[] = [];
    for (const item of merged) {
      const key = String(item.id || "");
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
      if (out.length >= 60) break;
    }
    out.sort((a, b) => Date.parse(b.ts || "") - Date.parse(a.ts || ""));
    return out;
  }, [contextNotifications, notificationItems]);
  const unreadNotificationCount = React.useMemo(
    () => Math.min(99, allNotifications.filter((it) => (it.level || "info") !== "default").length),
    [allNotifications]
  );
  const filteredTrackingItems = React.useMemo(() => {
    const kw = trackingKeyword.trim().toLowerCase();
    return trackingItems.filter((item) => {
      if (trackingStatusFilter !== "all" && String(item.status || "").toLowerCase() !== trackingStatusFilter) return false;
      if (trackingSourceFilter !== "all" && String(item.source || "").toLowerCase() !== trackingSourceFilter) return false;
      if (!kw) return true;
      const blob = `${item.target} ${item.query} ${item.source} ${item.status}`.toLowerCase();
      return blob.includes(kw);
    });
  }, [trackingItems, trackingStatusFilter, trackingSourceFilter, trackingKeyword]);
  const trackingUnreadCount = React.useMemo(
    () => trackingItems.reduce((sum, item) => sum + Math.max(0, Number(item.unread_changes || 0)), 0),
    [trackingItems]
  );
  const activeTrackingItem = React.useMemo(() => {
    if (!trackingItems.length) return null;
    if (trackingActiveTargetId !== null) {
      const matched = trackingItems.find((item) => Number(item.target_id || 0) === trackingActiveTargetId);
      if (matched) return matched;
    }
    return trackingItems[0] || null;
  }, [trackingActiveTargetId, trackingItems]);

  const playHandoffFX = React.useCallback((title: string, detail: string, holdMs = 900) => {
    setHandoffFX({ title, detail });
    if (handoffFXTimerRef.current !== null) {
      window.clearTimeout(handoffFXTimerRef.current);
    }
    handoffFXTimerRef.current = window.setTimeout(() => {
      setHandoffFX(null);
      handoffFXTimerRef.current = null;
    }, holdMs);
  }, []);

  const openDeskWithContext = React.useCallback(
    (args?: {
      messageId?: number | string;
      contactId?: number | string;
      focusQuery?: string;
      highlightSource?: string;
      resumePrompt?: string;
    }) => {
      const sid = (activeSession?.id || activeSessionId || "").trim();
      const messageNum = Number(args?.messageId ?? 0);
      const contactNum = Number(args?.contactId ?? 0);
      const source = (args?.highlightSource || "").trim();
      const focusQuery = (args?.focusQuery || "").trim();
      const resumePrompt = (args?.resumePrompt || "").trim();

      if (typeof window !== "undefined") {
        try {
          if (sid) window.localStorage.setItem(AELIN_LAST_SESSION_KEY, sid);
          window.sessionStorage.setItem(
            AELIN_LAST_DESK_BRIDGE_KEY,
            JSON.stringify({
              from: "aelin",
              session_id: sid,
                focus_message_id: Number.isFinite(messageNum) && messageNum > 0 ? Math.floor(messageNum) : undefined,
                focus_contact_id: Number.isFinite(contactNum) && contactNum > 0 ? Math.floor(contactNum) : undefined,
                focus_query: focusQuery || undefined,
                workspace: workspaceScope,
                highlight_source: source || undefined,
                resume_prompt: resumePrompt || undefined,
                ts: Date.now(),
              })
            );
        } catch {
          // ignore storage failures
        }
      }
      if (onOpenDesk) {
        playHandoffFX(
          "Aelin -> Desk",
          focusQuery ? `正在定位主题“${focusQuery.slice(0, 36)}”` : "正在打开观察视图"
        );
        onOpenDesk({
          sessionId: sid,
          workspace: workspaceScope,
          messageId: Number.isFinite(messageNum) && messageNum > 0 ? Math.floor(messageNum) : undefined,
          contactId: Number.isFinite(contactNum) && contactNum > 0 ? Math.floor(contactNum) : undefined,
          focusQuery: focusQuery || undefined,
          highlightSource: source || undefined,
          resumePrompt: resumePrompt || undefined,
        });
        return;
      }
      playHandoffFX(
        "Aelin -> Desk",
        focusQuery ? `正在定位主题“${focusQuery.slice(0, 36)}”` : "正在打开观察视图"
      );
      window.setTimeout(() => {
        setDeskPanelKey((prev) => prev + 1);
        setDeskOpen(true);
      }, 140);
    },
    [activeSession?.id, activeSessionId, onOpenDesk, playHandoffFX, workspaceScope]
  );

  const refreshContext = React.useCallback(async () => {
    try {
      const ctx = await getAelinContext(workspaceScope, "");
      setContextSnapshot(ctx);
    } catch {
      // ignore temporary context fetch failures
    }
  }, [workspaceScope]);

  const refreshTracking = React.useCallback(async () => {
    setTrackingBusy(true);
    setTrackingError("");
    try {
      const ret = await getAelinTracking({
        limit: 120,
        workspace: workspaceScope,
        status: trackingStatusFilter !== "all" ? trackingStatusFilter : undefined,
      });
      const items = ret.items || [];
      setTrackingItems(items);
      setTrackingActiveTargetId((prev) => {
        if (prev !== null && items.some((item) => Number(item.target_id || 0) === prev)) return prev;
        const first = items.find((item) => Number(item.target_id || 0) > 0);
        return first ? Number(first.target_id || 0) : null;
      });
    } catch (error) {
      setTrackingError(error instanceof Error ? error.message : "跟踪列表加载失败");
    } finally {
      setTrackingBusy(false);
    }
  }, [trackingStatusFilter, workspaceScope]);

  const refreshTrackingDetail = React.useCallback(
    async (targetId: number, options?: { silent?: boolean }) => {
      const safeTargetId = Number(targetId || 0);
      if (!safeTargetId) {
        setTrackingFileMemory([]);
        return;
      }
      if (!options?.silent) {
        setTrackingDetailBusy(true);
      }
      setTrackingDetailError("");
      try {
        const acked = trackingAckFilter === "all" ? undefined : trackingAckFilter === "acked";
        const targetMeta = trackingItems.find((item) => Number(item.target_id || 0) === safeTargetId) || null;
        const memoryQuery = String(targetMeta?.query || targetMeta?.target || "").trim();
        const [changesRet, snapshotsRet, fileMemoryRet] = await Promise.all([
          listAelinTrackingChanges(safeTargetId, {
            limit: 120,
            severity: trackingChangeSeverityFilter !== "all" ? trackingChangeSeverityFilter : undefined,
            change_type: trackingChangeTypeFilter !== "all" ? trackingChangeTypeFilter : undefined,
            acked,
          }),
          listAelinTrackingSnapshots(safeTargetId, 40),
          listAelinTrackingFileMemory({
            workspace: workspaceScope,
            query: memoryQuery,
            source: String(targetMeta?.source || "").trim() || undefined,
            limit: 12,
          }),
        ]);
        setTrackingChanges(changesRet.items || []);
        setTrackingSnapshots(snapshotsRet.items || []);
        setTrackingFileMemory(fileMemoryRet.items || []);
      } catch (error) {
        setTrackingDetailError(error instanceof Error ? error.message : "追踪详情加载失败");
        setTrackingFileMemory([]);
      } finally {
        if (!options?.silent) {
          setTrackingDetailBusy(false);
        }
      }
    },
    [trackingAckFilter, trackingChangeSeverityFilter, trackingChangeTypeFilter, trackingItems, workspaceScope]
  );

  const patchTrackingTarget = React.useCallback(
    async (
      targetId: number,
      payload: {
        status?: "active" | "paused" | "error" | "deleted";
        interval_seconds?: number;
        notify_level?: "all" | "important" | "critical";
        mute_until?: string | null;
        description?: string;
        tags?: string[];
      },
      successMessage: string
    ) => {
      const safeTargetId = Number(targetId || 0);
      if (!safeTargetId) return;
      setTrackingMutationBusy(safeTargetId);
      try {
        await updateAelinTrackingTarget(safeTargetId, payload);
        showToast(successMessage, "success");
        await refreshTracking();
        await refreshTrackingDetail(safeTargetId, { silent: true });
      } catch (error) {
        showToast(error instanceof Error ? error.message : "追踪项更新失败", "error");
      } finally {
        setTrackingMutationBusy(null);
      }
    },
    [refreshTracking, refreshTrackingDetail, showToast]
  );

  const runTrackingTargetNow = React.useCallback(
    async (targetId: number) => {
      const safeTargetId = Number(targetId || 0);
      if (!safeTargetId) return;
      setTrackingMutationBusy(safeTargetId);
      try {
        const ret = await runAelinTrackingTarget(safeTargetId);
        showToast(ret.message || "已触发立即执行", ret.ok ? "success" : "warning");
        await refreshTracking();
        await refreshTrackingDetail(safeTargetId, { silent: true });
      } catch (error) {
        showToast(error instanceof Error ? error.message : "手动执行失败", "error");
      } finally {
        setTrackingMutationBusy(null);
      }
    },
    [refreshTracking, refreshTrackingDetail, showToast]
  );

  const ackTrackingChange = React.useCallback(
    async (changeId: number) => {
      const safeChangeId = Number(changeId || 0);
      const targetId = Number(activeTrackingItem?.target_id || 0);
      if (!safeChangeId || !targetId) return;
      setTrackingAckBusy(safeChangeId);
      try {
        await ackAelinTrackingChange(safeChangeId);
        await Promise.all([refreshTracking(), refreshTrackingDetail(targetId, { silent: true })]);
      } catch (error) {
        showToast(error instanceof Error ? error.message : "标记已读失败", "error");
      } finally {
        setTrackingAckBusy(null);
      }
    },
    [activeTrackingItem?.target_id, refreshTracking, refreshTrackingDetail, showToast]
  );

  const refreshNotifications = React.useCallback(async () => {
    setNotificationBusy(true);
    try {
      const ret = await getAelinNotifications(30);
      setNotificationItems(ret.items || []);
    } catch {
      // ignore transient failures
    } finally {
      setNotificationBusy(false);
    }
  }, []);

  const pushSystemNotification = React.useCallback((item: AelinNotificationItem) => {
    if (typeof window === "undefined") return;
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    try {
      const title = (item.title || "Aelin 提醒").trim() || "Aelin 提醒";
      const detail = (item.detail || "").trim();
      const note = new Notification(title, {
        body: detail ? detail.slice(0, 180) : "你有新的动态值得查看",
        icon: AELIN_LOGO_SRC,
        tag: String(item.id || ""),
      });
      window.setTimeout(() => note.close(), 5600);
    } catch {
      // ignore notification errors
    }
  }, []);

  const pollProactive = React.useCallback(async () => {
    try {
      const ret = await getAelinProactivePoll(workspaceScope, 8);
      const incoming = Array.isArray(ret.items) ? ret.items.filter(Boolean) : [];
      if (!incoming.length) return;
      setNotificationItems((prev) => {
        const seen = new Set<string>();
        const merged: AelinNotificationItem[] = [];
        for (const row of [...incoming, ...prev]) {
          const key = String(row.id || "");
          if (!key || seen.has(key)) continue;
          seen.add(key);
          merged.push(row);
          if (merged.length >= 80) break;
        }
        return merged;
      });

      const justIn: AelinNotificationItem[] = [];
      for (const item of incoming) {
        const key = String(item.id || "");
        if (!key || proactiveSeenRef.current[key]) continue;
        proactiveSeenRef.current[key] = true;
        justIn.push(item);
      }
      if (!justIn.length) return;

      for (const item of justIn) {
        const detail = (item.detail || "").trim();
        const toastText = detail ? `${item.title} 路 ${detail}` : item.title;
        const level = String(item.level || "info").toLowerCase();
          showToast(
            toastText.slice(0, 220),
            level === "error" ? "error" : level === "warning" ? "warning" : level === "success" ? "success" : "info"
          );
        if (document.hidden) {
          pushSystemNotification(item);
        }
      }
    } catch {
      // ignore transient proactive polling failures
    }
  }, [pushSystemNotification, showToast, workspaceScope]);

  const refreshDeviceMode = React.useCallback(async () => {
    try {
      const mode = await getAelinDeviceMode();
      setDeviceModeState(mode);
    } catch {
      // ignore temporary failures
    }
  }, []);

  const refreshDeviceCapabilities = React.useCallback(async () => {
    try {
      const caps = await getAelinDeviceCapabilities();
      setDeviceCapabilities(caps);
    } catch {
      // ignore temporary failures
    }
  }, []);

  const refreshDeviceProcesses = React.useCallback(async () => {
    setDeviceBusy(true);
    try {
      const ret = await getAelinDeviceProcesses(deviceSortBy, 48);
      setDeviceProcesses(ret.items || []);
      setDeviceProcessMeta({
        emptyReason: ret.empty_reason || "",
        platform: ret.platform || "unknown",
        filterContext: ret.filter_context || {},
      });
    } catch (error) {
      showToast(error instanceof Error ? error.message : "读取进程失败", "error");
    } finally {
      setDeviceBusy(false);
    }
  }, [deviceSortBy, showToast]);

  const openDeviceDialog = React.useCallback(() => {
    setDeviceDialogOpen(true);
    void refreshDeviceMode();
    void refreshDeviceCapabilities();
    void refreshDeviceProcesses();
  }, [refreshDeviceCapabilities, refreshDeviceMode, refreshDeviceProcesses]);

  const applyDeviceModeAction = React.useCallback(
    async (mode: DeviceMode) => {
      setDeviceModeApplying(mode);
      try {
        const ret = await applyAelinDeviceMode(mode);
        setDeviceModeState(ret);
        const severity =
          ret.status === "applied"
            ? "success"
            : ret.status === "partial" || ret.status === "degraded"
              ? "warning"
              : "info";
        const warningText = (ret.warnings || []).slice(0, 1).join(";");
        showToast(
          warningText ? `${ret.summary || `模式已切换 ${mode}`} · ${warningText}` : ret.summary || `模式已切换 ${mode}`,
          severity
        );
      } catch (error) {
        showToast(error instanceof Error ? error.message : "模式切换失败", "error");
      } finally {
        setDeviceModeApplying(null);
      }
    },
    [showToast]
  );

  const handleDeviceProcessAction = React.useCallback(
    async (pid: number, action: "terminate" | "set_low_priority" | "set_high_priority") => {
      setDeviceActionBusyPid(pid);
      try {
        const ret = await runAelinDeviceProcessAction(pid, action);
        showToast(
          ret.ok ? `已执行：${ret.detail || action}` : `执行失败：${ret.detail || action}`,
          ret.ok ? "success" : "error"
        );
        await refreshDeviceProcesses();
      } catch (error) {
        showToast(error instanceof Error ? error.message : "进程操作失败", "error");
      } finally {
        setDeviceActionBusyPid(null);
      }
    },
    [refreshDeviceProcesses, showToast]
  );

  const runDeviceOptimize = React.useCallback(async () => {
    setDeviceOptimizeBusy(true);
    try {
      const ret = await optimizeAelinDeviceProcesses();
      setDeviceOptimizeResult(ret);
      showToast(
        ret.optimized_count > 0
          ? `已优化 ${ret.optimized_count} 个高占用进程`
          : "没有可优化的高占用进程",
        ret.optimized_count > 0 ? "success" : "info"
      );
      await refreshDeviceProcesses();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "优化失败", "error");
    } finally {
      setDeviceOptimizeBusy(false);
    }
  }, [refreshDeviceProcesses, showToast]);

  const getDefaultLlmBaseUrl = React.useCallback(
    (providerId: string, catalog: ModelCatalogResponse | null = llmCatalog) => {
      const normalizedProviderId = normalizeProviderId(providerId) || "rule_based";
      if (normalizedProviderId === "rule_based") return "https://api.openai.com/v1";
      const matched = (catalog?.providers ?? []).find((provider) => provider.id === normalizedProviderId);
      return (matched?.api || "").trim() || "https://api.openai.com/v1";
    },
    [llmCatalog]
  );

  const hydrateLlmDialogState = React.useCallback(
    (config: AgentConfig, catalog: ModelCatalogResponse | null) => {
      const provider = normalizeProviderId(config.provider || "rule_based") || "rule_based";
      const catalogIds = new Set((catalog?.providers ?? []).map((item) => item.id));
      setLlmProvider(provider);
      if (provider === "rule_based") {
        setLlmProviderSelectValue("rule_based");
        setLlmCustomProviderId("");
      } else if (catalogIds.has(provider)) {
        setLlmProviderSelectValue(provider);
      } else {
        setLlmProviderSelectValue(CUSTOM_PROVIDER_OPTION);
        setLlmCustomProviderId(provider);
      }
      setLlmBaseUrl(config.base_url || getDefaultLlmBaseUrl(provider, catalog));
      setLlmModel(config.model || "gpt-4o-mini");
      setLlmTemperature(Number.isFinite(config.temperature) ? config.temperature : 0.2);
      setLlmHasApiKey(Boolean(config.has_api_key));
      setLlmApiKey("");
    },
    [getDefaultLlmBaseUrl]
  );

  const loadLlmDialogData = React.useCallback(async () => {
    setLlmLoading(true);
    try {
      const [config, catalog] = await Promise.all([getAgentConfig(), getAgentCatalog(false)]);
      setLlmCatalog(catalog);
      hydrateLlmDialogState(config, catalog);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "加载模型配置失败", "error");
    } finally {
      setLlmLoading(false);
    }
  }, [hydrateLlmDialogState, showToast]);

  const openLlmDialog = React.useCallback(() => {
    setLlmDialogOpen(true);
    void loadLlmDialogData();
  }, [loadLlmDialogData]);

  const handleLlmCatalogRefresh = React.useCallback(async () => {
    setLlmRefreshing(true);
    try {
      const fresh = await getAgentCatalog(true);
      setLlmCatalog(fresh);
      showToast(`模型目录已刷新（${fresh.providers.length} 个服务商）`, "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "刷新模型目录失败", "error");
    } finally {
      setLlmRefreshing(false);
    }
  }, [showToast]);

  const handleLlmSave = React.useCallback(async () => {
    const provider = normalizeProviderId(llmProvider);
    if (!provider) {
      showToast("请填写服务商 ID", "error");
      return;
    }
    if (provider !== "rule_based") {
      if (!llmBaseUrl.trim()) {
          showToast("请填写 Base URL", "error");
        return;
      }
      if (!llmModel.trim()) {
          showToast("请填写模型 ID", "error");
        return;
      }
    }

    setLlmSaving(true);
    try {
      const payload: { provider: string; base_url?: string; model?: string; temperature: number; api_key?: string } = {
        provider,
        temperature: Number.isFinite(llmTemperature) ? llmTemperature : 0.2,
      };
      if (provider !== "rule_based") {
        payload.base_url = llmBaseUrl.trim();
        payload.model = llmModel.trim();
      }
      if (llmApiKey.trim()) {
        payload.api_key = llmApiKey.trim();
      }
      const updated = await updateAgentConfig(payload);
      hydrateLlmDialogState(updated, llmCatalog);
      showToast("Aelin 模型配置已保存", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "保存模型配置失败", "error");
    } finally {
      setLlmSaving(false);
    }
  }, [hydrateLlmDialogState, llmApiKey, llmBaseUrl, llmCatalog, llmModel, llmProvider, llmTemperature, showToast]);

  const handleLlmTest = React.useCallback(async () => {
    setLlmTesting(true);
    try {
      const ret = await testAgent();
      showToast(`测试通过：${ret.message || "OK"}`, "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "测试失败", "error");
    } finally {
      setLlmTesting(false);
    }
  }, [showToast]);

  React.useEffect(() => {
    void refreshContext();
  }, [refreshContext]);

  React.useEffect(() => {
    if (!trackingDialogOpen) return;
    void refreshTracking();
  }, [refreshTracking, trackingDialogOpen]);

  React.useEffect(() => {
    void refreshTracking();
  }, [refreshTracking]);

  React.useEffect(() => {
    if (!trackingItems.length) {
      setTrackingActiveTargetId(null);
      setTrackingChanges([]);
      setTrackingSnapshots([]);
      return;
    }
    if (trackingActiveTargetId === null || !trackingItems.some((item) => Number(item.target_id || 0) === trackingActiveTargetId)) {
      const first = trackingItems.find((item) => Number(item.target_id || 0) > 0);
      setTrackingActiveTargetId(first ? Number(first.target_id || 0) : null);
    }
  }, [trackingActiveTargetId, trackingItems]);

  React.useEffect(() => {
    if (!trackingDialogOpen) return;
    const targetId = Number(activeTrackingItem?.target_id || 0);
    if (!targetId) {
      setTrackingChanges([]);
      setTrackingSnapshots([]);
      return;
    }
    void refreshTrackingDetail(targetId);
  }, [activeTrackingItem?.target_id, refreshTrackingDetail, trackingDialogOpen]);

  React.useEffect(() => {
    if (!notificationDialogOpen) return;
    void refreshNotifications();
  }, [notificationDialogOpen, refreshNotifications]);

  React.useEffect(() => {
    void refreshNotifications();
  }, [refreshNotifications]);

  React.useEffect(() => {
    for (const item of notificationItems) {
      const key = String(item.id || "");
      if (!key) continue;
      proactiveSeenRef.current[key] = true;
    }
  }, [notificationItems]);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("Notification" in window)) return;
    if (Notification.permission !== "default") return;
    const timer = window.setTimeout(() => {
      void Notification.requestPermission().catch(() => "default");
    }, 1800);
    return () => window.clearTimeout(timer);
  }, []);

  React.useEffect(() => {
    void pollProactive();
    const timer = window.setInterval(() => {
      void pollProactive();
    }, PROACTIVE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [pollProactive]);

  React.useEffect(() => {
    if (!deviceDialogOpen) return;
    void refreshDeviceProcesses();
  }, [deviceDialogOpen, refreshDeviceProcesses]);

  React.useEffect(() => {
    if (!deviceDialogOpen) return;
    void refreshDeviceMode();
  }, [deviceDialogOpen, refreshDeviceMode]);

  React.useEffect(() => {
    if (llmProvider === "rule_based" || llmIsCustomProvider || !llmSelectedProvider) return;
    if (
      llmSelectedProvider.models.length > 0 &&
      !llmSelectedProvider.models.some((model) => model.id === llmModel)
    ) {
      setLlmModel(llmSelectedProvider.models[0].id);
    }
  }, [llmIsCustomProvider, llmModel, llmProvider, llmSelectedProvider]);

  React.useEffect(() => {
    if (embedded) return;
    const panel = new URLSearchParams(location.search || "").get("panel") || "";
    if (panel.trim().toLowerCase() === "desk") {
      setDeskOpen(true);
    }
  }, [embedded, location.search]);

  React.useEffect(() => {
    return () => {
      if (handoffFXTimerRef.current !== null) {
        window.clearTimeout(handoffFXTimerRef.current);
      }
    };
  }, []);

  React.useEffect(() => {
    if (!sessions.length) {
      const created = newSession();
      setSessions([created]);
      setActiveSessionId(created.id);
      return;
    }
    if (!sessions.some((item) => item.id === activeSessionId)) {
      setActiveSessionId(sessions[0].id);
    }
  }, [activeSessionId, sessions]);

  React.useEffect(() => {
    setTrackingSheet(null);
  }, [activeSessionId]);

  const updateActiveMessages = React.useCallback(
    (updater: (prev: ChatMessage[]) => ChatMessage[]) => {
      setSessions((prev) =>
        prev.map((session) => {
          if (session.id !== activeSessionId) return session;
          const nextMessages = updater(session.messages || []);
          return {
            ...session,
            messages: nextMessages,
            title: deriveSessionTitle(nextMessages),
            updated_at: Date.now(),
          };
        })
      );
    },
    [activeSessionId]
  );

  React.useEffect(() => {
    const el = timelineRef.current;
    if (!el) return;
    const delta = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (stickToBottomRef.current || delta < 120) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  React.useEffect(() => {
    const el = timelineRef.current;
    if (!el) return;
    const onScroll = () => {
      const delta = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickToBottomRef.current = delta < 96;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  React.useEffect(() => {
    if (!latestSparkMessageId) return;
    const timer = window.setTimeout(() => setLatestSparkMessageId(""), 1400);
    return () => window.clearTimeout(timer);
  }, [latestSparkMessageId]);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const compact = sessions
        .slice()
        .sort((a, b) => b.updated_at - a.updated_at)
        .slice(0, MAX_PERSISTED_SESSIONS)
        .map((session) => ({
          id: session.id,
          title: session.title,
          updated_at: session.updated_at,
          messages: toPersistedMessages(session.messages || []),
        }));
      const payload = { version: 1, sessions: compact, active_id: activeSessionId, saved_at: Date.now() };
      window.localStorage.setItem(AELIN_SESSIONS_STORAGE_KEY, JSON.stringify(payload));
      window.localStorage.removeItem(AELIN_CHAT_STORAGE_KEY);
    } catch {
      // Ignore storage failures (e.g., quota exceeded/private mode restrictions).
    }
  }, [activeSessionId, sessions]);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(AELIN_LAST_SESSION_KEY, activeSessionId);
    } catch {
      // ignore storage failures
    }
  }, [activeSessionId]);

  React.useEffect(() => {
    if (embedded) return;
    const currentSearch = location.search || "";
    if (!currentSearch) return;
    if (handledDeskReturnRef.current === currentSearch) return;
    const qs = new URLSearchParams(currentSearch);
    if ((qs.get("from") || "").trim().toLowerCase() !== "desk") return;
    handledDeskReturnRef.current = currentSearch;

    const sid = (qs.get("session_id") || "").trim();
    const focusQuery = (qs.get("focus_query") || "").trim();
    const resumePrompt = (qs.get("resume_prompt") || "").trim();
    const focusMessageId = Number(qs.get("focus_message_id") || 0);
    const source = (qs.get("highlight_source") || "").trim();

    if (sid && sessions.some((item) => item.id === sid)) {
      setActiveSessionId(sid);
    }
    if (resumePrompt) {
      setInput((prev) => (prev.trim() ? prev : resumePrompt));
    } else if (focusQuery) {
      setInput((prev) => (prev.trim() ? prev : `继续围绕这个主题：${focusQuery}`));
    }
    if (Number.isFinite(focusMessageId) && focusMessageId > 0) {
      playHandoffFX(
        "Desk -> Aelin",
        source
          ? `已带回 ${source} 的观察结果（消息 #${focusMessageId}）`
          : `已带回焦点消息 #${focusMessageId}`
      );
      showToast(
        source ? `已从 Desk 返回，继续围绕 ${source}（消息 #${focusMessageId}）` : `已从 Desk 返回，焦点消息 #${focusMessageId}`,
        "info"
      );
    } else {
      playHandoffFX("Desk -> Aelin", "已返回聊天，可继续追问。");
      showToast("已从 Desk 返回，可继续追问。", "info");
    }
    navigate("/", { replace: true });
  }, [embedded, location.search, navigate, playHandoffFX, sessions, showToast]);

  const resetConversation = React.useCallback(() => {
    const created = newSession();
    setSessions((prev) => [created, ...prev].slice(0, MAX_PERSISTED_SESSIONS));
    setActiveSessionId(created.id);
    setPendingImages([]);
    setTrackingSheet(null);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(AELIN_CHAT_STORAGE_KEY);
      } catch {
        // no-op
      }
    }
  }, []);

  const copyText = React.useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        showToast("已复制", "success");
      } catch {
        showToast("复制失败", "error");
      }
    },
    [showToast]
  );

  const appendFiles = React.useCallback(
    async (files: File[]) => {
      const existing = pendingImages.length;
      if (existing >= 4) {
        showToast("最多上传 4 张图片", "info");
        return;
      }
      const candidates = files.filter((file) => file.type.startsWith("image/")).slice(0, 4 - existing);
      if (!candidates.length) {
        showToast("请选择图片文件", "info");
        return;
      }
      const oversized = candidates.find((file) => file.size > 4 * 1024 * 1024);
      if (oversized) {
        showToast(`图片过大：${oversized.name}（限 4MB）`, "error");
        return;
      }
      try {
        const urls = await Promise.all(candidates.map((file) => fileToDataUrl(file)));
        setPendingImages((prev) => [
          ...prev,
          ...urls.map((dataUrl, idx) => ({
            id: nextMessageId(),
            dataUrl,
            name: candidates[idx]?.name || `image-${Date.now()}`,
          })),
        ]);
      } catch (error) {
        showToast(error instanceof Error ? error.message : "图片读取失败", "error");
      }
    },
    [pendingImages.length, showToast]
  );

  const send = React.useCallback(
    async (raw: string) => {
      const query = raw.trim();
      if ((!query && pendingImages.length === 0) || busy) return;
      const requestQuery = query || "请分析我上传的图片并结合上下文回复。";

      setBusy(true);
      setInput("");
      const assistantId = nextMessageId();
      const nowTs = Date.now();
      const sessionIdAtSend = activeSessionId;
      const historyForSend = (activeSession?.messages || [])
        .filter((item) => !item.pending && (item.role === "user" || item.role === "assistant"))
        .slice(-10)
        .map((item) => ({ role: item.role, content: item.content }));
      const imagesForSend: AelinImageInput[] = pendingImages.slice(0, 4).map((img) => ({
        data_url: img.dataUrl,
        name: img.name,
      }));
      setPendingImages([]);

      setSessions((prev) =>
        prev.map((session) =>
          session.id === sessionIdAtSend
            ? {
                ...session,
                messages: [
                  ...session.messages,
                  { id: nextMessageId(), role: "user", content: query || "（图片）", ts: nowTs, images: imagesForSend },
                  {
                    id: assistantId,
                    role: "assistant",
                    content: "",
                    ts: nowTs + 1,
                    pending: true,
                    tool_trace: [{ stage: "main_agent", status: "running", detail: "主控已接收请求", count: 0, ts: nowTs + 1 }],
                  },
                ],
                title: deriveSessionTitle([
                  ...session.messages,
                  { id: "tmp", role: "user", content: query || "（图片）", ts: nowTs, images: imagesForSend },
                ]),
                updated_at: Date.now(),
              }
            : session
        )
      );

      let finalResult: {
        answer: string;
        expression: string;
        citations: AelinCitation[];
        actions: AelinAction[];
        tool_trace: AelinToolStep[];
      } | null = null;

      try {
        const stream = aelinChatStream(requestQuery, {
          use_memory: true,
          max_citations: 8,
          workspace: workspaceScope,
          images: imagesForSend,
          history: historyForSend,
          search_mode: "auto",
        });

        for await (const evt of stream) {
          if (evt.type === "start") {
            startProgressTransition(() => {
              setSessions((prev) =>
                prev.map((session) =>
                  session.id === sessionIdAtSend
                    ? {
                        ...session,
                        messages: session.messages.map((item) =>
                          item.id === assistantId && item.pending
                            ? {
                                ...item,
                                tool_trace: upsertTraceStep(item.tool_trace || [], {
                                  stage: "main_agent",
                                  status: "running",
                                  detail: "主控开始编排子任务",
                                  count: 1,
                                }),
                              }
                            : item
                        ),
                      }
                    : session
                )
              );
            });
            continue;
          }

          if (evt.type === "trace") {
            startProgressTransition(() => {
              setSessions((prev) =>
                prev.map((session) =>
                  session.id === sessionIdAtSend
                    ? {
                        ...session,
                        messages: session.messages.map((item) =>
                          item.id === assistantId && item.pending
                            ? {
                                ...item,
                                tool_trace: upsertTraceStep(item.tool_trace || [], evt.step),
                              }
                            : item
                        ),
                      }
                    : session
                )
              );
            });
            continue;
          }

          if (evt.type === "evidence") {
            const citation = evt.citation;
            const queryText = (evt.query || "").trim() || "检索子任务";
            const queryIndex = Number(evt.progress?.query_index || 0);
            const queryTotal = Number(evt.progress?.query_total || 0);
            const evidenceCount = Number(evt.progress?.evidence_count || 0);
            const sourceBits = [evt.provider || "", evt.fetch_mode || ""].filter((x) => !!x.trim()).join("/");
            const progressText =
              queryTotal > 0
                ? ` (${Math.min(Math.max(queryIndex, 1), queryTotal)}/${queryTotal})`
                : "";
            const sourceText = sourceBits ? ` [${sourceBits}]` : "";
            const detail = `证据命中：${queryText}${progressText}${sourceText}`;
            startProgressTransition(() => {
              setSessions((prev) =>
                prev.map((session) =>
                  session.id === sessionIdAtSend
                    ? {
                        ...session,
                        messages: session.messages.map((item) =>
                          item.id === assistantId && item.pending
                            ? {
                                ...item,
                                citations: mergeCitations(item.citations || [], [citation], 12),
                                citation_snippets: mergeCitationSnippets(item.citation_snippets, [
                                  { citation, snippet: evt.snippet || "" },
                                ]),
                                tool_trace: upsertTraceStep(
                                  upsertTraceStep(item.tool_trace || [], {
                                    stage: "web_search",
                                    status: "running",
                                    detail,
                                    count: evidenceCount,
                                  }),
                                  {
                                    stage: "message_hub",
                                    status: "running",
                                    detail: "证据汇聚中",
                                    count: evidenceCount,
                                  }
                                ),
                              }
                            : item
                        ),
                      }
                    : session
                )
              );
            });
            continue;
          }

          if (evt.type === "confirmed") {
            const target = (evt.items || [])[0] || "";
            const sourceCount = Number(evt.source_count || 0);
            const detail = target
              ? `建议追踪 ${target}${sourceCount > 0 ? `（来源 ${sourceCount}）` : ""}`
              : "识别到可跟踪主题";
            startProgressTransition(() => {
              setSessions((prev) =>
                prev.map((session) =>
                  session.id === sessionIdAtSend
                    ? {
                        ...session,
                        messages: session.messages.map((item) =>
                          item.id === assistantId && item.pending
                            ? {
                                ...item,
                                tool_trace: upsertTraceStep(item.tool_trace || [], {
                                  stage: "trace_agent",
                                  status: "completed",
                                  detail,
                                  count: Number((evt.items || []).length || 0),
                                }),
                              }
                            : item
                        ),
                      }
                    : session
                )
              );
            });
            continue;
          }

          if (evt.type === "final") {
            finalResult = evt.result;
            setSessions((prev) =>
              prev.map((session) =>
                session.id === sessionIdAtSend
                  ? {
                      ...session,
                      messages: session.messages.map((item) =>
                        item.id === assistantId
                          ? {
                              ...item,
                              pending: false,
                              content: evt.result.answer || "当前未生成文本回答。",
                              expression: normalizeExpressionId(evt.result.expression),
                              citations: mergeCitations(item.citations || [], evt.result.citations || [], 12),
                              citation_snippets: item.citation_snippets,
                              actions: evt.result.actions || [],
                              tool_trace: (evt.result.tool_trace || []).map(normalizeTraceStep),
                            }
                          : item
                      ),
                      updated_at: Date.now(),
                    }
                  : session
              )
            );
            continue;
          }

          if (evt.type === "error") {
            throw new Error(evt.message || "stream error");
          }

          if (evt.type === "done") {
            continue;
          }
        }

        if (!finalResult) {
          const result = await aelinChat(requestQuery, {
            use_memory: true,
            max_citations: 8,
            workspace: workspaceScope,
            images: imagesForSend,
            history: historyForSend,
            search_mode: "auto",
          });
          finalResult = result;
          setSessions((prev) =>
            prev.map((session) =>
              session.id === sessionIdAtSend
                ? {
                    ...session,
                    messages: session.messages.map((item) =>
                      item.id === assistantId
                        ? {
                            ...item,
                            pending: false,
                            content: result.answer || "当前未生成文本回答。",
                            expression: normalizeExpressionId(result.expression),
                            citations: mergeCitations(item.citations || [], result.citations || [], 12),
                            citation_snippets: item.citation_snippets,
                            actions: result.actions || [],
                            tool_trace: (result.tool_trace || []).map(normalizeTraceStep),
                          }
                        : item
                    ),
                    updated_at: Date.now(),
                  }
                : session
            )
          );
        }

        if (finalResult) {
          setLatestSparkMessageId(assistantId);
          const trackAction = (finalResult.actions || []).find((it) => it.kind === "confirm_track");
          if (trackAction) {
            const target = (trackAction.payload.target || "").trim().toLowerCase();
            if (!dismissedTrackTargetsRef.current[target]) {
              setTrackingSheet({ action: trackAction, messageId: assistantId });
            }
          } else {
            setTrackingSheet(null);
          }
        }

        void refreshContext();
      } catch (error) {
        setSessions((prev) =>
          prev.map((session) =>
            session.id === sessionIdAtSend
              ? {
                  ...session,
                  messages: session.messages.map((item) =>
                    item.id === assistantId
                      ? {
                          ...item,
                          pending: false,
                          content:
                            error instanceof Error
                              ? `请求失败：${error.message}`
                              : "请求失败，请稍后重试。",
                          expression: "exp-07",
                          tool_trace: upsertTraceStep(
                            upsertTraceStep(item.tool_trace || [], {
                              stage: "main_agent",
                              status: "completed",
                              detail: "请求已发送",
                              count: 1,
                            }),
                            {
                              stage: "generation",
                              status: "failed",
                              detail: error instanceof Error ? error.message : "request failed",
                              count: 0,
                            }
                          ),
                        }
                      : item
                  ),
                  updated_at: Date.now(),
                }
              : session
          )
        );
      } finally {
        setBusy(false);
      }
    },
    [activeSession?.messages, activeSessionId, busy, pendingImages, refreshContext, startProgressTransition, workspaceScope]
  );

  const onActionClick = React.useCallback(
    async (action: AelinAction) => {
      if (action.kind === "open_desk" || action.kind === "open_todos") {
        const path = action.payload.path || "/desk";
        if (path.startsWith("/desk")) {
          openDeskWithContext({
            messageId: action.payload.message_id,
            contactId: action.payload.contact_id,
            focusQuery: action.payload.query || "",
            highlightSource: action.payload.source || lastAssistantCitation?.source_label || "",
            resumePrompt: action.payload.query || "",
          });
        } else {
          navigate(path);
        }
        return;
      }
      if (action.kind === "open_settings") {
        const targetPath = (action.payload.path || "/settings").trim() || "/settings";
        if (targetPath === "/settings") {
          openLlmDialog();
        } else {
          navigate(targetPath);
        }
        return;
      }
      if (action.kind === "open_message") {
        const messageId = action.payload.message_id;
        openDeskWithContext({
          messageId,
          contactId: action.payload.contact_id,
          focusQuery: action.payload.query || "",
          highlightSource: action.payload.source || lastAssistantCitation?.source_label || "",
          resumePrompt: action.payload.query || "",
        });
        return;
      }
      if (action.kind === "track_topic") {
        setInput(action.payload.query || "");
        showToast("已填入追踪主题。", "info");
        return;
      }
      if (action.kind === "open_tracking") {
        const targetId = Number(action.payload.target_id || 0);
        if (targetId > 0) {
          setTrackingActiveTargetId(targetId);
          void refreshTrackingDetail(targetId, { silent: true });
        }
        setTrackingDialogOpen(true);
        return;
      }
      if (action.kind === "confirm_track") {
        setTrackingSheet({ action, messageId: nextMessageId() });
      }
    },
    [lastAssistantCitation?.source_label, navigate, openDeskWithContext, openLlmDialog, refreshTrackingDetail, showToast]
  );

  const resolveCitationUrl = React.useCallback(
    async (item: AelinCitation): Promise<{ url: string; detail: MessageDetail | null }> => {
      const id = Number(item.message_id || 0);
      if (id > 0 && citationUrlCacheRef.current[id]) {
        return { url: citationUrlCacheRef.current[id], detail: null };
      }
      const detail = await getMessage(item.message_id);
      const url = extractFirstUrl(detail.body || "") || extractFirstUrl(detail.subject || "");
      if (id > 0 && url) {
        citationUrlCacheRef.current[id] = url;
      }
      return { url, detail };
    },
    []
  );

  const handleCitationOpen = React.useCallback(
    async (item: AelinCitation) => {
      setCitationPreview({ open: true, citation: item, url: "", loading: true, error: "" });
      try {
        const { url, detail } = await resolveCitationUrl(item);
        if (url) {
          setCitationPreview({ open: true, citation: item, url, loading: false, error: "" });
          return;
        }
        setCitationPreview({ open: false, citation: null, url: "", loading: false, error: "" });
        setCitationDrawer({
          open: true,
          citation: item,
          detail,
          loading: false,
          error: "该证据暂无可跳转网页链接，已切换到详情视图。",
        });
      } catch (error) {
        setCitationPreview({ open: false, citation: null, url: "", loading: false, error: "" });
        setCitationDrawer({
          open: true,
          citation: item,
          detail: null,
          loading: false,
          error: error instanceof Error ? error.message : "加载详情失败",
        });
      }
    },
    [resolveCitationUrl]
  );

  const handleTrackingChoice = React.useCallback(
    async (mode: "track" | "once" | "dismiss") => {
      if (!trackingSheet) return;
      const target = (trackingSheet.action.payload.target || "").trim();
      if (!target) {
        setTrackingSheet(null);
        return;
      }
      if (mode === "dismiss") {
        dismissedTrackTargetsRef.current[target.toLowerCase()] = true;
        setTrackingSheet(null);
        showToast("已关闭该主题的跟踪提醒。", "info");
        return;
      }
      if (mode === "once") {
        setTrackingSheet(null);
        showToast("本次仅回答，不开启持续跟踪。", "info");
        return;
      }
      try {
        const ret = await aelinConfirmTrack({
          target,
          source: trackingSheet.action.payload.source || "auto",
          query: trackingSheet.action.payload.query || "",
          workspace: workspaceScope,
          track_type: trackingSheet.action.payload.track_type === "url" ? "url" : "term",
          notify_level: "all",
        });
        updateActiveMessages((prev) => [
          ...prev,
          {
            id: nextMessageId(),
            role: "assistant",
            content: ret.message || "已处理你的跟踪请求。",
            expression: ret.status === "needs_config" ? "exp-05" : "exp-02",
            ts: Date.now(),
            actions: ret.actions || [],
          },
        ]);
        setTrackingSheet(null);
        void refreshContext();
        await refreshTracking();
        if (ret.target_id && Number(ret.target_id) > 0) {
          const targetId = Number(ret.target_id);
          setTrackingActiveTargetId(targetId);
          await refreshTrackingDetail(targetId, { silent: true });
        }
        if (ret.status === "needs_config") {
          const goSettings = await confirm({
            title: "需要先配置数据源",
            message: `当前缺少 ${ret.provider || "对应"} 配置，是否现在去配置模型？`,
            confirmLabel: "立即配置",
            cancelLabel: "稍后",
          });
          if (goSettings) openLlmDialog();
        } else {
          showToast("已开启持续跟踪", "success");
        }
      } catch (error) {
        showToast(error instanceof Error ? error.message : "跟踪开启失败", "error");
      }
    },
    [confirm, openLlmDialog, refreshContext, refreshTracking, refreshTrackingDetail, showToast, trackingSheet, updateActiveMessages, workspaceScope]
  );

  const runStoryMode = React.useCallback(async () => {
    setStoryBusy(true);
    try {
      const ctx = contextSnapshot || (await getAelinContext(workspaceScope, ""));
      if (!contextSnapshot) setContextSnapshot(ctx);
      const story = buildStoryFromContext(ctx);
      updateActiveMessages((prev) => [
        ...prev,
        {
          id: nextMessageId(),
          role: "assistant",
          content: story,
          expression: "exp-03",
          ts: Date.now(),
          tool_trace: [
            { stage: "planner", status: "completed", detail: "story mode enabled", count: 1 },
            { stage: "local_search", status: "completed", detail: "used 24h local context", count: (ctx.focus_items || []).length },
          ],
        },
      ]);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "故事模式生成失败", "error");
    } finally {
      setStoryBusy(false);
    }
  }, [contextSnapshot, showToast, updateActiveMessages, workspaceScope]);

  const handleNotificationAction = React.useCallback(
    (item: AelinNotificationItem) => {
      const kind = String(item.action_kind || "").trim();
      const payload = item.action_payload || {};
      if (kind === "open_message" && payload.message_id) {
        openDeskWithContext({
          messageId: payload.message_id,
          focusQuery: item.title || "",
          highlightSource: item.source || "",
          resumePrompt: `继续围绕这条通知深入分析：${item.title}`,
        });
        setNotificationDialogOpen(false);
        return;
      }
      if (kind === "open_todo") {
        openDeskWithContext({
          focusQuery: item.title || "查看待办",
          highlightSource: "todo",
          resumePrompt: "继续处理我的待办并给我优先级建议。",
        });
        setNotificationDialogOpen(false);
        return;
      }
      if (kind === "open_tracking") {
        const targetId = Number(payload.target_id || 0);
        if (targetId > 0) {
          setTrackingActiveTargetId(targetId);
          void refreshTrackingDetail(targetId, { silent: true });
        }
        setNotificationDialogOpen(false);
        setTrackingDialogOpen(true);
        return;
      }
      if (kind === "open_device") {
        setNotificationDialogOpen(false);
        openDeviceDialog();
        return;
      }
      if (kind === "open_brief") {
        void runStoryMode();
        setNotificationDialogOpen(false);
      }
    },
    [openDeskWithContext, openDeviceDialog, refreshTrackingDetail, runStoryMode]
  );

  return (
    <Box
      component={motion.div}
      initial={embedded ? undefined : { opacity: 0, y: 8 }}
      animate={embedded ? undefined : { opacity: 1, y: 0 }}
      transition={embedded ? undefined : { duration: 0.24 }}
      sx={{
        height: embedded ? "100%" : "100dvh",
        maxHeight: embedded ? "100%" : "100dvh",
        width: embedded ? "100%" : compactFramed ? "min(100vw, 430px)" : "100%",
        display: "flex",
        flexDirection: "column",
        bgcolor: "background.default",
        overflow: "hidden",
        fontSize: compactMode ? "0.94rem" : "1rem",
        mx: embedded ? 0 : compactFramed ? "auto" : 0,
        borderLeft: compactFramed ? `1px solid ${alpha(theme.palette.divider, 0.8)}` : "none",
        borderRight: compactFramed ? `1px solid ${alpha(theme.palette.divider, 0.8)}` : "none",
      }}
    >
      <Box
        sx={{
          height: compactMode ? "auto" : 64,
          minHeight: compactMode ? 74 : 64,
          py: compactMode ? 0.75 : 0,
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          flexShrink: 0,
          position: "relative",
          zIndex: 2,
          bgcolor: alpha(theme.palette.background.default, 0.82),
          backdropFilter: "blur(8px)",
        }}
      >
        <Container
          maxWidth={mainContainerMaxWidth}
          sx={{
            display: "flex",
            flexDirection: compactMode ? "column" : "row",
            alignItems: compactMode ? "stretch" : "center",
            justifyContent: "space-between",
            rowGap: compactMode ? 0.65 : 0,
            px: { xs: 0.9, sm: compactMode ? 1.3 : 2.2 },
          }}
        >
          <Stack direction="row" spacing={1.1} alignItems="center" sx={{ width: compactMode ? "100%" : "auto" }}>
            <Avatar
              src={AELIN_LOGO_SRC}
              sx={{ width: 34, height: 34, borderRadius: 1.2, bgcolor: "transparent", border: "none", boxShadow: "none" }}
              imgProps={{ style: { objectFit: "cover", objectPosition: "center 24%" } }}
            />
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.06, fontSize: "1.03rem" }}>
                Aelin
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.8rem" }}>
                Chat
              </Typography>
            </Box>
          </Stack>

          <Stack
            direction="row"
            spacing={0.55}
            alignItems="center"
            flexWrap={compactMode ? "wrap" : "nowrap"}
            useFlexGap
            sx={{
              width: compactMode ? "100%" : "auto",
              justifyContent: compactMode ? "flex-start" : "flex-end",
              rowGap: compactMode ? 0.5 : 0,
            }}
          >
            <FormControl
              size="small"
              sx={{
                minWidth: compactMode ? 150 : 170,
                width: compactMode ? "100%" : "auto",
                flex: compactMode ? "1 1 210px" : "0 0 auto",
              }}
            >
              <Select
                value={activeSession?.id || ""}
                onChange={(event) => setActiveSessionId(String(event.target.value || ""))}
                displayEmpty
                sx={{
                  borderRadius: 1.4,
                  fontSize: "0.85rem",
                  "& .MuiSelect-select": { py: compactMode ? 0.58 : 0.6, pr: 2.2 },
                }}
              >
                {sortedSessions.map((session) => (
                  <MenuItem key={session.id} value={session.id}>
                    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", gap: 1 }}>
                      <Typography variant="body2" sx={{ maxWidth: 132, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {session.title || "新对话"}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {formatTime(session.updated_at)}
                      </Typography>
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Tooltip title="新对话">
              <IconButton onClick={resetConversation}>
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="故事模式">
              <span>
                <IconButton onClick={runStoryMode} disabled={storyBusy}>
                  <TimelineIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="跟踪列表">
              <IconButton onClick={() => setTrackingDialogOpen(true)}>
                <Badge
                  color="primary"
                  badgeContent={Math.min(99, trackingUnreadCount || trackingItems.length)}
                  invisible={!trackingUnreadCount && !trackingItems.length}
                  overlap="circular"
                >
                  <TrackChangesIcon fontSize="small" />
                </Badge>
              </IconButton>
            </Tooltip>
            <Tooltip title="通知中心">
              <IconButton onClick={() => setNotificationDialogOpen(true)}>
                <Badge
                  color="error"
                  badgeContent={unreadNotificationCount}
                  invisible={!unreadNotificationCount}
                  overlap="circular"
                >
                  <NotificationsNoneIcon fontSize="small" />
                </Badge>
              </IconButton>
            </Tooltip>
            <Tooltip title="设备中心">
              <IconButton onClick={openDeviceDialog}>
                <ComputerIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="分层记忆">
              <IconButton onClick={() => setMemoryDialogOpen(true)}>
                <LayersIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="打开观察台">
              <IconButton onClick={() => setDeskOpen(true)}>
                <TravelExploreIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="设置">
              <IconButton onClick={openLlmDialog}>
                <SettingsIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            {embedded && onRequestClose ? (
              <Tooltip title="收起 Aelin">
                <IconButton onClick={onRequestClose}>
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            ) : null}
          </Stack>
        </Container>
      </Box>

      {handoffFX ? (
        <Box
          component={motion.div}
          initial={{ opacity: 0, y: -8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -6, scale: 0.99 }}
          transition={{ duration: 0.2 }}
          sx={{
            position: "fixed",
            top: { xs: 72, md: 80 },
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 1500,
            pointerEvents: "none",
            width: "min(620px, calc(100vw - 28px))",
          }}
        >
          <Paper
            variant="outlined"
            sx={{
              px: 1.1,
              py: 0.85,
              borderRadius: 1.8,
              borderColor: alpha(theme.palette.primary.main, 0.34),
              bgcolor: alpha(theme.palette.background.paper, 0.95),
              backdropFilter: "blur(10px)",
              boxShadow: `0 12px 24px ${alpha(theme.palette.common.black, 0.14)}`,
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 800, lineHeight: 1.2 }}>
              {handoffFX.title}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.3 }}>
              {handoffFX.detail}
            </Typography>
          </Paper>
        </Box>
      ) : null}

      <Box
        ref={timelineRef}
        sx={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          overflowX: "hidden",
          pb: compactMode ? 1.1 : 1.6,
          overscrollBehaviorY: "contain",
        }}
      >
        <Container maxWidth={mainContainerMaxWidth} sx={{ px: { xs: 0.5, sm: compactMode ? 1.0 : 0.4 }, py: compactMode ? 1.0 : 1.35 }}>
          {messages.length <= 1 ? (
            <Paper
              variant="outlined"
              sx={{
                px: 1.2,
                py: 1.1,
                borderRadius: 2.2,
                borderColor: alpha(theme.palette.primary.main, 0.28),
                background:
                  theme.palette.mode === "light"
                    ? "linear-gradient(135deg, rgba(255,255,255,0.96), rgba(245,249,255,0.86))"
                    : "linear-gradient(135deg, rgba(34,34,34,0.96), rgba(22,28,36,0.86))",
                mb: 1.1,
              }}
            >
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.8 }}>
                <Stack direction="row" spacing={0.8} alignItems="center">
                  <BoltIcon sx={{ fontSize: 18, color: "primary.main" }} />
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Today Focus
                  </Typography>
                </Stack>
                <Button
                  size="small"
                  startIcon={<AutoStoriesIcon sx={{ fontSize: 16 }} />}
                  onClick={runStoryMode}
                  disabled={storyBusy}
                >
                  {storyBusy ? "生成中..." : "故事模式"}
                </Button>
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.55 }}>
                {contextSnapshot?.daily_brief?.summary || "正在读取你的每日简报与高价值信号..."}
              </Typography>

              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" }, gap: 0.7, mt: 0.95 }}>
                {(contextSnapshot?.daily_brief?.top_updates || []).slice(0, 3).map((item, idx) => (
                  <Paper
                    key={`${item.message_id}-${idx}`}
                    variant="outlined"
                    onClick={() => send(`请详细解释这个更新并告诉我为什么重要：${item.title}`)}
                    sx={{
                      px: 0.85,
                      py: 0.72,
                      borderRadius: 1.5,
                      borderColor: alpha(theme.palette.primary.main, 0.24),
                      bgcolor: alpha(theme.palette.primary.main, 0.06),
                      cursor: "pointer",
                      transition: "transform 160ms ease, box-shadow 200ms ease",
                      "&:hover": { transform: "translateY(-1px)", boxShadow: "0 10px 20px rgba(0,0,0,0.08)" },
                    }}
                  >
                    <Typography variant="caption" sx={{ fontWeight: 700, color: "primary.main" }}>
                      {item.source_label}
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 700, mt: 0.2, lineHeight: 1.35 }}>
                      {item.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {item.sender} 路 {item.received_at}
                    </Typography>
                  </Paper>
                ))}
              </Box>

              <Divider sx={{ my: 0.95 }} />
              <Stack direction="row" spacing={0.7} flexWrap="wrap" useFlexGap sx={{ py: 0.2 }}>
                {QUICK_PROMPTS.map((prompt) => (
                  <Chip key={prompt} size="small" variant="outlined" clickable onClick={() => send(prompt)} label={prompt} />
                ))}
              </Stack>
            </Paper>
          ) : null}

          {groupedMessages.map(({ message, isGroupStart }) => (
            <MessageRow
              key={message.id}
              message={message}
              isGroupStart={isGroupStart}
              onActionClick={onActionClick}
              onCopy={copyText}
              onCitationOpen={handleCitationOpen}
              pulse={latestSparkMessageId === message.id}
              streamBusy={isProgressPending}
            />
          ))}
        </Container>
      </Box>

      <Box
        sx={{
          flexShrink: 0,
          pt: compactMode ? 0.7 : 1.1,
          pb: compactMode ? 1.0 : 1.35,
          px: 1.1,
          borderTop: "1px solid",
          borderColor: alpha(theme.palette.divider, 0.9),
          backdropFilter: "blur(8px)",
          background:
            theme.palette.mode === "light"
              ? "linear-gradient(to top, rgba(250,249,245,1), rgba(250,249,245,0.96), rgba(250,249,245,0.56), rgba(250,249,245,0))"
              : "linear-gradient(to top, rgba(20,20,19,1), rgba(20,20,19,0.96), rgba(20,20,19,0.52), rgba(20,20,19,0))",
        }}
      >
        <Container maxWidth={mainContainerMaxWidth} sx={{ px: { xs: 0.5, sm: compactMode ? 1.0 : 0.4 } }}>
          <Paper
            variant="outlined"
            sx={{
              p: compactMode ? 0.72 : 0.9,
              borderRadius: 2.4,
              borderColor: alpha(theme.palette.divider, 0.95),
            }}
          >
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.65, px: 0.1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                观察联动
              </Typography>
              <Button
                size="small"
                variant="text"
                startIcon={<TravelExploreIcon sx={{ fontSize: 15 }} />}
                onClick={() =>
                  openDeskWithContext({
                    messageId: lastAssistantCitation?.message_id,
                    focusQuery: (input || "").trim() || lastAssistantCitation?.title || "",
                    highlightSource: lastAssistantCitation?.source_label || lastAssistantCitation?.source || "",
                    resumePrompt:
                      ((input || "").trim() && `继续围绕这个问题讨论：${input.trim()}`) ||
                      (lastAssistantCitation?.title && `继续分析这条线索：${lastAssistantCitation.title}`) ||
                      "继续从观察视图里分析我的重点信息。",
                  })
                }
              >
                在 Desk 观察
              </Button>
            </Stack>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: "none" }}
              onChange={async (event) => {
                const files = Array.from(event.target.files || []);
                if (!files.length) return;
                await appendFiles(files);
                event.target.value = "";
              }}
            />

            {pendingImages.length ? (
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(88px, 1fr))", gap: 0.7, mb: 0.8 }}>
                {pendingImages.map((img) => (
                  <Box key={img.id} sx={{ position: "relative" }}>
                    <Box
                      component="img"
                      src={img.dataUrl}
                      alt={img.name}
                      sx={{
                        width: "100%",
                        height: 88,
                        objectFit: "cover",
                        borderRadius: 1.1,
                        border: "1px solid",
                        borderColor: "divider",
                      }}
                    />
                    <IconButton
                      size="small"
                      onClick={() => setPendingImages((prev) => prev.filter((item) => item.id !== img.id))}
                      sx={{
                        position: "absolute",
                        right: 4,
                        top: 4,
                        bgcolor: alpha(theme.palette.background.paper, 0.88),
                        "&:hover": { bgcolor: alpha(theme.palette.background.paper, 1) },
                      }}
                    >
                      <CloseIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Box>
                ))}
              </Box>
            ) : null}

            <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.8 }}>
              <Tooltip title="上传图片">
                <span>
                  <IconButton
                    onClick={() => fileInputRef.current?.click()}
                    disabled={busy || pendingImages.length >= 4}
                    sx={{
                      width: 36,
                      height: 36,
                      borderRadius: 1.1,
                      border: "1px solid",
                      borderColor: "divider",
                      alignSelf: "flex-end",
                      mb: 0.2,
                    }}
                  >
                    <ImageIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <InputBase
                fullWidth
                multiline
                minRows={1}
                maxRows={8}
                placeholder="发送消息..."
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onPaste={async (event) => {
                  const items = Array.from(event.clipboardData?.items || []);
                  const imageFiles: File[] = [];
                  for (const item of items) {
                    if (item.type.startsWith("image/")) {
                      const file = item.getAsFile();
                      if (file) imageFiles.push(file);
                    }
                  }
                  if (!imageFiles.length) return;
                  event.preventDefault();
                  await appendFiles(imageFiles);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    send(input);
                  }
                }}
                sx={{
                  flex: 1,
                  px: 1,
                  py: 0.75,
                  fontSize: "1rem",
                  lineHeight: 1.6,
                  borderRadius: 1.6,
                  border: "1px solid",
                  borderColor: "divider",
                  bgcolor: "background.paper",
                  "& textarea": {
                    resize: "none",
                    p: 0,
                  },
                  "&.Mui-focused": {
                    borderColor: "primary.main",
                  },
                }}
              />
              <Button
                variant="contained"
                onClick={() => send(input)}
                disabled={busy || (!input.trim() && pendingImages.length === 0)}
                sx={{
                  minWidth: 36,
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  p: 0,
                  alignSelf: "flex-end",
                  mb: 0.2,
                  transition: "transform 180ms ease, box-shadow 200ms ease",
                  boxShadow: `0 6px 14px ${alpha(theme.palette.primary.main, 0.24)}`,
                  "&:hover": {
                    transform: "translateY(-1px) scale(1.03)",
                    boxShadow: `0 10px 20px ${alpha(theme.palette.primary.main, 0.32)}`,
                  },
                }}
              >
                <SendIcon sx={{ fontSize: 18 }} />
              </Button>
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.55, px: 0.6 }}>
              Enter 发送，Shift+Enter 换行
            </Typography>
          </Paper>
        </Container>
      </Box>

      <Dialog
        open={llmDialogOpen}
        onClose={() => setLlmDialogOpen(false)}
        fullWidth
        maxWidth="sm"
        PaperProps={{
          sx: {
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: alpha(theme.palette.background.paper, 0.98),
            backdropFilter: "blur(10px)",
          },
        }}
      >
        <Box sx={{ px: 1.2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Aelin 模型设置
            </Typography>
            <Stack direction="row" spacing={0.4}>
              <Tooltip title="刷新模型目录">
                <span>
                  <IconButton size="small" onClick={() => void handleLlmCatalogRefresh()} disabled={llmRefreshing || llmLoading}>
                    {llmRefreshing ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
              <IconButton size="small" onClick={() => setLlmDialogOpen(false)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>
        </Box>

        <Box sx={{ px: 1.2, py: 1.1 }}>
          {llmLoading ? (
            <Stack direction="row" spacing={0.8} alignItems="center" sx={{ py: 2.6 }}>
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                正在加载模型配置...
              </Typography>
            </Stack>
          ) : (
            <Stack spacing={1.1}>
              <TextField
                select
                fullWidth
                size="small"
                label="服务商"
                value={llmProviderSelectValue}
                onChange={(event) => {
                  const value = String(event.target.value || "");
                  if (value === CUSTOM_PROVIDER_OPTION) {
                    setLlmProviderSelectValue(CUSTOM_PROVIDER_OPTION);
                    setLlmProvider(normalizeProviderId(llmCustomProviderId));
                    if (!llmBaseUrl.trim()) {
                      setLlmBaseUrl("https://api.openai.com/v1");
                    }
                    return;
                  }
                  const normalized = normalizeProviderId(value) || "rule_based";
                  setLlmProviderSelectValue(normalized);
                  setLlmProvider(normalized);
                  if (normalized === "rule_based") {
                    setLlmCustomProviderId("");
                  }
                  setLlmBaseUrl(getDefaultLlmBaseUrl(normalized));
                }}
                SelectProps={{ native: true }}
              >
                <option value="rule_based">内置规则（免费）</option>
                {(llmCatalog?.providers ?? []).map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name} ({provider.id})
                  </option>
                ))}
                <option value={CUSTOM_PROVIDER_OPTION}>自定义提供商（手动填写）</option>
              </TextField>

              {llmIsCustomProvider ? (
                <TextField
                  fullWidth
                  size="small"
                  label="自定义 Provider ID"
                  value={llmCustomProviderId}
                  onChange={(event) => {
                    const value = String(event.target.value || "");
                    setLlmCustomProviderId(value);
                    setLlmProvider(normalizeProviderId(value));
                  }}
                  placeholder="例如：deepseek / groq / my-private-llm"
                />
              ) : null}

              {llmProvider !== "rule_based" ? (
                <>
                  {llmSelectedProvider?.models?.length && !llmIsCustomProvider ? (
                    <TextField
                      select
                      fullWidth
                      size="small"
                      label="模型"
                      value={llmModel}
                      onChange={(event) => setLlmModel(String(event.target.value || ""))}
                      SelectProps={{ native: true }}
                    >
                      {llmSelectedProvider.models.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name} ({model.id})
                        </option>
                      ))}
                    </TextField>
                  ) : (
                    <TextField
                      fullWidth
                      size="small"
                      label="模型"
                      value={llmModel}
                      onChange={(event) => setLlmModel(String(event.target.value || ""))}
                      placeholder="输入模型 ID"
                    />
                  )}

                  <TextField
                    fullWidth
                    size="small"
                    label="接口地址（Base URL）"
                    value={llmBaseUrl}
                    onChange={(event) => setLlmBaseUrl(String(event.target.value || ""))}
                    placeholder={llmSelectedProvider?.api || "https://api.openai.com/v1"}
                  />
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="随机度（Temperature）"
                    value={llmTemperature}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      setLlmTemperature(Number.isFinite(value) ? value : 0.2);
                    }}
                    inputProps={{ min: 0, max: 2, step: 0.1 }}
                  />
                  <TextField
                    fullWidth
                    size="small"
                    type="password"
                    label="API Key（留空则沿用已保存 Key）"
                    value={llmApiKey}
                    onChange={(event) => setLlmApiKey(String(event.target.value || ""))}
                    placeholder={llmHasApiKey ? "已保存（不显示）" : "sk-..."}
                  />
                  <Alert severity="info" sx={{ borderRadius: 1.2, py: 0.35 }}>
                    当前使用 OpenAI-Compatible 接口。请确保 Base URL 与模型 ID 对应同一服务商。
                  </Alert>
                </>
              ) : (
                <Alert severity="info" sx={{ borderRadius: 1.2, py: 0.35 }}>
                  已使用内置规则模式，可直接聊天；若需高质量模型回答，请切换到任意 API 提供商。
                </Alert>
              )}

              <Typography variant="caption" color="text.secondary">
                当前：{normalizeProviderId(llmProvider) || "rule_based"} · Key：{llmHasApiKey ? "已配置" : "未配置"}
              </Typography>
            </Stack>
          )}
        </Box>

        <Box sx={{ px: 1.2, pb: 1.1, pt: 0.2, display: "flex", gap: 0.8, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <Button size="small" variant="text" onClick={() => navigate("/settings")}>
            完整设置
          </Button>
          <Button size="small" variant="outlined" onClick={() => void handleLlmTest()} disabled={llmLoading || llmSaving || llmTesting}>
            {llmTesting ? "测试中..." : "测试连接"}
          </Button>
          <Button size="small" variant="contained" onClick={() => void handleLlmSave()} disabled={llmLoading || llmSaving}>
            {llmSaving ? "保存中..." : "保存配置"}
          </Button>
        </Box>
      </Dialog>

      <Dialog
        open={trackingDialogOpen}
        onClose={() => setTrackingDialogOpen(false)}
        fullWidth
        maxWidth="lg"
        PaperProps={{
          sx: {
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: alpha(theme.palette.background.paper, 0.98),
            backdropFilter: "blur(10px)",
          },
        }}
      >
        <Box sx={{ px: 1.2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Stack direction="row" spacing={0.8} alignItems="center">
              <TrackChangesIcon sx={{ fontSize: 18, color: "primary.main" }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                跟踪中心
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.4}>
              <Tooltip title="刷新">
                <span>
                  <IconButton
                    size="small"
                    onClick={() => {
                      void refreshTracking();
                      if (activeTrackingItem?.target_id) {
                        void refreshTrackingDetail(Number(activeTrackingItem.target_id));
                      }
                    }}
                    disabled={trackingBusy}
                  >
                    <RefreshIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <IconButton size="small" onClick={() => setTrackingDialogOpen(false)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap sx={{ mt: 0.8 }}>
            <Chip size="small" label={`目标 ${trackingItems.length}`} />
            <Chip
              size="small"
              color="success"
              label={`进行中 ${trackingItems.filter((it) => it.status === "sync_started" || it.status === "active").length}`}
            />
            <Chip
              size="small"
              color="warning"
              label={`已暂停 ${trackingItems.filter((it) => it.status === "paused").length}`}
            />
            <Chip size="small" color="error" label={`异常 ${trackingItems.filter((it) => it.status === "error" || it.status === "failed").length}`} />
            <Chip size="small" color="info" label={`未读变化 ${trackingUnreadCount}`} />
          </Stack>
        </Box>

        <Box sx={{ px: 1.2, py: 1.1, maxHeight: "76vh", overflow: "hidden", display: "flex", flexDirection: "column", gap: 0.9 }}>
          <Paper variant="outlined" sx={{ p: 0.8, borderRadius: 1.4 }}>
            <Stack spacing={0.65}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={0.65}>
                <TextField
                  size="small"
                  placeholder="筛选目标/问题"
                  value={trackingKeyword}
                  onChange={(event) => setTrackingKeyword(event.target.value)}
                  fullWidth
                />
                <TextField
                  select
                  size="small"
                  label="状态"
                  value={trackingStatusFilter}
                  onChange={(event) => setTrackingStatusFilter(String(event.target.value || "all"))}
                  sx={{ minWidth: 120 }}
                  SelectProps={{ native: true }}
                >
                  <option value="all">全部</option>
                  <option value="active">进行中</option>
                  <option value="sync_started">同步中</option>
                  <option value="paused">已暂停</option>
                  <option value="needs_config">待配置</option>
                  <option value="error">异常</option>
                  <option value="failed">失败</option>
                </TextField>
                <TextField
                  select
                  size="small"
                  label="来源"
                  value={trackingSourceFilter}
                  onChange={(event) => setTrackingSourceFilter(String(event.target.value || "all"))}
                  sx={{ minWidth: 120 }}
                  SelectProps={{ native: true }}
                >
                  <option value="all">全部</option>
                  {Object.entries(TRACKING_SOURCE_LABEL).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </TextField>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                当前匹配 {filteredTrackingItems.length} 条。选择左侧目标可查看变化流与快照。
              </Typography>
            </Stack>
          </Paper>

          {trackingBusy ? (
            <Stack direction="row" spacing={0.8} alignItems="center" sx={{ py: 2.6 }}>
              <CircularProgress size={18} />
              <Typography variant="body2" color="text.secondary">
                正在加载跟踪列表...
              </Typography>
            </Stack>
          ) : trackingError ? (
            <Paper variant="outlined" sx={{ p: 1, borderRadius: 1.4 }}>
              <Typography variant="body2" color="error.main">
                {trackingError}
              </Typography>
              <Button size="small" sx={{ mt: 0.6 }} onClick={() => void refreshTracking()}>
                重试
              </Button>
            </Paper>
          ) : filteredTrackingItems.length ? (
            <Box
              sx={{
                flex: 1,
                minHeight: 0,
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "minmax(260px,0.95fr) minmax(340px,1.25fr)" },
                gap: 0.9,
              }}
            >
              <Stack spacing={0.75} sx={{ minHeight: 0, overflowY: "auto", pr: { md: 0.25 } }}>
                {filteredTrackingItems.map((item) => {
                  const status = formatTrackingStatus(item.status);
                  const sourceLabel = TRACKING_SOURCE_LABEL[item.source] || item.source || "未知";
                  const itemTargetId = Number(item.target_id || 0);
                  const selected = itemTargetId > 0 && itemTargetId === trackingActiveTargetId;
                  const unread = Math.max(0, Number(item.unread_changes || 0));
                  const statusTs = item.status_updated_at || item.updated_at;
                  const nextProbe = item.next_run_at || "";
                  return (
                    <Paper
                      key={`tracking-item-${item.target_id || item.target}-${item.source}`}
                      variant="outlined"
                      onClick={() => {
                        if (itemTargetId > 0) {
                          setTrackingActiveTargetId(itemTargetId);
                          void refreshTrackingDetail(itemTargetId);
                        }
                      }}
                      sx={{
                        p: 0.85,
                        borderRadius: 1.5,
                        borderColor: selected ? alpha(theme.palette.primary.main, 0.52) : alpha(theme.palette.divider, 0.85),
                        boxShadow: selected ? `0 0 0 1px ${alpha(theme.palette.primary.main, 0.14)}` : "none",
                        cursor: itemTargetId > 0 ? "pointer" : "default",
                      }}
                    >
                      <Stack spacing={0.45}>
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={0.8}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.35 }}>
                              {item.target}
                            </Typography>
                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.45 }}>
                              <Chip size="small" label={sourceLabel} variant="outlined" />
                              <Chip size="small" label={status.label} color={status.color} />
                              {item.track_type ? <Chip size="small" variant="outlined" label={item.track_type === "url" ? "URL" : "词条"} /> : null}
                              {unread > 0 ? <Chip size="small" color="info" label={`未读 ${unread}`} /> : null}
                            </Stack>
                          </Box>
                        </Stack>
                        {item.query ? (
                          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>
                            触发问题：{item.query}
                          </Typography>
                        ) : null}
                        <Typography variant="caption" color="text.secondary">
                          最近更新：{formatIsoTime(statusTs)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          下次执行：{nextProbe ? formatIsoTime(nextProbe) : "待调度"}
                        </Typography>
                      </Stack>
                    </Paper>
                  );
                })}
              </Stack>

              <Paper
                variant="outlined"
                sx={{
                  p: 0.95,
                  borderRadius: 1.5,
                  minHeight: 0,
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                }}
              >
                {activeTrackingItem ? (
                  (() => {
                    const targetId = Number(activeTrackingItem.target_id || 0);
                    const sourceLabel = TRACKING_SOURCE_LABEL[activeTrackingItem.source] || activeTrackingItem.source || "未知";
                    const status = formatTrackingStatus(activeTrackingItem.status || "active");
                    const statusValue = String(activeTrackingItem.status || "").toLowerCase();
                    const mutationBusy = trackingMutationBusy === targetId;
                    const mutedUntil = String(activeTrackingItem.mute_until || "").trim();
                    const muted = !!mutedUntil && Date.parse(mutedUntil) > Date.now();
                    return (
                      <>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={0.7} justifyContent="space-between" alignItems={{ xs: "flex-start", sm: "center" }}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 800, lineHeight: 1.25 }}>
                              {activeTrackingItem.target}
                            </Typography>
                            <Stack direction="row" spacing={0.55} flexWrap="wrap" useFlexGap sx={{ mt: 0.45 }}>
                              <Chip size="small" variant="outlined" label={sourceLabel} />
                              <Chip size="small" color={status.color} label={status.label} />
                              <Chip size="small" variant="outlined" label={`${Math.max(30, Number(activeTrackingItem.interval_seconds || 120))}s`} />
                              {Math.max(0, Number(activeTrackingItem.error_count || 0)) > 0 ? (
                                <Chip size="small" color="error" label={`错误 ${Math.max(0, Number(activeTrackingItem.error_count || 0))}`} />
                              ) : null}
                            </Stack>
                          </Box>
                          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={!targetId || mutationBusy}
                              onClick={() =>
                                void patchTrackingTarget(
                                  targetId,
                                  { status: statusValue === "active" || statusValue === "sync_started" ? "paused" : "active" },
                                  statusValue === "active" || statusValue === "sync_started" ? "已暂停该追踪" : "已恢复该追踪"
                                )
                              }
                            >
                              {mutationBusy ? "处理中..." : statusValue === "active" || statusValue === "sync_started" ? "暂停" : "恢复"}
                            </Button>
                            <Button size="small" variant="outlined" disabled={!targetId || mutationBusy} onClick={() => void runTrackingTargetNow(targetId)}>
                              立即执行
                            </Button>
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={!targetId || mutationBusy}
                              onClick={() =>
                                void patchTrackingTarget(
                                  targetId,
                                  { mute_until: muted ? null : new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString() },
                                  muted ? "已取消静音" : "已静音 24 小时"
                                )
                              }
                            >
                              {muted ? "取消静音" : "静音24h"}
                            </Button>
                          </Stack>
                        </Stack>

                        <Stack direction="row" spacing={1.2} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          <Typography variant="caption" color="text.secondary">
                            工作区：{activeTrackingItem.workspace || workspaceScope}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            下次执行：{activeTrackingItem.next_run_at ? formatIsoTime(activeTrackingItem.next_run_at) : "待调度"}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            最近执行：{activeTrackingItem.last_run_at ? formatIsoTime(activeTrackingItem.last_run_at) : "暂无"}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            静音至：{mutedUntil ? formatIsoTime(mutedUntil) : "未静音"}
                          </Typography>
                        </Stack>

                        <Divider sx={{ my: 0.9 }} />

                        <Stack spacing={0.65} sx={{ mb: 0.8 }}>
                          <Stack direction={{ xs: "column", sm: "row" }} spacing={0.65}>
                            <TextField
                              select
                              size="small"
                              label="级别"
                              value={trackingChangeSeverityFilter}
                              onChange={(event) => setTrackingChangeSeverityFilter(String(event.target.value || "all"))}
                              sx={{ minWidth: 120 }}
                              SelectProps={{ native: true }}
                            >
                              <option value="all">全部级别</option>
                              <option value="low">低</option>
                              <option value="medium">中</option>
                              <option value="high">高</option>
                              <option value="critical">严重</option>
                            </TextField>
                            <TextField
                              select
                              size="small"
                              label="类型"
                              value={trackingChangeTypeFilter}
                              onChange={(event) => setTrackingChangeTypeFilter(String(event.target.value || "all"))}
                              sx={{ minWidth: 132 }}
                              SelectProps={{ native: true }}
                            >
                              <option value="all">全部类型</option>
                              {Object.entries(TRACKING_CHANGE_TYPE_LABEL).map(([key, label]) => (
                                <option key={key} value={key}>
                                  {label}
                                </option>
                              ))}
                            </TextField>
                            <TextField
                              select
                              size="small"
                              label="已读"
                              value={trackingAckFilter}
                              onChange={(event) => setTrackingAckFilter(String(event.target.value || "unacked") as TrackingAckFilter)}
                              sx={{ minWidth: 120 }}
                              SelectProps={{ native: true }}
                            >
                              <option value="unacked">仅未读</option>
                              <option value="all">全部</option>
                              <option value="acked">仅已读</option>
                            </TextField>
                          </Stack>
                        </Stack>

                        {trackingDetailBusy ? (
                          <Stack direction="row" spacing={0.8} alignItems="center" sx={{ py: 1.8 }}>
                            <CircularProgress size={16} />
                            <Typography variant="body2" color="text.secondary">
                              正在加载追踪详情...
                            </Typography>
                          </Stack>
                        ) : trackingDetailError ? (
                          <Paper variant="outlined" sx={{ p: 0.9, borderRadius: 1.25 }}>
                            <Typography variant="body2" color="error.main">
                              {trackingDetailError}
                            </Typography>
                            <Button size="small" sx={{ mt: 0.5 }} onClick={() => void refreshTrackingDetail(targetId)}>
                              重试
                            </Button>
                          </Paper>
                        ) : (
                          <Stack spacing={0.75} sx={{ minHeight: 0, overflowY: "auto", pr: { md: 0.25 } }}>
                            <Paper variant="outlined" sx={{ p: 0.75, borderRadius: 1.3 }}>
                              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                                变化流（{trackingChanges.length}）
                              </Typography>
                              {trackingChanges.length ? (
                                <Stack spacing={0.6} sx={{ mt: 0.55 }}>
                                  {trackingChanges.slice(0, 16).map((change) => {
                                    const severityMeta = TRACKING_SEVERITY_META[change.severity] || {
                                      label: change.severity || "未知",
                                      color: "default" as const,
                                    };
                                    const changeLabel = TRACKING_CHANGE_TYPE_LABEL[change.change_type] || change.change_type || "变化";
                                    const summary = String(change.summary || "").trim() || String(change.title || "").trim();
                                    return (
                                      <Paper key={`tracking-change-${change.id}`} variant="outlined" sx={{ p: 0.65, borderRadius: 1.2 }}>
                                        <Stack spacing={0.45}>
                                          <Stack direction="row" alignItems="center" spacing={0.45} flexWrap="wrap" useFlexGap>
                                            <Chip size="small" label={changeLabel} variant="outlined" />
                                            <Chip size="small" color={severityMeta.color} label={severityMeta.label} />
                                            <Typography variant="caption" color="text.secondary">
                                              {formatIsoTime(change.created_at)}
                                            </Typography>
                                          </Stack>
                                          <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.35 }}>
                                            {change.title || changeLabel}
                                          </Typography>
                                          {summary ? (
                                            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                                              {summary}
                                            </Typography>
                                          ) : null}
                                          {!change.acked ? (
                                            <Stack direction="row" justifyContent="flex-end">
                                              <Button
                                                size="small"
                                                variant="text"
                                                disabled={trackingAckBusy === change.id}
                                                onClick={() => void ackTrackingChange(change.id)}
                                              >
                                                {trackingAckBusy === change.id ? "处理中..." : "标记已读"}
                                              </Button>
                                            </Stack>
                                          ) : null}
                                        </Stack>
                                      </Paper>
                                    );
                                  })}
                                </Stack>
                              ) : (
                                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.6, display: "block" }}>
                                  {trackingSnapshots.length === 0
                                    ? "已执行但暂未命中数据源（source_no_result），可稍后重试或更换追踪关键词。"
                                    : "暂无变化记录。"}
                                </Typography>
                              )}
                            </Paper>

                            <Paper variant="outlined" sx={{ p: 0.75, borderRadius: 1.3 }}>
                              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                                最近快照（{trackingSnapshots.length}）
                              </Typography>
                              {trackingSnapshots.length ? (
                                <Stack spacing={0.6} sx={{ mt: 0.55 }}>
                                  {trackingSnapshots.slice(0, 10).map((snapshot) => {
                                    const payloadText = JSON.stringify(snapshot.normalized_payload_json || {});
                                    return (
                                      <Paper key={`tracking-snapshot-${snapshot.id}`} variant="outlined" sx={{ p: 0.6, borderRadius: 1.15 }}>
                                        <Stack spacing={0.35}>
                                          <Stack direction="row" spacing={0.45} alignItems="center" flexWrap="wrap" useFlexGap>
                                            <Chip size="small" variant="outlined" label={`v${snapshot.version_no}`} />
                                            <Chip
                                              size="small"
                                              color={snapshot.fetch_status === "ok" ? "success" : snapshot.fetch_status === "failed" ? "error" : "warning"}
                                              label={snapshot.fetch_status || "ok"}
                                            />
                                            <Typography variant="caption" color="text.secondary">
                                              {formatIsoTime(snapshot.fetched_at)}
                                            </Typography>
                                          </Stack>
                                          {snapshot.fetch_error ? (
                                            <Typography variant="caption" color="error.main" sx={{ lineHeight: 1.4 }}>
                                              {snapshot.fetch_error}
                                            </Typography>
                                          ) : null}
                                          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.35 }}>
                                            {payloadText.length > 180 ? `${payloadText.slice(0, 180)}...` : payloadText}
                                          </Typography>
                                        </Stack>
                                      </Paper>
                                    );
                                  })}
                                </Stack>
                              ) : (
                                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.6, display: "block" }}>
                                  暂无快照记录（已执行但本轮未命中可用结果）。
                                </Typography>
                              )}
                            </Paper>
                            <Paper variant="outlined" sx={{ p: 0.75, borderRadius: 1.3 }}>
                              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                                文件记忆命中（{trackingFileMemory.length}）
                              </Typography>
                              {trackingFileMemory.length ? (
                                <Stack spacing={0.55} sx={{ mt: 0.55 }}>
                                  {trackingFileMemory.slice(0, 10).map((item, idx) => (
                                    <Paper key={`tracking-file-memory-${item.canonical_id || item.path || idx}`} variant="outlined" sx={{ p: 0.55, borderRadius: 1.1 }}>
                                      <Stack spacing={0.35}>
                                        <Stack direction="row" spacing={0.45} alignItems="center" flexWrap="wrap" useFlexGap>
                                          <Chip size="small" variant="outlined" label={item.kind || "memory"} />
                                          {item.source ? <Chip size="small" variant="outlined" label={item.source} /> : null}
                                          <Typography variant="caption" color="text.secondary">
                                            score {Number(item.score || 0).toFixed(2)}
                                          </Typography>
                                        </Stack>
                                        <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.35 }}>
                                          {item.title || item.target || "memory item"}
                                        </Typography>
                                        {item.preview ? (
                                          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                                            {item.preview}
                                          </Typography>
                                        ) : null}
                                        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={0.6}>
                                          <Typography
                                            variant="caption"
                                            color="text.secondary"
                                            sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
                                          >
                                            {item.path}
                                          </Typography>
                                          <Button size="small" variant="text" onClick={() => void copyText(item.path)}>
                                            复制路径
                                          </Button>
                                        </Stack>
                                      </Stack>
                                    </Paper>
                                  ))}
                                </Stack>
                              ) : (
                                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.6, display: "block" }}>
                                  当前未命中文件化追踪记忆，可在抓取后再查看。
                                </Typography>
                              )}
                            </Paper>
                          </Stack>
                        )}
                      </>
                    );
                  })()
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    请选择一个追踪目标查看详情。
                  </Typography>
                )}
              </Paper>
            </Box>
          ) : (
            <Paper variant="outlined" sx={{ p: 1.1, borderRadius: 1.4 }}>
              <Typography variant="body2" color="text.secondary">
                {trackingItems.length ? "当前筛选条件下没有匹配项，请调整筛选。" : "暂无跟踪项。你在对话里同意“开启跟踪”后，这里会自动出现。"}
              </Typography>
            </Paper>
          )}
        </Box>
      </Dialog>

      <Dialog
        open={deviceDialogOpen}
        onClose={() => setDeviceDialogOpen(false)}
        fullWidth
        maxWidth="md"
        PaperProps={{
          sx: {
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: alpha(theme.palette.background.paper, 0.98),
            backdropFilter: "blur(10px)",
          },
        }}
      >
        <Box sx={{ px: 1.2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Stack direction="row" spacing={0.7} alignItems="center">
              <ComputerIcon sx={{ fontSize: 18, color: "primary.main" }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                设备中心
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.4}>
              <Tooltip title="刷新进程">
                <span>
                  <IconButton size="small" onClick={() => void refreshDeviceProcesses()} disabled={deviceBusy}>
                    <RefreshIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <IconButton size="small" onClick={() => setDeviceDialogOpen(false)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>
        </Box>

        <Box sx={{ px: 1.2, py: 1.05, maxHeight: "72vh", overflowY: "auto" }}>
          <Typography variant="caption" color="text.secondary">
            模式控制会尽力应用到系统；如果权限或设备不支持，会给出明确提示。          </Typography>

          {deviceCapabilities ? (
            <Paper variant="outlined" sx={{ mt: 0.8, p: 0.85, borderRadius: 1.4 }}>
              <Stack spacing={0.45}>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                  平台能力
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  平台：{deviceCapabilities.platform}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                  {Object.entries(deviceCapabilities.capabilities || {})
                    .map(([k, v]) => `${k}:${v ? "✅" : "❌"}`)
                    .join(" · ")}
                </Typography>
                {(deviceCapabilities.notes || []).length ? (
                  <Alert severity="info" sx={{ borderRadius: 1.1 }}>
                    {(deviceCapabilities.notes || []).slice(0, 2).join("；")}
                  </Alert>
                ) : null}
              </Stack>
            </Paper>
          ) : null}

          <Stack direction={{ xs: "column", md: "row" }} spacing={0.8} sx={{ mt: 0.8 }}>
            {(Object.keys(DEVICE_MODE_META) as DeviceMode[]).map((mode) => {
              const meta = DEVICE_MODE_META[mode];
              const active = (deviceModeState?.mode || "normal") === mode;
              return (
                <Paper
                  key={mode}
                  variant="outlined"
                  sx={{
                    flex: 1,
                    p: 0.8,
                    borderRadius: 1.45,
                    borderColor: active ? alpha(theme.palette.primary.main, 0.55) : alpha(theme.palette.divider, 0.9),
                    bgcolor: active ? alpha(theme.palette.primary.main, 0.08) : alpha(theme.palette.background.default, 0.45),
                  }}
                >
                  <Stack spacing={0.45}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {meta.label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                      {meta.detail}
                    </Typography>
                    <Button
                      size="small"
                      variant={active ? "contained" : "outlined"}
                      startIcon={<PowerSettingsNewIcon sx={{ fontSize: 14 }} />}
                      disabled={deviceModeApplying !== null}
                      onClick={() => void applyDeviceModeAction(mode)}
                    >
                      {deviceModeApplying === mode ? "应用中..." : active ? "已启用" : "启用"}
                    </Button>
                  </Stack>
                </Paper>
              );
            })}
          </Stack>

          <Paper variant="outlined" sx={{ mt: 0.9, p: 0.9, borderRadius: 1.45 }}>
            <Stack spacing={0.5}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                当前设备模式
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                {deviceModeState?.summary || "尚未读取模式状态"}
              </Typography>
              {(deviceModeState?.steps || []).length ? (
                <Stack spacing={0.35}>
                  {(deviceModeState?.steps || []).slice(0, 4).map((step, idx) => (
                    <Typography key={`mode-step-${idx}`} variant="caption" color="text.secondary">
                      - {step}
                    </Typography>
                  ))}
                </Stack>
              ) : null}
              {(deviceModeState?.warnings || []).length ? (
                <Alert severity="warning" sx={{ borderRadius: 1.2 }}>
                  {(deviceModeState?.warnings || []).slice(0, 2).join("；")}
                </Alert>
              ) : null}
            </Stack>
          </Paper>

          <Stack direction="row" spacing={0.7} alignItems="center" sx={{ mt: 1 }}>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <Select
                value={deviceSortBy}
                onChange={(event) => setDeviceSortBy(String(event.target.value || "cpu") as DeviceSortBy)}
              >
                <MenuItem value="cpu">按 CPU 排序</MenuItem>
                <MenuItem value="memory">按内存排序</MenuItem>
              </Select>
            </FormControl>
            <Button
              size="small"
              variant="outlined"
              startIcon={<SpeedIcon sx={{ fontSize: 14 }} />}
              onClick={() => void runDeviceOptimize()}
              disabled={deviceOptimizeBusy}
            >
              {deviceOptimizeBusy ? "优化中..." : "一键降载"}
            </Button>
            <Typography variant="caption" color="text.secondary">
              异常分越高越需要处理            </Typography>
          </Stack>

          {deviceOptimizeResult ? (
            <Paper variant="outlined" sx={{ mt: 0.85, p: 0.75, borderRadius: 1.35 }}>
              <Typography variant="caption" color="text.secondary">
                最近优化：{deviceOptimizeResult.optimized_count} 个进程              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                {(deviceOptimizeResult.steps || []).slice(0, 2).join("；")}
              </Typography>
            </Paper>
          ) : null}

          <Stack spacing={0.7} sx={{ mt: 0.9 }}>
            {deviceBusy ? (
              <>
                <Skeleton variant="rounded" height={72} />
                <Skeleton variant="rounded" height={72} />
                <Skeleton variant="rounded" height={72} />
              </>
            ) : deviceProcesses.length ? (
              deviceProcesses.slice(0, 18).map((proc) => {
                const isAnomaly = proc.anomaly_score >= 1.6;
                return (
                  <Paper
                    key={`proc-${proc.pid}`}
                    variant="outlined"
                    sx={{
                      p: 0.82,
                      borderRadius: 1.4,
                      borderColor: isAnomaly ? alpha(theme.palette.warning.main, 0.52) : alpha(theme.palette.divider, 0.88),
                      bgcolor: isAnomaly ? alpha(theme.palette.warning.main, 0.07) : alpha(theme.palette.background.default, 0.5),
                    }}
                  >
                    <Stack spacing={0.5}>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={0.8}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.35 }}>
                            {proc.name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            PID {proc.pid} 路 {proc.username || "unknown"} 路 {proc.status || "running"}
                          </Typography>
                        </Box>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          <Chip
                            size="small"
                            icon={<SpeedIcon sx={{ fontSize: 12 }} />}
                            color={proc.cpu_percent >= 60 ? "warning" : "default"}
                            label={`${proc.cpu_percent.toFixed(1)}% CPU`}
                          />
                          <Chip
                            size="small"
                            icon={<MemoryIcon sx={{ fontSize: 12 }} />}
                            color={proc.memory_mb >= 800 ? "warning" : "default"}
                            label={`${proc.memory_mb.toFixed(0)}MB`}
                          />
                          <Chip size="small" variant="outlined" label={`异常分 ${proc.anomaly_score.toFixed(1)}`} />
                        </Stack>
                      </Stack>
                      {proc.anomaly_reasons.length ? (
                        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                          {proc.anomaly_reasons.join("；")}
                        </Typography>
                      ) : null}
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={deviceActionBusyPid === proc.pid}
                          onClick={() => void handleDeviceProcessAction(proc.pid, "set_low_priority")}
                        >
                          降优先级
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={deviceActionBusyPid === proc.pid}
                          onClick={() => void handleDeviceProcessAction(proc.pid, "set_high_priority")}
                        >
                          提升优先级
                        </Button>
                        {proc.safe_to_terminate ? (
                          <Button
                            size="small"
                            color="error"
                            variant="outlined"
                            disabled={deviceActionBusyPid === proc.pid}
                            onClick={() => void handleDeviceProcessAction(proc.pid, "terminate")}
                          >
                            结束进程
                          </Button>
                        ) : null}
                      </Stack>
                    </Stack>
                  </Paper>
                );
              })
            ) : (
              <Paper variant="outlined" sx={{ p: 1.05, borderRadius: 1.4 }}>
                <Typography variant="body2" color="text.secondary">
                  当前未读取到进程数据。可能是系统权限限制或运行环境不支持。
                </Typography>
              </Paper>
            )}
          </Stack>
        </Box>
      </Dialog>

      <Dialog
        open={memoryDialogOpen}
        onClose={() => setMemoryDialogOpen(false)}
        fullWidth
        maxWidth="md"
        PaperProps={{
          sx: {
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: alpha(theme.palette.background.paper, 0.98),
            backdropFilter: "blur(10px)",
          },
        }}
      >
        <Box sx={{ px: 1.2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Stack direction="row" spacing={0.7} alignItems="center">
              <LayersIcon sx={{ fontSize: 18, color: "primary.main" }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                分层记忆视图
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => setMemoryDialogOpen(false)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
          <Tabs
            value={memoryLayerTab}
            onChange={(_event, value) => setMemoryLayerTab(value)}
            variant="fullWidth"
            sx={{ mt: 0.8, minHeight: 34, "& .MuiTab-root": { minHeight: 34, fontSize: "0.82rem", fontWeight: 700 } }}
          >
            <Tab icon={<FactCheckIcon sx={{ fontSize: 15 }} />} iconPosition="start" label={`事实层 ${memoryLayers.facts.length}`} value="facts" />
            <Tab icon={<TuneIcon sx={{ fontSize: 15 }} />} iconPosition="start" label={`偏好层 ${memoryLayers.preferences.length}`} value="preferences" />
            <Tab icon={<PendingActionsIcon sx={{ fontSize: 15 }} />} iconPosition="start" label={`进行中 ${memoryLayers.in_progress.length}`} value="in_progress" />
          </Tabs>
        </Box>

        <Box sx={{ px: 1.2, py: 1.1, maxHeight: "68vh", overflowY: "auto" }}>
          <Typography variant="caption" color="text.secondary">
            生成时间：{formatIsoTime(memoryLayers.generated_at)}
          </Typography>
          <Stack spacing={0.8} sx={{ mt: 0.8 }}>
            {memoryLayerItems.length ? (
              memoryLayerItems.map((item) => (
                <Paper key={item.id} variant="outlined" sx={{ p: 0.85, borderRadius: 1.4 }}>
                  <Stack spacing={0.45}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={0.8}>
                      <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.35 }}>
                        {item.title}
                      </Typography>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${Math.round((item.confidence || 0) * 100)}%`}
                        sx={{ "& .MuiChip-label": { px: 0.7, fontSize: "0.68rem", fontWeight: 700 } }}
                      />
                    </Stack>
                    {item.detail ? (
                      <Box
                        sx={{
                          "& p": { m: 0, mb: 0.5, lineHeight: 1.55, fontSize: "0.82rem" },
                          "& p:last-of-type": { mb: 0 },
                          "& a": { color: "primary.main", textDecoration: "underline" },
                          "& ul, & ol": { mt: 0.25, mb: 0.5, pl: 2.2 },
                        }}
                      >
                        <ReactMarkdown>{item.detail}</ReactMarkdown>
                      </Box>
                    ) : null}
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={item.source || item.layer} />
                      <Chip size="small" variant="outlined" label={formatIsoTime(item.updated_at)} />
                    </Stack>
                  </Stack>
                </Paper>
              ))
            ) : (
              <Paper variant="outlined" sx={{ p: 1.1, borderRadius: 1.4 }}>
                <Typography variant="body2" color="text.secondary">
                  当前层暂无可展示记忆。
                </Typography>
              </Paper>
            )}
          </Stack>
        </Box>
      </Dialog>

      <Dialog
        open={notificationDialogOpen}
        onClose={() => setNotificationDialogOpen(false)}
        fullWidth
        maxWidth="sm"
        PaperProps={{
          sx: {
            borderRadius: 2,
            overflow: "hidden",
            bgcolor: alpha(theme.palette.background.paper, 0.98),
            backdropFilter: "blur(10px)",
          },
        }}
      >
        <Box sx={{ px: 1.2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Stack direction="row" spacing={0.7} alignItems="center">
              <NotificationsNoneIcon sx={{ fontSize: 18, color: "primary.main" }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
                通知中心
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.4}>
              <Tooltip title="刷新">
                <span>
                  <IconButton size="small" onClick={() => void refreshNotifications()} disabled={notificationBusy}>
                    <RefreshIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <IconButton size="small" onClick={() => setNotificationDialogOpen(false)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>
        </Box>

        <Box sx={{ px: 1.2, py: 1.1, maxHeight: "68vh", overflowY: "auto" }}>
          {notificationBusy ? (
            <Stack spacing={0.7}>
              <Skeleton variant="rounded" height={64} />
              <Skeleton variant="rounded" height={64} />
              <Skeleton variant="rounded" height={64} />
            </Stack>
          ) : allNotifications.length ? (
            <Stack spacing={0.72}>
              {allNotifications.map((item) => (
                <Paper key={item.id} variant="outlined" sx={{ p: 0.85, borderRadius: 1.4 }}>
                  <Stack spacing={0.45}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={0.7}>
                      <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.35 }}>
                        {item.title}
                      </Typography>
                      <Chip
                        size="small"
                        color={
                          item.level === "warning"
                            ? "warning"
                            : item.level === "success"
                              ? "success"
                              : item.level === "error"
                                ? "error"
                                : "info"
                        }
                        label={item.level || "info"}
                        sx={{ "& .MuiChip-label": { px: 0.72, fontSize: "0.68rem", fontWeight: 700 } }}
                      />
                    </Stack>
                    {item.detail ? (
                      <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.5 }}>
                        {item.detail}
                      </Typography>
                    ) : null}
                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={0.7}>
                      <Typography variant="caption" color="text.secondary">
                        {item.source || "system"} 路 {formatIsoTime(item.ts)}
                      </Typography>
                      {item.action_kind ? (
                        <Button size="small" variant="outlined" onClick={() => handleNotificationAction(item)}>
                          查看
                        </Button>
                      ) : null}
                    </Stack>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          ) : (
            <Paper variant="outlined" sx={{ p: 1.1, borderRadius: 1.4 }}>
              <Typography variant="body2" color="text.secondary">
                暂无通知。新的简报、待办和跟踪进展会显示在这里。
              </Typography>
            </Paper>
          )}
        </Box>
      </Dialog>

      <Drawer
        anchor="right"
        open={deskOpen}
        onClose={() => setDeskOpen(false)}
        PaperProps={{
          sx: {
            width: { xs: "100%", sm: compactFramed ? "min(100vw, 430px)" : "min(100vw, 1320px)" },
            maxWidth: "100vw",
            borderLeft: "1px solid",
            borderColor: "divider",
            bgcolor: theme.palette.background.default,
          },
        }}
      >
        <Box sx={{ height: "100dvh", overflow: "auto" }}>
          <Dashboard key={`embedded-desk-${deskPanelKey}`} embedded onRequestClose={() => setDeskOpen(false)} />
        </Box>
      </Drawer>

      {trackingSheet ? (
        <Paper
          variant="outlined"
          sx={{
            position: "fixed",
            left: "50%",
            transform: "translateX(-50%)",
            bottom: 112,
            zIndex: 1300,
            width: "min(760px, calc(100vw - 24px))",
            px: 1.1,
            py: 0.95,
            borderRadius: 2,
            borderColor: alpha(theme.palette.primary.main, 0.4),
            bgcolor: alpha(theme.palette.background.paper, 0.96),
            backdropFilter: "blur(10px)",
            boxShadow: "0 16px 32px rgba(0,0,0,0.16)",
            "@keyframes sheetIn": {
              from: { opacity: 0, transform: "translateX(-50%) translateY(8px)" },
              to: { opacity: 1, transform: "translateX(-50%) translateY(0)" },
            },
            animation: "sheetIn 180ms ease",
          }}
        >
          <Stack direction={{ xs: "column", sm: "row" }} spacing={0.9} alignItems={{ xs: "flex-start", sm: "center" }} justifyContent="space-between">
            <Stack direction="row" spacing={0.7} alignItems="center">
              <TrackChangesIcon sx={{ fontSize: 17, color: "primary.main" }} />
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {trackingSheet.action.title || "是否开启持续跟踪？"}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap>
              <Button size="small" variant="contained" onClick={() => void handleTrackingChoice("track")}>
                跟踪 7 天
              </Button>
              <Button size="small" variant="outlined" onClick={() => void handleTrackingChoice("once")}>
                仅这次
              </Button>
              <Button size="small" color="inherit" onClick={() => void handleTrackingChoice("dismiss")}>
                不再提示
              </Button>
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <Drawer
        anchor="right"
        open={citationPreview.open}
        onClose={() => setCitationPreview((prev) => ({ ...prev, open: false }))}
        PaperProps={{
          sx: {
            width: {
              xs: "100vw",
              sm: "min(100vw, 92vw)",
              md: "min(100vw, 88vw)",
              lg: "min(100vw, 1240px)",
            },
            maxWidth: "100vw",
            p: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          },
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ px: 1.1, py: 0.9, borderBottom: "1px solid", borderColor: "divider", gap: 0.8 }}
        >
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 800, lineHeight: 1.2 }}>
              网页预览
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {citationPreview.citation?.title || citationPreview.url || "来源链接"}
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.4} sx={{ flexShrink: 0 }}>
            {citationPreview.url ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  window.open(citationPreview.url, "_blank", "noopener,noreferrer");
                }}
              >
                外部打开
              </Button>
            ) : null}
            <IconButton size="small" onClick={() => setCitationPreview((prev) => ({ ...prev, open: false }))}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
        <Box sx={{ p: 1.05, flex: 1, minHeight: 0 }}>
          {citationPreview.loading ? (
            <Stack spacing={0.9}>
              <Skeleton variant="rounded" height={24} />
              <Skeleton variant="rounded" height={24} />
              <Skeleton variant="rounded" height={420} />
            </Stack>
          ) : citationPreview.error ? (
            <Alert severity="warning" sx={{ borderRadius: 1.2 }}>
              {citationPreview.error}
            </Alert>
          ) : citationPreview.url ? (
            <Box
              component="iframe"
              src={citationPreview.url}
              title={citationPreview.citation?.title || "citation-preview"}
              sx={{
                width: "100%",
                height: "100%",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1.1,
                bgcolor: "background.paper",
              }}
            />
          ) : (
            <Alert severity="info" sx={{ borderRadius: 1.2 }}>
              未解析到可预览网页，请在证据详情中查看原文。
            </Alert>
          )}
        </Box>
      </Drawer>

      <Drawer
        anchor="right"
        open={citationDrawer.open}
        onClose={() => setCitationDrawer((prev) => ({ ...prev, open: false }))}
        PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 1.2 } }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.9 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
            证据详情
          </Typography>
          <IconButton size="small" onClick={() => setCitationDrawer((prev) => ({ ...prev, open: false }))}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
        {citationDrawer.citation ? (
          <Paper variant="outlined" sx={{ p: 0.9, borderRadius: 1.4, mb: 0.95 }}>
            <Typography variant="caption" color="text.secondary">
              {citationDrawer.citation.source_label} 路 {citationDrawer.citation.sender} 路 {citationDrawer.citation.received_at}
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.35, fontWeight: 700, lineHeight: 1.4 }}>
              {citationDrawer.citation.title}
            </Typography>
          </Paper>
        ) : null}
        {citationDrawer.loading ? (
          <Stack direction="row" spacing={0.7} alignItems="center" sx={{ py: 1 }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              正在加载原文...
            </Typography>
          </Stack>
        ) : citationDrawer.error ? (
          <Typography variant="body2" color="error.main">
            {citationDrawer.error}
          </Typography>
        ) : (
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.62 }}>
            {citationDrawer.detail?.body || "暂无正文内容。"}
          </Typography>
        )}
        <Divider sx={{ my: 1 }} />
        <Stack direction="row" spacing={0.7}>
          <Button
            size="small"
            variant="contained"
            onClick={() => {
              if (!citationDrawer.citation) return;
              void handleCitationOpen(citationDrawer.citation);
            }}
          >
            打开网页
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => {
              const citation = citationDrawer.citation;
              if (!citation?.message_id) return;
              openDeskWithContext({
                messageId: citation.message_id,
                highlightSource: citation.source_label || citation.source,
                resumePrompt: `继续分析这条证据并给我后续建议：${citation.title}`,
              });
              setCitationDrawer((prev) => ({ ...prev, open: false }));
            }}
          >
            在 Desk 查看
          </Button>
          <Button
            size="small"
            variant="text"
            onClick={() => {
              const text = citationDrawer.detail?.body || citationDrawer.citation?.title || "";
              void copyText(text);
            }}
          >
            复制内容
          </Button>
        </Stack>
      </Drawer>
      {ConfirmDialog}
    </Box>
  );
}







