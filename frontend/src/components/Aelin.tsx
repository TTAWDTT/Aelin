import React from "react";
import { motion } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Drawer from "@mui/material/Drawer";
import { alpha, useTheme } from "@mui/material/styles";
import {
  AelinAction,
  AelinCitation,
  AelinContextResponse,
  AelinMemoryLayerItem,
  AelinNotificationItem,
  AelinImageInput,
  AelinToolStep,
  MessageDetail,
  aelinChat,
  aelinChatStream,
  aelinConfirmTrack,
  getAelinNotifications,
  getAelinProactivePoll,
  getAelinContext,
  getMessage,
} from "../api";
import { useConfirmDialog } from "../hooks/useConfirmDialog";
import { useToast } from "../contexts/ToastContext";
import { isNativeMobileShell } from "../mobile/runtime";
import Dashboard from "./Dashboard";
import {
  AELIN_CHAT_STORAGE_KEY,
  AELIN_LAST_DESK_BRIDGE_KEY,
  AELIN_LAST_SESSION_KEY,
  AELIN_LOGO_SRC,
  AELIN_SESSIONS_STORAGE_KEY,
  CUSTOM_PROVIDER_OPTION,
  DEVICE_MODE_META,
  MAX_PERSISTED_SESSIONS,
  PROACTIVE_POLL_MS,
} from "./aelin/constants";
import {
  extractFirstUrl,
  nextMessageId,
  normalizeExpressionId,
  normalizeProviderId,
} from "./aelin/helpers";
import {
  buildStoryFromContext,
  deriveSessionTitle,
  loadPersistedSessions,
  mergeCitations,
  mergeCitationSnippets,
  normalizeTraceStep,
  newSession,
  toPersistedMessages,
  upsertTraceStep,
  useGroupedMessages,
} from "./aelin/chatState";
import type {
  AelinDeskBridgePayload,
  AelinProps,
  ChatMessage,
  ChatSession,
  HandoffFXState,
  PendingImage,
  TrackingSheetState,
} from "./aelin/types";
import { MessageRow } from "./aelin/conversation/MessageRow";
import { AelinComposer } from "./aelin/composer/AelinComposer";
import { AelinHeader } from "./aelin/layout/AelinHeader";
import { AelinHandoffBanner } from "./aelin/layout/AelinHandoffBanner";
import { useAelinLlmConfig } from "./aelin/hooks/useAelinLlmConfig";
import { useAelinDeviceCenter } from "./aelin/hooks/useAelinDeviceCenter";
import { useAelinTrackingCenter } from "./aelin/hooks/useAelinTrackingCenter";
import {
  AelinCitationDrawers,
  type CitationDrawerState,
  type CitationPreviewState,
} from "./aelin/panels/CitationDrawers";
import { AelinTrackingChoiceSheet } from "./aelin/panels/TrackingChoiceSheet";
import { AelinMemoryDialog } from "./aelin/panels/MemoryDialog";
import { AelinNotificationDialog } from "./aelin/panels/NotificationDialog";
import { AelinLlmSettingsDialog } from "./aelin/panels/LlmSettingsDialog";
import { AelinTrackingCenterDialog } from "./aelin/panels/TrackingCenterDialog";
import { AelinDeviceCenterDialog } from "./aelin/panels/DeviceCenterDialog";
import { AelinTodayFocusCard } from "./aelin/sections/AelinTodayFocusCard";

export type { AelinDeskBridgePayload } from "./aelin/types";

async function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsDataURL(file);
  });
}

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
  const workspaceScope = React.useMemo(
    () => (workspace || "default").trim() || "default",
    [workspace],
  );
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [storyBusy, setStoryBusy] = React.useState(false);
  const [sessions, setSessions] = React.useState<ChatSession[]>(boot.sessions);
  const [activeSessionId, setActiveSessionId] = React.useState<string>(
    boot.activeId,
  );
  const [pendingImages, setPendingImages] = React.useState<PendingImage[]>([]);
  const [contextSnapshot, setContextSnapshot] =
    React.useState<AelinContextResponse | null>(null);
  const [trackingSheet, setTrackingSheet] =
    React.useState<TrackingSheetState | null>(null);
  const {
    trackingDialogOpen,
    setTrackingDialogOpen,
    trackingItems,
    trackingBusy,
    trackingError,
    trackingStatusFilter,
    setTrackingStatusFilter,
    trackingSourceFilter,
    setTrackingSourceFilter,
    trackingKeyword,
    setTrackingKeyword,
    trackingActiveTargetId,
    setTrackingActiveTargetId,
    trackingChanges,
    trackingSnapshots,
    trackingFileMemory,
    trackingDetailBusy,
    trackingDetailError,
    trackingMutationBusy,
    trackingAckBusy,
    trackingChangeSeverityFilter,
    setTrackingChangeSeverityFilter,
    trackingChangeTypeFilter,
    setTrackingChangeTypeFilter,
    trackingAckFilter,
    setTrackingAckFilter,
    filteredTrackingItems,
    trackingUnreadCount,
    activeTrackingItem,
    refreshTracking,
    refreshTrackingDetail,
    patchTrackingTarget,
    runTrackingTargetNow,
    ackTrackingChange,
  } = useAelinTrackingCenter({ workspaceScope, showToast });
  const [memoryDialogOpen, setMemoryDialogOpen] = React.useState(false);
  const [memoryLayerTab, setMemoryLayerTab] = React.useState<
    "facts" | "preferences" | "in_progress"
  >("facts");
  const [notificationDialogOpen, setNotificationDialogOpen] =
    React.useState(false);
  const [notificationBusy, setNotificationBusy] = React.useState(false);
  const [notificationItems, setNotificationItems] = React.useState<
    AelinNotificationItem[]
  >([]);
  const {
    deviceDialogOpen,
    setDeviceDialogOpen,
    deviceBusy,
    deviceSortBy,
    setDeviceSortBy,
    deviceProcesses,
    deviceCapabilities,
    deviceModeState,
    deviceActionBusyPid,
    deviceModeApplying,
    deviceOptimizeBusy,
    deviceOptimizeResult,
    refreshDeviceProcesses,
    openDeviceDialog,
    applyDeviceModeAction,
    handleDeviceProcessAction,
    runDeviceOptimize,
  } = useAelinDeviceCenter({ showToast });
  const [isProgressPending, startProgressTransition] = React.useTransition();
  const {
    llmDialogOpen,
    setLlmDialogOpen,
    llmLoading,
    llmRefreshing,
    llmSaving,
    llmTesting,
    llmCatalog,
    llmProvider,
    llmProviderSelectValue,
    llmCustomProviderId,
    llmBaseUrl,
    llmModel,
    llmTemperature,
    llmApiKey,
    llmHasApiKey,
    llmIsCustomProvider,
    llmSelectedProvider,
    openLlmDialog,
    handleLlmCatalogRefresh,
    handleLlmSave,
    handleLlmTest,
    handleLlmProviderSelect,
    handleLlmCustomProviderIdChange,
    setLlmModel,
    setLlmBaseUrl,
    setLlmTemperature,
    setLlmApiKey,
  } = useAelinLlmConfig({ showToast });
  const [deskOpen, setDeskOpen] = React.useState(false);
  const [deskPanelKey, setDeskPanelKey] = React.useState(0);
  const [handoffFX, setHandoffFX] = React.useState<HandoffFXState | null>(null);
  const [latestSparkMessageId, setLatestSparkMessageId] =
    React.useState<string>("");
  const dismissedTrackTargetsRef = React.useRef<Record<string, true>>({});
  const proactiveSeenRef = React.useRef<Record<string, true>>({});
  const [citationDrawer, setCitationDrawer] =
    React.useState<CitationDrawerState>({
      open: false,
      citation: null,
      detail: null,
      loading: false,
      error: "",
    });
  const [citationPreview, setCitationPreview] =
    React.useState<CitationPreviewState>({
      open: false,
      citation: null,
      url: "",
      loading: false,
      error: "",
    });
  const timelineRef = React.useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = React.useRef(true);
  const citationUrlCacheRef = React.useRef<Record<number, string>>({});
  const handledDeskReturnRef = React.useRef<string>("");
  const handoffFXTimerRef = React.useRef<number | null>(null);
  const activeSession = React.useMemo(
    () => sessions.find((item) => item.id === activeSessionId) || sessions[0],
    [activeSessionId, sessions],
  );
  const messages = activeSession?.messages || [];
  const sortedSessions = React.useMemo(
    () => sessions.slice().sort((a, b) => b.updated_at - a.updated_at),
    [sessions],
  );
  const groupedMessages = useGroupedMessages(messages);
  const nativeMobileShell = React.useMemo(() => isNativeMobileShell(), []);
  const compactMode = React.useMemo(() => {
    if (embedded) return false;
    const qs = new URLSearchParams(location.search || "");
    return nativeMobileShell || (qs.get("compact") || "").trim() === "1";
  }, [embedded, location.search, nativeMobileShell]);
  const compactFramed = compactMode && !nativeMobileShell;
  const mainContainerMaxWidth = embedded ? false : compactMode ? false : "md";

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
    () =>
      contextSnapshot?.memory_layers || {
        facts: [],
        preferences: [],
        in_progress: [],
        generated_at: "",
      },
    [contextSnapshot?.memory_layers],
  );
  const memoryLayerItems = React.useMemo<AelinMemoryLayerItem[]>(() => {
    if (memoryLayerTab === "facts") return memoryLayers.facts || [];
    if (memoryLayerTab === "preferences") return memoryLayers.preferences || [];
    return memoryLayers.in_progress || [];
  }, [
    memoryLayerTab,
    memoryLayers.facts,
    memoryLayers.in_progress,
    memoryLayers.preferences,
  ]);
  const contextNotifications = React.useMemo(
    () => contextSnapshot?.notifications || [],
    [contextSnapshot?.notifications],
  );
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
    () =>
      Math.min(
        99,
        allNotifications.filter((it) => (it.level || "info") !== "default")
          .length,
      ),
    [allNotifications],
  );
  const playHandoffFX = React.useCallback(
    (title: string, detail: string, holdMs = 900) => {
      setHandoffFX({ title, detail });
      if (handoffFXTimerRef.current !== null) {
        window.clearTimeout(handoffFXTimerRef.current);
      }
      handoffFXTimerRef.current = window.setTimeout(() => {
        setHandoffFX(null);
        handoffFXTimerRef.current = null;
      }, holdMs);
    },
    [],
  );

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
              focus_message_id:
                Number.isFinite(messageNum) && messageNum > 0
                  ? Math.floor(messageNum)
                  : undefined,
              focus_contact_id:
                Number.isFinite(contactNum) && contactNum > 0
                  ? Math.floor(contactNum)
                  : undefined,
              focus_query: focusQuery || undefined,
              workspace: workspaceScope,
              highlight_source: source || undefined,
              resume_prompt: resumePrompt || undefined,
              ts: Date.now(),
            }),
          );
        } catch {
          // ignore storage failures
        }
      }
      if (onOpenDesk) {
        playHandoffFX(
          "Aelin -> Desk",
          focusQuery
            ? `正在定位主题“${focusQuery.slice(0, 36)}”`
            : "正在打开观察视图",
        );
        onOpenDesk({
          sessionId: sid,
          workspace: workspaceScope,
          messageId:
            Number.isFinite(messageNum) && messageNum > 0
              ? Math.floor(messageNum)
              : undefined,
          contactId:
            Number.isFinite(contactNum) && contactNum > 0
              ? Math.floor(contactNum)
              : undefined,
          focusQuery: focusQuery || undefined,
          highlightSource: source || undefined,
          resumePrompt: resumePrompt || undefined,
        });
        return;
      }
      playHandoffFX(
        "Aelin -> Desk",
        focusQuery
          ? `正在定位主题“${focusQuery.slice(0, 36)}”`
          : "正在打开观察视图",
      );
      window.setTimeout(() => {
        setDeskPanelKey((prev) => prev + 1);
        setDeskOpen(true);
      }, 140);
    },
    [
      activeSession?.id,
      activeSessionId,
      onOpenDesk,
      playHandoffFX,
      workspaceScope,
    ],
  );

  const refreshContext = React.useCallback(async () => {
    try {
      const ctx = await getAelinContext(workspaceScope, "");
      setContextSnapshot(ctx);
    } catch {
      // ignore temporary context fetch failures
    }
  }, [workspaceScope]);

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

  const pushSystemNotification = React.useCallback(
    (item: AelinNotificationItem) => {
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
    },
    [],
  );

  const pollProactive = React.useCallback(async () => {
    try {
      const ret = await getAelinProactivePoll(workspaceScope, 8);
      const incoming = Array.isArray(ret.items)
        ? ret.items.filter(Boolean)
        : [];
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
          level === "error"
            ? "error"
            : level === "warning"
              ? "warning"
              : level === "success"
                ? "success"
                : "info",
        );
        if (document.hidden) {
          pushSystemNotification(item);
        }
      }
    } catch {
      // ignore transient proactive polling failures
    }
  }, [pushSystemNotification, showToast, workspaceScope]);

  React.useEffect(() => {
    void refreshContext();
  }, [refreshContext]);

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
        }),
      );
    },
    [activeSessionId],
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
      const payload = {
        version: 1,
        sessions: compact,
        active_id: activeSessionId,
        saved_at: Date.now(),
      };
      window.localStorage.setItem(
        AELIN_SESSIONS_STORAGE_KEY,
        JSON.stringify(payload),
      );
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
      setInput((prev) =>
        prev.trim() ? prev : `继续围绕这个主题：${focusQuery}`,
      );
    }
    if (Number.isFinite(focusMessageId) && focusMessageId > 0) {
      playHandoffFX(
        "Desk -> Aelin",
        source
          ? `已带回 ${source} 的观察结果（消息 #${focusMessageId}）`
          : `已带回焦点消息 #${focusMessageId}`,
      );
      showToast(
        source
          ? `已从 Desk 返回，继续围绕 ${source}（消息 #${focusMessageId}）`
          : `已从 Desk 返回，焦点消息 #${focusMessageId}`,
        "info",
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
    [showToast],
  );

  const appendFiles = React.useCallback(
    async (files: File[]) => {
      const existing = pendingImages.length;
      if (existing >= 4) {
        showToast("最多上传 4 张图片", "info");
        return;
      }
      const candidates = files
        .filter((file) => file.type.startsWith("image/"))
        .slice(0, 4 - existing);
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
        const urls = await Promise.all(
          candidates.map((file) => fileToDataUrl(file)),
        );
        setPendingImages((prev) => [
          ...prev,
          ...urls.map((dataUrl, idx) => ({
            id: nextMessageId(),
            dataUrl,
            name: candidates[idx]?.name || `image-${Date.now()}`,
          })),
        ]);
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "图片读取失败",
          "error",
        );
      }
    },
    [pendingImages.length, showToast],
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
        .filter(
          (item) =>
            !item.pending &&
            (item.role === "user" || item.role === "assistant"),
        )
        .slice(-10)
        .map((item) => ({ role: item.role, content: item.content }));
      const imagesForSend: AelinImageInput[] = pendingImages
        .slice(0, 4)
        .map((img) => ({
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
                  {
                    id: nextMessageId(),
                    role: "user",
                    content: query || "（图片）",
                    ts: nowTs,
                    images: imagesForSend,
                  },
                  {
                    id: assistantId,
                    role: "assistant",
                    content: "",
                    ts: nowTs + 1,
                    pending: true,
                    tool_trace: [
                      {
                        stage: "main_agent",
                        status: "running",
                        detail: "主控已接收请求",
                        count: 0,
                        ts: nowTs + 1,
                      },
                    ],
                  },
                ],
                title: deriveSessionTitle([
                  ...session.messages,
                  {
                    id: "tmp",
                    role: "user",
                    content: query || "（图片）",
                    ts: nowTs,
                    images: imagesForSend,
                  },
                ]),
                updated_at: Date.now(),
              }
            : session,
        ),
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
                                tool_trace: upsertTraceStep(
                                  item.tool_trace || [],
                                  {
                                    stage: "main_agent",
                                    status: "running",
                                    detail: "主控开始编排子任务",
                                    count: 1,
                                  },
                                ),
                              }
                            : item,
                        ),
                      }
                    : session,
                ),
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
                                tool_trace: upsertTraceStep(
                                  item.tool_trace || [],
                                  evt.step,
                                ),
                              }
                            : item,
                        ),
                      }
                    : session,
                ),
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
            const sourceBits = [evt.provider || "", evt.fetch_mode || ""]
              .filter((x) => !!x.trim())
              .join("/");
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
                                citations: mergeCitations(
                                  item.citations || [],
                                  [citation],
                                  12,
                                ),
                                citation_snippets: mergeCitationSnippets(
                                  item.citation_snippets,
                                  [{ citation, snippet: evt.snippet || "" }],
                                ),
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
                                  },
                                ),
                              }
                            : item,
                        ),
                      }
                    : session,
                ),
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
                                tool_trace: upsertTraceStep(
                                  item.tool_trace || [],
                                  {
                                    stage: "trace_agent",
                                    status: "completed",
                                    detail,
                                    count: Number(
                                      (evt.items || []).length || 0,
                                    ),
                                  },
                                ),
                              }
                            : item,
                        ),
                      }
                    : session,
                ),
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
                              content:
                                evt.result.answer || "当前未生成文本回答。",
                              expression: normalizeExpressionId(
                                evt.result.expression,
                              ),
                              citations: mergeCitations(
                                item.citations || [],
                                evt.result.citations || [],
                                12,
                              ),
                              citation_snippets: item.citation_snippets,
                              actions: evt.result.actions || [],
                              tool_trace: (evt.result.tool_trace || []).map(
                                normalizeTraceStep,
                              ),
                            }
                          : item,
                      ),
                      updated_at: Date.now(),
                    }
                  : session,
              ),
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
                            expression: normalizeExpressionId(
                              result.expression,
                            ),
                            citations: mergeCitations(
                              item.citations || [],
                              result.citations || [],
                              12,
                            ),
                            citation_snippets: item.citation_snippets,
                            actions: result.actions || [],
                            tool_trace: (result.tool_trace || []).map(
                              normalizeTraceStep,
                            ),
                          }
                        : item,
                    ),
                    updated_at: Date.now(),
                  }
                : session,
            ),
          );
        }

        if (finalResult) {
          setLatestSparkMessageId(assistantId);
          const trackAction = (finalResult.actions || []).find(
            (it) => it.kind === "confirm_track",
          );
          if (trackAction) {
            const target = (trackAction.payload.target || "")
              .trim()
              .toLowerCase();
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
                              detail:
                                error instanceof Error
                                  ? error.message
                                  : "request failed",
                              count: 0,
                            },
                          ),
                        }
                      : item,
                  ),
                  updated_at: Date.now(),
                }
              : session,
          ),
        );
      } finally {
        setBusy(false);
      }
    },
    [
      activeSession?.messages,
      activeSessionId,
      busy,
      pendingImages,
      refreshContext,
      startProgressTransition,
      workspaceScope,
    ],
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
            highlightSource:
              action.payload.source ||
              lastAssistantCitation?.source_label ||
              "",
            resumePrompt: action.payload.query || "",
          });
        } else {
          navigate(path);
        }
        return;
      }
      if (action.kind === "open_settings") {
        const targetPath =
          (action.payload.path || "/settings").trim() || "/settings";
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
          highlightSource:
            action.payload.source || lastAssistantCitation?.source_label || "",
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
    [
      lastAssistantCitation?.source_label,
      navigate,
      openDeskWithContext,
      openLlmDialog,
      refreshTrackingDetail,
      showToast,
    ],
  );

  const resolveCitationUrl = React.useCallback(
    async (
      item: AelinCitation,
    ): Promise<{ url: string; detail: MessageDetail | null }> => {
      const id = Number(item.message_id || 0);
      if (id > 0 && citationUrlCacheRef.current[id]) {
        return { url: citationUrlCacheRef.current[id], detail: null };
      }
      const detail = await getMessage(item.message_id);
      const url =
        extractFirstUrl(detail.body || "") ||
        extractFirstUrl(detail.subject || "");
      if (id > 0 && url) {
        citationUrlCacheRef.current[id] = url;
      }
      return { url, detail };
    },
    [],
  );

  const handleCitationOpen = React.useCallback(
    async (item: AelinCitation) => {
      setCitationPreview({
        open: true,
        citation: item,
        url: "",
        loading: true,
        error: "",
      });
      try {
        const { url, detail } = await resolveCitationUrl(item);
        if (url) {
          setCitationPreview({
            open: true,
            citation: item,
            url,
            loading: false,
            error: "",
          });
          return;
        }
        setCitationPreview({
          open: false,
          citation: null,
          url: "",
          loading: false,
          error: "",
        });
        setCitationDrawer({
          open: true,
          citation: item,
          detail,
          loading: false,
          error: "该证据暂无可跳转网页链接，已切换到详情视图。",
        });
      } catch (error) {
        setCitationPreview({
          open: false,
          citation: null,
          url: "",
          loading: false,
          error: "",
        });
        setCitationDrawer({
          open: true,
          citation: item,
          detail: null,
          loading: false,
          error: error instanceof Error ? error.message : "加载详情失败",
        });
      }
    },
    [resolveCitationUrl],
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
          track_type:
            trackingSheet.action.payload.track_type === "url" ? "url" : "term",
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
        showToast(
          error instanceof Error ? error.message : "跟踪开启失败",
          "error",
        );
      }
    },
    [
      confirm,
      openLlmDialog,
      refreshContext,
      refreshTracking,
      refreshTrackingDetail,
      showToast,
      trackingSheet,
      updateActiveMessages,
      workspaceScope,
    ],
  );

  const runStoryMode = React.useCallback(async () => {
    setStoryBusy(true);
    try {
      const ctx =
        contextSnapshot || (await getAelinContext(workspaceScope, ""));
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
            {
              stage: "planner",
              status: "completed",
              detail: "story mode enabled",
              count: 1,
            },
            {
              stage: "local_search",
              status: "completed",
              detail: "used 24h local context",
              count: (ctx.focus_items || []).length,
            },
          ],
        },
      ]);
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : "故事模式生成失败",
        "error",
      );
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
    [
      openDeskWithContext,
      openDeviceDialog,
      refreshTrackingDetail,
      runStoryMode,
    ],
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
        borderLeft: compactFramed
          ? `1px solid ${alpha(theme.palette.divider, 0.8)}`
          : "none",
        borderRight: compactFramed
          ? `1px solid ${alpha(theme.palette.divider, 0.8)}`
          : "none",
      }}
    >
      <AelinHeader
        compactMode={compactMode}
        embedded={embedded}
        mainContainerMaxWidth={mainContainerMaxWidth}
        activeSessionId={activeSession?.id || ""}
        sortedSessions={sortedSessions}
        storyBusy={storyBusy}
        trackingUnreadCount={trackingUnreadCount}
        trackingItemsCount={trackingItems.length}
        unreadNotificationCount={unreadNotificationCount}
        onSessionChange={setActiveSessionId}
        onNewConversation={resetConversation}
        onRunStoryMode={() => {
          void runStoryMode();
        }}
        onOpenTracking={() => setTrackingDialogOpen(true)}
        onOpenNotification={() => setNotificationDialogOpen(true)}
        onOpenDevice={openDeviceDialog}
        onOpenMemory={() => setMemoryDialogOpen(true)}
        onOpenDesk={() => setDeskOpen(true)}
        onOpenSettings={openLlmDialog}
        onRequestClose={onRequestClose}
      />{" "}
      <AelinHandoffBanner handoffFX={handoffFX} />{" "}
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
        <Container
          maxWidth={mainContainerMaxWidth}
          sx={{
            px: { xs: 0.5, sm: compactMode ? 1.0 : 0.4 },
            py: compactMode ? 1.0 : 1.35,
          }}
        >
          {messages.length <= 1 ? (
            <AelinTodayFocusCard
              contextSnapshot={contextSnapshot}
              storyBusy={storyBusy}
              onRunStoryMode={() => {
                void runStoryMode();
              }}
              onSendPrompt={(prompt) => {
                void send(prompt);
              }}
            />
          ) : null}{" "}
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
      <AelinComposer
        compactMode={compactMode}
        mainContainerMaxWidth={mainContainerMaxWidth}
        input={input}
        busy={busy}
        pendingImages={pendingImages}
        lastAssistantCitation={lastAssistantCitation}
        onInputChange={setInput}
        onSend={(value) => {
          void send(value);
        }}
        onAppendFiles={appendFiles}
        onRemovePendingImage={(id) =>
          setPendingImages((prev) => prev.filter((item) => item.id !== id))
        }
        onOpenDeskObserve={() =>
          openDeskWithContext({
            messageId: lastAssistantCitation?.message_id,
            focusQuery:
              (input || "").trim() || lastAssistantCitation?.title || "",
            highlightSource:
              lastAssistantCitation?.source_label ||
              lastAssistantCitation?.source ||
              "",
            resumePrompt:
              ((input || "").trim() &&
                `继续围绕这个问题讨论：${input.trim()}`) ||
              (lastAssistantCitation?.title &&
                `继续分析这条线索：${lastAssistantCitation.title}`) ||
              "继续从观察视图里分析我的重点信息。",
          })
        }
      />{" "}
      <AelinLlmSettingsDialog
        open={llmDialogOpen}
        loading={llmLoading}
        refreshing={llmRefreshing}
        saving={llmSaving}
        testing={llmTesting}
        catalog={llmCatalog}
        provider={llmProvider}
        providerSelectValue={llmProviderSelectValue}
        customProviderId={llmCustomProviderId}
        baseUrl={llmBaseUrl}
        model={llmModel}
        temperature={llmTemperature}
        apiKey={llmApiKey}
        hasApiKey={llmHasApiKey}
        isCustomProvider={llmIsCustomProvider}
        selectedProvider={llmSelectedProvider}
        customProviderOption={CUSTOM_PROVIDER_OPTION}
        providerDisplay={normalizeProviderId(llmProvider) || "rule_based"}
        onClose={() => setLlmDialogOpen(false)}
        onRefreshCatalog={() => {
          void handleLlmCatalogRefresh();
        }}
        onProviderSelect={handleLlmProviderSelect}
        onCustomProviderIdChange={handleLlmCustomProviderIdChange}
        onModelChange={setLlmModel}
        onBaseUrlChange={setLlmBaseUrl}
        onTemperatureChange={setLlmTemperature}
        onApiKeyChange={setLlmApiKey}
        onOpenSettings={() => navigate("/settings")}
        onTest={() => {
          void handleLlmTest();
        }}
        onSave={() => {
          void handleLlmSave();
        }}
      />
      <AelinTrackingCenterDialog
        trackingDialogOpen={trackingDialogOpen}
        setTrackingDialogOpen={setTrackingDialogOpen}
        refreshTracking={refreshTracking}
        activeTrackingItem={activeTrackingItem}
        refreshTrackingDetail={refreshTrackingDetail}
        trackingBusy={trackingBusy}
        trackingItems={trackingItems}
        trackingUnreadCount={trackingUnreadCount}
        trackingKeyword={trackingKeyword}
        setTrackingKeyword={setTrackingKeyword}
        trackingStatusFilter={trackingStatusFilter}
        setTrackingStatusFilter={setTrackingStatusFilter}
        trackingSourceFilter={trackingSourceFilter}
        setTrackingSourceFilter={setTrackingSourceFilter}
        filteredTrackingItems={filteredTrackingItems}
        trackingError={trackingError}
        trackingActiveTargetId={trackingActiveTargetId}
        setTrackingActiveTargetId={setTrackingActiveTargetId}
        patchTrackingTarget={patchTrackingTarget}
        trackingMutationBusy={trackingMutationBusy}
        runTrackingTargetNow={runTrackingTargetNow}
        workspaceScope={workspaceScope}
        trackingChangeSeverityFilter={trackingChangeSeverityFilter}
        setTrackingChangeSeverityFilter={setTrackingChangeSeverityFilter}
        trackingChangeTypeFilter={trackingChangeTypeFilter}
        setTrackingChangeTypeFilter={setTrackingChangeTypeFilter}
        trackingAckFilter={trackingAckFilter}
        setTrackingAckFilter={setTrackingAckFilter}
        trackingDetailBusy={trackingDetailBusy}
        trackingDetailError={trackingDetailError}
        trackingChanges={trackingChanges}
        trackingAckBusy={trackingAckBusy}
        ackTrackingChange={ackTrackingChange}
        trackingSnapshots={trackingSnapshots}
        trackingFileMemory={trackingFileMemory}
        copyText={copyText}
      />
      <AelinDeviceCenterDialog
        deviceDialogOpen={deviceDialogOpen}
        setDeviceDialogOpen={setDeviceDialogOpen}
        refreshDeviceProcesses={refreshDeviceProcesses}
        deviceBusy={deviceBusy}
        deviceCapabilities={deviceCapabilities}
        deviceModeState={deviceModeState}
        deviceModeApplying={deviceModeApplying}
        applyDeviceModeAction={applyDeviceModeAction}
        deviceSortBy={deviceSortBy}
        setDeviceSortBy={setDeviceSortBy}
        runDeviceOptimize={runDeviceOptimize}
        deviceOptimizeBusy={deviceOptimizeBusy}
        deviceOptimizeResult={deviceOptimizeResult}
        deviceProcesses={deviceProcesses}
        deviceActionBusyPid={deviceActionBusyPid}
        handleDeviceProcessAction={handleDeviceProcessAction}
      />
      <AelinMemoryDialog
        open={memoryDialogOpen}
        onClose={() => setMemoryDialogOpen(false)}
        layerTab={memoryLayerTab}
        onLayerTabChange={setMemoryLayerTab}
        memoryLayers={memoryLayers}
        layerItems={memoryLayerItems}
      />
      <AelinNotificationDialog
        open={notificationDialogOpen}
        busy={notificationBusy}
        items={allNotifications}
        onClose={() => setNotificationDialogOpen(false)}
        onRefresh={() => {
          void refreshNotifications();
        }}
        onAction={(item) => {
          handleNotificationAction(item);
        }}
      />
      <Drawer
        anchor="right"
        open={deskOpen}
        onClose={() => setDeskOpen(false)}
        PaperProps={{
          sx: {
            width: {
              xs: "100%",
              sm: compactFramed ? "min(100vw, 430px)" : "min(100vw, 1320px)",
            },
            maxWidth: "100vw",
            borderLeft: "1px solid",
            borderColor: "divider",
            bgcolor: theme.palette.background.default,
          },
        }}
      >
        <Box sx={{ height: "100dvh", overflow: "auto" }}>
          <Dashboard
            key={`embedded-desk-${deskPanelKey}`}
            embedded
            onRequestClose={() => setDeskOpen(false)}
          />
        </Box>
      </Drawer>
      <AelinTrackingChoiceSheet
        trackingSheet={trackingSheet}
        onChoice={(choice) => {
          void handleTrackingChoice(choice);
        }}
      />
      <AelinCitationDrawers
        citationPreview={citationPreview}
        citationDrawer={citationDrawer}
        onClosePreview={() =>
          setCitationPreview((prev) => ({ ...prev, open: false }))
        }
        onCloseDrawer={() =>
          setCitationDrawer((prev) => ({ ...prev, open: false }))
        }
        onOpenCitationWeb={(citation) => {
          void handleCitationOpen(citation);
        }}
        onOpenDeskFromCitation={(citation) => {
          openDeskWithContext({
            messageId: citation.message_id,
            highlightSource: citation.source_label || citation.source,
            resumePrompt: `继续分析这条证据并给我后续建议：${citation.title}`,
          });
          setCitationDrawer((prev) => ({ ...prev, open: false }));
        }}
        onCopyText={(text) => {
          void copyText(text);
        }}
      />
      {ConfirmDialog}
    </Box>
  );
}
