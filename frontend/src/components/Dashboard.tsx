import React, {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
} from "react";
import useSWR from "swr";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Divider from "@mui/material/Divider";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Drawer from "@mui/material/Drawer";
import Tooltip from "@mui/material/Tooltip";
import Chip from "@mui/material/Chip";
import useMediaQuery from "@mui/material/useMediaQuery";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import LaunchIcon from "@mui/icons-material/Launch";
import KeyboardReturnIcon from "@mui/icons-material/KeyboardReturn";
import { motion } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import { alpha, useTheme } from "@mui/material/styles";
import { TopBar } from "./TopBar";
import { ConversationDrawer } from "./ConversationDrawer";
import { GmailBindDialog } from "./dashboard/GmailBindDialog";
import { FirstRunGuideDialog } from "./dashboard/FirstRunGuideDialog";
import { DashboardSyncProgress } from "./dashboard/SyncProgressPanel";
import { AgentPanelSection } from "./dashboard/layout/AgentPanelSection";
import { DeskBoardSurface } from "./dashboard/layout/DeskBoardSurface";
import { DashboardHandoffBanner } from "./dashboard/layout/DashboardHandoffBanner";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import {
  AgentAdvancedSearchItem,
  AgentCardLayoutItem,
  AgentDailyBrief,
  AgentDailyBriefAction,
  AgentMemorySnapshot,
  AgentPinRecommendationResponse,
  AgentTodoItem,
  Contact,
  ConnectedAccount,
  addAgentMemoryNote,
  advancedSearch,
  agentDraftReply,
  agentSummarize,
  createAccount,
  createAgentTodo,
  deleteAgentMemoryNote,
  deleteAgentTodo,
  getAgentMemory,
  getMessage,
  listAccounts,
  startAccountOAuth,
  syncAccount,
  syncAgentCardLayout,
  updateAgentTodo,
} from "../api";
import { useToast } from "../contexts/ToastContext";
import {
  extractRedirectOriginFromAuthUrl,
  openOAuthPopup,
  waitForOAuthPopupMessage,
} from "../utils/oauthPopup";

const DEFAULT_DASHBOARD_SYNC_CONCURRENCY = 12;
const DASHBOARD_SYNC_CONCURRENCY = (() => {
  const raw = Number(
    import.meta.env.VITE_DASHBOARD_SYNC_CONCURRENCY ??
      DEFAULT_DASHBOARD_SYNC_CONCURRENCY,
  );
  if (!Number.isFinite(raw)) return DEFAULT_DASHBOARD_SYNC_CONCURRENCY;
  return Math.max(1, Math.floor(raw));
})();

const FIRST_RUN_GUIDE_KEY = "mercurydesk:dashboard:first-run-guide:v1";
const WORKSPACE_KEY = "mercurydesk:dashboard:workspace:v1";
const SIDEBAR_OPEN_KEY = "mercurydesk:dashboard:ai-sidebar-open:v1";
const AELIN_LAST_SESSION_KEY = "aelin:last-session-id:v1";
const AELIN_LAST_DESK_BRIDGE_KEY = "aelin:last-desk-bridge:v1";
const WORKSPACES = [
  { key: "default", label: "主工作区" },
  { key: "work", label: "工作" },
  { key: "life", label: "生活" },
  { key: "monitor", label: "监控" },
];
const DESKTOP_SIDEBAR_WIDTH = 372;
const DESKTOP_SIDEBAR_GAP = 16;

const wait = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

type AelinBridgeContext = {
  fromAelin: boolean;
  sessionId: string;
  workspace: string;
  focusMessageId: number | null;
  focusContactId: number | null;
  focusQuery: string;
  highlightSource: string;
  resumePrompt: string;
};

type HandoffFXState = {
  title: string;
  detail: string;
};

const parsePositiveInt = (raw: string | null): number | null => {
  const n = Number(raw || 0);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
};

const readBridgeFromSearch = (search: string): AelinBridgeContext => {
  const qs = new URLSearchParams(search);
  const workspace = (qs.get("workspace") || "default").trim() || "default";
  return {
    fromAelin: (qs.get("from") || "").trim().toLowerCase() === "aelin",
    sessionId: (qs.get("session_id") || "").trim(),
    workspace,
    focusMessageId: parsePositiveInt(
      qs.get("focus_message_id") || qs.get("message_id"),
    ),
    focusContactId: parsePositiveInt(qs.get("focus_contact_id")),
    focusQuery: (qs.get("focus_query") || "").trim(),
    highlightSource: (qs.get("highlight_source") || "").trim(),
    resumePrompt: (qs.get("resume_prompt") || "").trim(),
  };
};

const normalizeBridgeContext = (
  raw: Partial<AelinBridgeContext> | null | undefined,
): AelinBridgeContext | null => {
  if (!raw) return null;
  const legacy = raw as Record<string, unknown>;
  return {
    fromAelin: Boolean(
      raw.fromAelin ?? legacy.from_aelin ?? legacy.from === "aelin",
    ),
    sessionId: String(raw.sessionId || legacy.session_id || "").trim(),
    workspace: String(raw.workspace || "default").trim() || "default",
    focusMessageId: parsePositiveInt(
      raw.focusMessageId == null && legacy.focus_message_id == null
        ? null
        : String(raw.focusMessageId ?? legacy.focus_message_id),
    ),
    focusContactId: parsePositiveInt(
      raw.focusContactId == null && legacy.focus_contact_id == null
        ? null
        : String(raw.focusContactId ?? legacy.focus_contact_id),
    ),
    focusQuery: String(raw.focusQuery || legacy.focus_query || "").trim(),
    highlightSource: String(
      raw.highlightSource || legacy.highlight_source || "",
    ).trim(),
    resumePrompt: String(raw.resumePrompt || legacy.resume_prompt || "").trim(),
  };
};

const formatRunningAccounts = (labels: string[]) => {
  if (labels.length === 0) return "";
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return labels.join("、");
  return `${labels[0]}、${labels[1]} 等 ${labels.length} 个账户`;
};

type DashboardProps = {
  embedded?: boolean;
  onRequestClose?: () => void;
};

export default function Dashboard({
  embedded = false,
  onRequestClose,
}: DashboardProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("lg"));
  const prefersReducedMotion = useMediaQuery(
    "(prefers-reduced-motion: reduce)",
  );
  const location = useLocation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const compactMode = useMemo(() => {
    const panel =
      new URLSearchParams(location.search || "").get("compact") || "";
    return panel.trim() === "1";
  }, [location.search]);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  const [drawerContact, setDrawerContact] = useState<Contact | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] =
    useState<DashboardSyncProgress | null>(null);
  const [gmailPromptOpen, setGmailPromptOpen] = useState(false);
  const [bindingGmail, setBindingGmail] = useState(false);
  const [firstRunGuideOpen, setFirstRunGuideOpen] = useState(false);
  const [activeWorkspace, setActiveWorkspace] = useState<string>(() => {
    try {
      return localStorage.getItem(WORKSPACE_KEY) || "default";
    } catch {
      return "default";
    }
  });

  const [memorySnapshot, setMemorySnapshot] =
    useState<AgentMemorySnapshot | null>(null);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryCorrection, setMemoryCorrection] = useState("");

  const [todoInput, setTodoInput] = useState("");
  const [todoBusy, setTodoBusy] = useState(false);

  const [quickActionOutput, setQuickActionOutput] = useState<{
    title: string;
    content: string;
  } | null>(null);
  const [advancedQuery, setAdvancedQuery] = useState("");
  const [advancedSource, setAdvancedSource] = useState("");
  const [advancedUnreadOnly, setAdvancedUnreadOnly] = useState(false);
  const [advancedDays, setAdvancedDays] = useState(30);
  const [advancedLimit, setAdvancedLimit] = useState(20);
  const [advancedBusy, setAdvancedBusy] = useState(false);
  const [advancedItems, setAdvancedItems] = useState<AgentAdvancedSearchItem[]>(
    [],
  );
  const [actionBusy, setActionBusy] = useState(false);
  const [activePanel, setActivePanel] = useState<
    "brief" | "todo" | "search" | "memory"
  >("brief");
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState<boolean>(() => {
    if (embedded) return true;
    try {
      const raw = localStorage.getItem(SIDEBAR_OPEN_KEY);
      if (raw === "0") return false;
      if (raw === "1") return true;
    } catch {
      // ignore
    }
    return true;
  });
  const [desktopHostWidth, setDesktopHostWidth] = useState(0);
  const [boardNaturalHeight, setBoardNaturalHeight] = useState(860);
  const [highlightContactId, setHighlightContactId] = useState<number | null>(
    null,
  );
  const [handoffFX, setHandoffFX] = useState<HandoffFXState | null>(null);
  const [pendingFocusMessageId, setPendingFocusMessageId] = useState<
    number | null
  >(null);
  const [pendingFocusContactId, setPendingFocusContactId] = useState<
    number | null
  >(null);
  const [bridgeContext, setBridgeContext] = useState<AelinBridgeContext | null>(
    () => {
      if (typeof window === "undefined") return null;
      try {
        const raw = window.sessionStorage.getItem(AELIN_LAST_DESK_BRIDGE_KEY);
        if (!raw) return null;
        return normalizeBridgeContext(
          JSON.parse(raw) as Partial<AelinBridgeContext>,
        );
      } catch {
        return null;
      }
    },
  );

  const layoutSyncTimerRef = useRef<number | null>(null);
  const handoffFXTimerRef = useRef<number | null>(null);
  const desktopHostRef = useRef<HTMLDivElement | null>(null);
  const boardNaturalRef = useRef<HTMLDivElement | null>(null);
  const processedBridgeSearchRef = useRef<string>("");

  useEffect(() => {
    if (selectedContact) setDrawerContact(selectedContact);
  }, [selectedContact]);

  const debouncedQuery = useDebouncedValue(searchQuery, 300);
  const contactsKey = useMemo(() => {
    const qs = new URLSearchParams();
    if (debouncedQuery) qs.set("q", debouncedQuery);
    qs.set("limit", "200");
    return `/api/v1/contacts?${qs.toString()}`;
  }, [debouncedQuery]);

  const { data: contacts, mutate: mutateContacts } =
    useSWR<Contact[]>(contactsKey);
  const { data: accounts, mutate: mutateAccounts } =
    useSWR<ConnectedAccount[]>("/api/v1/accounts");
  const { data: pinRecommendations, mutate: mutatePinRecommendations } =
    useSWR<AgentPinRecommendationResponse>(
      "/api/v1/agent/pin-recommendations?limit=8",
    );
  const { data: dailyBrief, mutate: mutateDailyBrief } =
    useSWR<AgentDailyBrief>("/api/v1/agent/daily-brief");
  const { data: todos, mutate: mutateTodos } = useSWR<AgentTodoItem[]>(
    "/api/v1/agent/todos?include_done=false",
  );

  const contactsById = useMemo(() => {
    const map = new Map<number, Contact>();
    (contacts ?? []).forEach((item) => map.set(item.id, item));
    return map;
  }, [contacts]);

  const hasGmailAccount = useMemo(
    () => !!accounts?.some((item) => item.provider.toLowerCase() === "gmail"),
    [accounts],
  );

  const loadMemorySnapshot = useCallback(
    async (query = "") => {
      setMemoryBusy(true);
      try {
        const data = await getAgentMemory(query);
        setMemorySnapshot(data);
      } catch (error) {
        showToast(
          error instanceof Error
            ? `记忆加载失败: ${error.message}`
            : "记忆加载失败",
          "error",
        );
      } finally {
        setMemoryBusy(false);
      }
    },
    [showToast],
  );

  const refreshAgentPanels = useCallback(async () => {
    await Promise.all([
      mutatePinRecommendations(),
      mutateDailyBrief(),
      mutateTodos(),
      loadMemorySnapshot(""),
    ]);
  }, [
    loadMemorySnapshot,
    mutateDailyBrief,
    mutatePinRecommendations,
    mutateTodos,
  ]);

  useEffect(() => {
    if (!accounts) return;
    if (hasGmailAccount) {
      setGmailPromptOpen(false);
      sessionStorage.removeItem("mercurydesk:gmail-bind-dismissed");
      return;
    }
    const dismissed =
      sessionStorage.getItem("mercurydesk:gmail-bind-dismissed") === "1";
    if (!dismissed) setGmailPromptOpen(true);
  }, [accounts, hasGmailAccount]);

  useEffect(() => {
    try {
      const seen = localStorage.getItem(FIRST_RUN_GUIDE_KEY) === "1";
      if (!seen) setFirstRunGuideOpen(true);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(WORKSPACE_KEY, activeWorkspace);
    } catch {
      // ignore
    }
  }, [activeWorkspace]);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_OPEN_KEY, desktopSidebarOpen ? "1" : "0");
    } catch {
      // ignore
    }
  }, [desktopSidebarOpen, embedded]);

  useEffect(() => {
    if (!isMobile) setMobilePanelOpen(false);
  }, [isMobile]);

  useEffect(() => {
    loadMemorySnapshot("");
  }, [loadMemorySnapshot]);

  const playHandoffFX = useCallback(
    (title: string, detail: string, holdMs = 980) => {
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

  useEffect(() => {
    const bridge = readBridgeFromSearch(location.search || "");
    const hasFocus = Boolean(bridge.focusMessageId || bridge.focusContactId);
    const hasBridgeSignal = bridge.fromAelin || hasFocus;
    if (!hasBridgeSignal) return;
    if (processedBridgeSearchRef.current === location.search) return;
    processedBridgeSearchRef.current = location.search;

    if (bridge.workspace && bridge.workspace !== activeWorkspace) {
      setActiveWorkspace(bridge.workspace);
    }
    if (hasFocus) {
      setSearchQuery("");
      setPendingFocusMessageId(bridge.focusMessageId);
      setPendingFocusContactId(bridge.focusContactId);
      setActivePanel("search");
    }
    if (bridge.focusQuery) {
      setSearchQuery(bridge.focusQuery);
      setActivePanel("search");
    }
    if (bridge.fromAelin && !isMobile) {
      setDesktopSidebarOpen(true);
      playHandoffFX(
        "Aelin -> Desk",
        bridge.focusQuery
          ? `已接收主题“${bridge.focusQuery.slice(0, 36)}”，正在定位观察点`
          : "已接收上下文，正在定位观察点",
      );
    }

    setBridgeContext((prev) => {
      const merged: AelinBridgeContext = {
        fromAelin: bridge.fromAelin || Boolean(prev?.fromAelin),
        sessionId: bridge.sessionId || prev?.sessionId || "",
        workspace: bridge.workspace || prev?.workspace || "default",
        focusMessageId: bridge.focusMessageId ?? prev?.focusMessageId ?? null,
        focusContactId: bridge.focusContactId ?? prev?.focusContactId ?? null,
        focusQuery: bridge.focusQuery || prev?.focusQuery || "",
        highlightSource: bridge.highlightSource || prev?.highlightSource || "",
        resumePrompt: bridge.resumePrompt || prev?.resumePrompt || "",
      };
      if (typeof window !== "undefined") {
        try {
          if (merged.sessionId)
            window.localStorage.setItem(
              AELIN_LAST_SESSION_KEY,
              merged.sessionId,
            );
          window.sessionStorage.setItem(
            AELIN_LAST_DESK_BRIDGE_KEY,
            JSON.stringify(merged),
          );
        } catch {
          // ignore storage failures
        }
      }
      return merged;
    });
  }, [activeWorkspace, isMobile, location.search, playHandoffFX]);

  useEffect(() => {
    if (!pendingFocusMessageId) return;
    let cancelled = false;
    const targetMessageId = pendingFocusMessageId;
    setPendingFocusMessageId(null);
    (async () => {
      try {
        const detail = await getMessage(targetMessageId);
        if (cancelled) return;
        setPendingFocusContactId(detail.contact_id);
      } catch (error) {
        if (!cancelled) {
          showToast(
            error instanceof Error
              ? `无法定位焦点消息: ${error.message}`
              : "无法定位焦点消息",
            "warning",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pendingFocusMessageId, showToast]);

  useEffect(() => {
    if (!pendingFocusContactId) return;
    if (!contacts) return;
    const target = contactsById.get(pendingFocusContactId);
    if (!target) {
      showToast("Aelin 指向的联系人不在当前列表中。", "warning");
      setPendingFocusContactId(null);
      return;
    }
    setSelectedContact(target);
    setDrawerContact(target);
    setHighlightContactId(target.id);
    setPendingFocusContactId(null);
  }, [contacts, contactsById, pendingFocusContactId, showToast]);

  useEffect(() => {
    if (!highlightContactId) return;
    const timer = window.setTimeout(() => setHighlightContactId(null), 2600);
    return () => window.clearTimeout(timer);
  }, [highlightContactId]);

  useEffect(() => {
    return () => {
      if (layoutSyncTimerRef.current !== null) {
        window.clearTimeout(layoutSyncTimerRef.current);
      }
      if (handoffFXTimerRef.current !== null) {
        window.clearTimeout(handoffFXTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (isMobile) return;
    const host = desktopHostRef.current;
    if (!host) return;

    let frame = 0;
    const update = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const next = host.clientWidth;
        setDesktopHostWidth((prev) => (prev === next ? prev : next));
      });
    };
    update();

    const observer = new ResizeObserver(update);
    observer.observe(host);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [isMobile]);

  useEffect(() => {
    if (isMobile) return;
    const board = boardNaturalRef.current;
    if (!board) return;

    let frame = 0;
    const update = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const next = board.scrollHeight || board.clientHeight || 860;
        setBoardNaturalHeight((prev) =>
          Math.abs(prev - next) < 2 ? prev : next,
        );
      });
    };
    update();

    const observer = new ResizeObserver(update);
    observer.observe(board);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [isMobile]);

  const syncSingleAccount = async (accountId: number, label: string) => {
    try {
      const res = await syncAccount(accountId);
      showToast(`${label}已连接并同步：+${res.inserted}`, "success");
    } catch (error) {
      showToast(
        error instanceof Error
          ? `${label}已连接，但首次同步失败（${error.message}）。可稍后在设置中手动同步。`
          : `${label}已连接，但首次同步失败。可稍后在设置中手动同步。`,
        "warning",
      );
    }
  };

  const showGmailOAuthSetupGuide = (
    popup: Window,
    message: string,
  ): boolean => {
    if (!message.includes("未配置 client_id/client_secret")) return false;
    popup.document.title = "Gmail OAuth 未配置";
    popup.document.body.innerHTML = `
      <div style="font-family:system-ui;padding:20px;line-height:1.65">
        <h3 style="margin:0 0 8px">未完成 Gmail OAuth 配置</h3>
        <p style="margin:0 0 12px">${message}</p>
        <ol style="margin:0 0 12px;padding-left:20px">
          <li>在后端配置：<code>MERCURYDESK_GMAIL_CLIENT_ID</code> 与 <code>MERCURYDESK_GMAIL_CLIENT_SECRET</code></li>
          <li>Google 回调地址：<code>http://127.0.0.1:8000/api/v1/accounts/oauth/gmail/callback</code></li>
          <li>重启后端后再次点击“同意并绑定 Gmail”</li>
        </ol>
        <p style="margin:0;color:#6b7280">建议在 <code>backend</code> 目录启动后端，确保读取到环境变量。</p>
      </div>
    `;
    return true;
  };

  const connectGmailFromPrompt = async () => {
    if (bindingGmail) return;
    setBindingGmail(true);
    const knownIds = new Set(
      (accounts ?? [])
        .filter((item) => item.provider.toLowerCase() === "gmail")
        .map((item) => item.id),
    );
    let allowFallback = false;
    let popup: Window | null = null;
    try {
      popup = openOAuthPopup(
        "oauth-gmail-login-bind",
        "正在跳转到 Google 授权页面…",
      );
      const started = await startAccountOAuth("gmail");
      const allowedOrigin = extractRedirectOriginFromAuthUrl(started.auth_url);
      popup.location.href = started.auth_url;
      allowFallback = true;

      const result = await waitForOAuthPopupMessage(popup, { allowedOrigin });
      if (!result.ok || !result.account_id) {
        throw new Error(result.error || "Gmail 授权失败");
      }
      await syncSingleAccount(result.account_id, "Gmail");
      setGmailPromptOpen(false);
      sessionStorage.removeItem("mercurydesk:gmail-bind-dismissed");
      await Promise.all([
        mutateAccounts(),
        mutateContacts(),
        refreshAgentPanels(),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (popup && !popup.closed && !showGmailOAuthSetupGuide(popup, message))
        popup.close();
      if (allowFallback) {
        const latest = await listAccounts().catch(() => accounts ?? []);
        const fallback = latest
          .filter(
            (item) =>
              item.provider.toLowerCase() === "gmail" && !knownIds.has(item.id),
          )
          .sort((a, b) => b.id - a.id)[0];
        if (fallback) {
          await syncSingleAccount(fallback.id, "Gmail");
          setGmailPromptOpen(false);
          sessionStorage.removeItem("mercurydesk:gmail-bind-dismissed");
          await Promise.all([
            mutateAccounts(),
            mutateContacts(),
            refreshAgentPanels(),
          ]);
          return;
        }
      }
      showToast(`Gmail 绑定失败：${message}`, "error");
    } finally {
      setBindingGmail(false);
    }
  };

  const deferGmailBinding = () => {
    sessionStorage.setItem("mercurydesk:gmail-bind-dismissed", "1");
    setGmailPromptOpen(false);
  };

  const handleCloseFirstRunGuide = useCallback(() => {
    try {
      localStorage.setItem(FIRST_RUN_GUIDE_KEY, "1");
    } catch {
      // ignore
    }
    setFirstRunGuideOpen(false);
  }, []);

  const handleSyncAll = async () => {
    if (syncing) return;
    setSyncing(true);
    setSyncProgress(null);
    try {
      let list = accounts ?? [];
      if (list.length === 0) {
        const mockAccount = await createAccount({
          provider: "mock",
          identifier: "demo",
          access_token: "x",
        });
        list = [mockAccount];
      }

      const total = list.length;
      let completed = 0;
      let nextIndex = 0;
      let inserted = 0;
      const failedAccounts: string[] = [];
      const runningById = new Map<number, string>();
      const maxRetry = 2;

      const updateProgress = () => {
        const runningLabels = Array.from(runningById.values());
        const runningSummary = formatRunningAccounts(runningLabels);
        setSyncProgress({
          current: completed,
          total,
          currentAccount: runningSummary
            ? `并发同步中：${runningSummary}`
            : "完成中...",
          failedAccounts: [...failedAccounts],
        });
      };

      updateProgress();

      const runSyncWorker = async () => {
        while (true) {
          const index = nextIndex;
          nextIndex += 1;
          if (index >= total) return;

          const account = list[index];
          const label = account.identifier || account.provider;
          runningById.set(account.id, label);
          updateProgress();

          let success = false;
          let accountInserted = 0;
          try {
            for (let attempt = 0; attempt <= maxRetry; attempt += 1) {
              try {
                if (attempt > 0) {
                  runningById.set(
                    account.id,
                    `${label}（重试 ${attempt}/${maxRetry}）`,
                  );
                  updateProgress();
                }
                const res = await syncAccount(account.id);
                accountInserted = res.inserted;
                success = true;
                break;
              } catch (error) {
                if (attempt >= maxRetry) throw error;
                await wait(800 * (attempt + 1));
              }
            }
          } catch {
            failedAccounts.push(label);
          } finally {
            if (success) inserted += accountInserted;
            runningById.delete(account.id);
            completed += 1;
            updateProgress();
          }
        }
      };

      const workerCount = Math.min(DASHBOARD_SYNC_CONCURRENCY, total);
      await Promise.all(
        Array.from({ length: workerCount }, () => runSyncWorker()),
      );

      const failed = failedAccounts.length;
      const message =
        failed === 0
          ? `同步完成：+${inserted}`
          : `同步完成：+${inserted}（失败 ${failed} 个：${failedAccounts.join(", ")}）`;
      showToast(message, failed === 0 ? "success" : "error");

      await Promise.all([
        mutateContacts(),
        mutateAccounts(),
        refreshAgentPanels(),
      ]);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "同步失败", "error");
    } finally {
      setSyncing(false);
      setSyncProgress(null);
    }
  };

  const handleCardLayoutChange = useCallback(
    (cards: AgentCardLayoutItem[]) => {
      if (layoutSyncTimerRef.current !== null) {
        window.clearTimeout(layoutSyncTimerRef.current);
      }
      layoutSyncTimerRef.current = window.setTimeout(async () => {
        try {
          await syncAgentCardLayout(cards, activeWorkspace);
        } catch (error) {
          console.error("syncAgentCardLayout failed", error);
        }
      }, 500);
    },
    [activeWorkspace],
  );

  const openContactById = useCallback(
    (contactId?: number | null) => {
      if (!contactId) return;
      const target = contactsById.get(contactId);
      if (!target) {
        showToast(
          "该联系人不在当前筛选结果中，请先清空搜索或刷新。",
          "warning",
        );
        return;
      }
      setSelectedContact(target);
    },
    [contactsById, showToast],
  );

  const replayBridgeFocus = useCallback(() => {
    if (bridgeContext?.focusMessageId) {
      setPendingFocusMessageId(bridgeContext.focusMessageId);
      return;
    }
    if (bridgeContext?.focusContactId) {
      setPendingFocusContactId(bridgeContext.focusContactId);
    }
  }, [bridgeContext]);

  const clearBridgeContext = useCallback(() => {
    setBridgeContext(null);
    setPendingFocusMessageId(null);
    setPendingFocusContactId(null);
    setHighlightContactId(null);
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.removeItem(AELIN_LAST_DESK_BRIDGE_KEY);
      } catch {
        // ignore storage failures
      }
    }
    if (!embedded) {
      navigate("/", { replace: true });
    }
  }, [embedded, navigate]);

  const returnToAelin = useCallback(() => {
    if (embedded) {
      playHandoffFX("Desk -> Aelin", "已返回聊天，可继续追问");
      onRequestClose?.();
      return;
    }
    const fallbackSessionId = (() => {
      try {
        return localStorage.getItem(AELIN_LAST_SESSION_KEY) || "";
      } catch {
        return "";
      }
    })();
    const sid = (bridgeContext?.sessionId || fallbackSessionId || "").trim();
    const focusMessageId = bridgeContext?.focusMessageId || null;
    const focusContactId =
      bridgeContext?.focusContactId || selectedContact?.id || null;
    const highlightSource = (bridgeContext?.highlightSource || "").trim();
    const focusQuery = (bridgeContext?.focusQuery || searchQuery || "").trim();
    const resumePrompt = (
      bridgeContext?.resumePrompt ||
      (focusMessageId
        ? `继续围绕消息 #${focusMessageId} 帮我判断下一步应该关注什么。`
        : "继续我们刚才在 Desk 里的讨论。")
    ).trim();

    const qs = new URLSearchParams();
    qs.set("from", "desk");
    if (sid) qs.set("session_id", sid);
    if (focusMessageId) qs.set("focus_message_id", String(focusMessageId));
    if (focusContactId) qs.set("focus_contact_id", String(focusContactId));
    if (focusQuery) qs.set("focus_query", focusQuery.slice(0, 180));
    if (highlightSource)
      qs.set("highlight_source", highlightSource.slice(0, 40));
    if (resumePrompt) qs.set("resume_prompt", resumePrompt.slice(0, 240));
    const to = `/?${qs.toString()}`;
    playHandoffFX(
      "Desk -> Aelin",
      focusQuery
        ? `带着主题“${focusQuery.slice(0, 36)}”返回聊天`
        : "将观察结果带回聊天",
    );
    window.setTimeout(() => navigate(to), 140);
  }, [
    bridgeContext,
    embedded,
    navigate,
    onRequestClose,
    playHandoffFX,
    searchQuery,
    selectedContact?.id,
  ]);

  const handleCardAction = useCallback(
    async (contact: Contact, action: "summarize" | "draft" | "todo") => {
      const text = [
        `联系人: ${contact.display_name}`,
        `渠道: ${contact.latest_source || "unknown"}`,
        `标题: ${contact.latest_subject || ""}`,
        `内容: ${contact.latest_preview || ""}`,
      ].join("\n");

      try {
        if (action === "summarize") {
          const res = await agentSummarize(text);
          setQuickActionOutput({
            title: `${contact.display_name} - 快速总结`,
            content: res.summary,
          });
          return;
        }
        if (action === "draft") {
          const res = await agentDraftReply(text, "professional");
          setQuickActionOutput({
            title: `${contact.display_name} - 回复草稿`,
            content: res.draft,
          });
          return;
        }
        const todoTitle = `跟进 ${contact.display_name}`;
        await createAgentTodo({
          title: todoTitle,
          detail:
            `${contact.latest_subject || ""}\n${contact.latest_preview || ""}`.trim(),
          priority: "high",
          contact_id: contact.id,
        });
        showToast(`已添加待办: ${todoTitle}`, "success");
        await Promise.all([mutateTodos(), mutateDailyBrief()]);
      } catch (error) {
        showToast(
          error instanceof Error
            ? `卡片 AI 动作失败: ${error.message}`
            : "卡片 AI 动作失败",
          "error",
        );
      }
    },
    [mutateDailyBrief, mutateTodos, showToast],
  );

  const handleToggleTodoDone = useCallback(
    async (todo: AgentTodoItem, done: boolean) => {
      try {
        await updateAgentTodo(todo.id, { done });
        await Promise.all([mutateTodos(), mutateDailyBrief()]);
      } catch (error) {
        showToast(
          error instanceof Error
            ? `更新待办失败: ${error.message}`
            : "更新待办失败",
          "error",
        );
      }
    },
    [mutateDailyBrief, mutateTodos, showToast],
  );

  const handleDeleteTodo = useCallback(
    async (todoId: number) => {
      try {
        await deleteAgentTodo(todoId);
        await Promise.all([mutateTodos(), mutateDailyBrief()]);
      } catch (error) {
        showToast(
          error instanceof Error
            ? `删除待办失败: ${error.message}`
            : "删除待办失败",
          "error",
        );
      }
    },
    [mutateDailyBrief, mutateTodos, showToast],
  );

  const handleCreateManualTodo = useCallback(async () => {
    const title = todoInput.trim();
    if (!title) return;
    setTodoBusy(true);
    try {
      await createAgentTodo({ title, priority: "normal" });
      setTodoInput("");
      await Promise.all([mutateTodos(), mutateDailyBrief()]);
    } catch (error) {
      showToast(
        error instanceof Error
          ? `新增待办失败: ${error.message}`
          : "新增待办失败",
        "error",
      );
    } finally {
      setTodoBusy(false);
    }
  }, [mutateDailyBrief, mutateTodos, showToast, todoInput]);

  const runAdvancedSearch = useCallback(async () => {
    setAdvancedBusy(true);
    try {
      const result = await advancedSearch({
        query: advancedQuery,
        source: advancedSource || undefined,
        unread_only: advancedUnreadOnly,
        days: advancedDays,
        limit: advancedLimit,
      });
      setAdvancedItems(result.items);
    } catch (error) {
      showToast(
        error instanceof Error
          ? `高级检索失败: ${error.message}`
          : "高级检索失败",
        "error",
      );
    } finally {
      setAdvancedBusy(false);
    }
  }, [
    advancedDays,
    advancedLimit,
    advancedQuery,
    advancedSource,
    advancedUnreadOnly,
    showToast,
  ]);

  const handleApplyBriefAction = useCallback(
    async (action: AgentDailyBriefAction) => {
      if (action.contact_id) {
        openContactById(action.contact_id);
        return;
      }
      setActionBusy(true);
      try {
        await createAgentTodo({
          title: action.title,
          detail: action.detail,
          priority: action.priority || "normal",
          message_id: action.message_id ?? undefined,
        });
        showToast("行动项已加入待办", "success");
        await Promise.all([mutateTodos(), mutateDailyBrief()]);
      } catch (error) {
        showToast(
          error instanceof Error
            ? `处理行动项失败: ${error.message}`
            : "处理行动项失败",
          "error",
        );
      } finally {
        setActionBusy(false);
      }
    },
    [mutateDailyBrief, mutateTodos, openContactById, showToast],
  );

  const handleSaveMemoryCorrection = useCallback(async () => {
    const clean = memoryCorrection.trim();
    if (!clean) return;
    setMemoryBusy(true);
    try {
      await addAgentMemoryNote(clean, "preference");
      setMemoryCorrection("");
      await loadMemorySnapshot("");
      showToast("记忆修正已保存", "success");
    } catch (error) {
      setMemoryBusy(false);
      showToast(
        error instanceof Error
          ? `保存记忆失败: ${error.message}`
          : "保存记忆失败",
        "error",
      );
    }
  }, [loadMemorySnapshot, memoryCorrection, showToast]);

  const handleDeleteMemoryNote = useCallback(
    async (noteId: number) => {
      setMemoryBusy(true);
      try {
        await deleteAgentMemoryNote(noteId);
        await loadMemorySnapshot("");
      } catch (error) {
        setMemoryBusy(false);
        showToast(
          error instanceof Error
            ? `删除记忆失败: ${error.message}`
            : "删除记忆失败",
          "error",
        );
      }
    },
    [loadMemorySnapshot, showToast],
  );

  const panelSection = (
    <AgentPanelSection
      activePanel={activePanel}
      setActivePanel={setActivePanel}
      todos={todos ?? []}
      advancedItems={advancedItems}
      memorySnapshot={memorySnapshot}
      dailyBrief={dailyBrief}
      actionBusy={actionBusy}
      onApplyBriefAction={handleApplyBriefAction}
      todoInput={todoInput}
      todoBusy={todoBusy}
      onTodoInputChange={setTodoInput}
      onCreateTodo={handleCreateManualTodo}
      onToggleTodoDone={handleToggleTodoDone}
      onDeleteTodo={handleDeleteTodo}
      onOpenContact={openContactById}
      advancedQuery={advancedQuery}
      advancedSource={advancedSource}
      advancedUnreadOnly={advancedUnreadOnly}
      advancedDays={advancedDays}
      advancedLimit={advancedLimit}
      advancedBusy={advancedBusy}
      onAdvancedQueryChange={setAdvancedQuery}
      onAdvancedSourceChange={setAdvancedSource}
      onAdvancedUnreadOnlyChange={setAdvancedUnreadOnly}
      onAdvancedDaysChange={setAdvancedDays}
      onAdvancedLimitChange={setAdvancedLimit}
      onAdvancedSearch={runAdvancedSearch}
      memoryBusy={memoryBusy}
      memoryCorrection={memoryCorrection}
      onMemoryCorrectionChange={setMemoryCorrection}
      onRefreshMemory={() => loadMemorySnapshot("")}
      onSaveMemoryCorrection={handleSaveMemoryCorrection}
      onDeleteMemoryNote={handleDeleteMemoryNote}
    />
  );
  const hasDesktopMeasure = desktopHostWidth > 0;
  const desktopSidebarBaseWidth = compactMode ? 332 : DESKTOP_SIDEBAR_WIDTH;
  const desktopSidebarWidth =
    !isMobile && desktopSidebarOpen ? desktopSidebarBaseWidth : 0;
  const desktopGap = !isMobile && desktopSidebarOpen ? DESKTOP_SIDEBAR_GAP : 0;
  const desktopReservedWidth = desktopSidebarWidth + desktopGap;
  const boardBaseWidth = hasDesktopMeasure ? desktopHostWidth : 1;
  const boardAvailableWidth = hasDesktopMeasure
    ? Math.max(1, desktopHostWidth - desktopReservedWidth)
    : 1;
  const boardScale =
    !isMobile && desktopSidebarOpen && hasDesktopMeasure
      ? Math.max(0.62, Math.min(1, boardAvailableWidth / boardBaseWidth))
      : 1;
  const boardScaledHeight = hasDesktopMeasure
    ? Math.max(
        compactMode ? 520 : 600,
        Math.round(boardNaturalHeight * boardScale),
      )
    : "auto";
  const boardTransition = prefersReducedMotion
    ? "none"
    : "transform 240ms cubic-bezier(0.22, 0.61, 0.36, 1)";
  const sidebarTransition = prefersReducedMotion
    ? "none"
    : "transform 240ms cubic-bezier(0.22, 0.61, 0.36, 1), opacity 180ms ease";
  const panelToggleOpen = isMobile ? mobilePanelOpen : desktopSidebarOpen;

  return (
    <Box
      component={motion.div}
      initial={embedded ? undefined : { opacity: 0, y: 10 }}
      animate={embedded ? undefined : { opacity: 1, y: 0 }}
      exit={embedded ? undefined : { opacity: 0, y: -10 }}
      transition={embedded ? undefined : { duration: 0.4 }}
      sx={{
        minHeight: embedded ? "100%" : "100vh",
        bgcolor: "transparent",
        pb: embedded ? 2 : 8,
      }}
    >
      {!embedded ? (
        <TopBar
          onRefresh={handleSyncAll}
          onSearch={setSearchQuery}
          loading={syncing}
        />
      ) : null}

      {embedded ? (
        <Box
          sx={{
            position: "sticky",
            top: 0,
            zIndex: 8,
            px: { xs: 0.8, md: 1.1 },
            pt: 0.8,
          }}
        >
          <Paper
            variant="outlined"
            sx={{
              px: 1.1,
              py: 0.9,
              borderRadius: 2.2,
              borderColor: alpha(theme.palette.primary.main, 0.22),
              bgcolor: alpha(theme.palette.background.paper, 0.9),
              backdropFilter: "blur(8px)",
              boxShadow:
                theme.palette.mode === "light"
                  ? "0 6px 14px rgba(20,20,19,0.05)"
                  : "0 8px 18px rgba(0,0,0,0.24)",
            }}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 0.9,
                flexWrap: "wrap",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.6 }}>
                <Typography
                  variant="subtitle2"
                  sx={{ fontWeight: 800, lineHeight: 1.2 }}
                >
                  Desk
                </Typography>
                <Chip
                  size="small"
                  variant="outlined"
                  color="primary"
                  label={
                    WORKSPACES.find((w) => w.key === activeWorkspace)?.label ||
                    "主工作区"
                  }
                />
                {bridgeContext?.focusQuery ? (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`主题: ${bridgeContext.focusQuery.slice(0, 22)}`}
                  />
                ) : null}
              </Box>
              <Button
                size="small"
                variant="contained"
                startIcon={<KeyboardReturnIcon />}
                onClick={returnToAelin}
              >
                回到聊天
              </Button>
            </Box>
          </Paper>
        </Box>
      ) : null}

      <Container
        maxWidth="xl"
        sx={{ mt: embedded ? { xs: 0.8, md: 1.2 } : { xs: 2.2, md: 3.2 } }}
      >
        {bridgeContext?.fromAelin && !embedded ? (
          <Paper
            variant="outlined"
            sx={{
              mb: 1.3,
              px: { xs: 1.1, md: 1.4 },
              py: 0.85,
              borderRadius: 2.2,
              borderColor: alpha(theme.palette.primary.main, 0.36),
              bgcolor: alpha(theme.palette.primary.main, 0.07),
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: 0.8,
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              来自 Aelin 的上下文已加载
            </Typography>
            <Chip
              size="small"
              color="primary"
              variant="filled"
              label="观察模式"
              sx={{ "& .MuiChip-label": { fontWeight: 700 } }}
            />
            {bridgeContext.highlightSource ? (
              <Chip size="small" label={bridgeContext.highlightSource} />
            ) : null}
            {bridgeContext.focusMessageId ? (
              <Chip
                size="small"
                variant="outlined"
                label={`消息 #${bridgeContext.focusMessageId}`}
              />
            ) : null}
            {bridgeContext.workspace ? (
              <Chip
                size="small"
                variant="outlined"
                label={`工作区 ${bridgeContext.workspace}`}
              />
            ) : null}
            {bridgeContext.focusQuery ? (
              <Chip
                size="small"
                variant="outlined"
                label={`检索: ${bridgeContext.focusQuery}`}
              />
            ) : null}
            <Box sx={{ flex: 1 }} />
            {bridgeContext.focusMessageId || bridgeContext.focusContactId ? (
              <Button
                size="small"
                variant="outlined"
                startIcon={<LaunchIcon />}
                onClick={replayBridgeFocus}
              >
                重新定位焦点
              </Button>
            ) : null}
            {!embedded ? (
              <Button
                size="small"
                variant="contained"
                startIcon={<KeyboardReturnIcon />}
                onClick={returnToAelin}
              >
                回到 Aelin 续聊
              </Button>
            ) : null}
            <Button size="small" color="inherit" onClick={clearBridgeContext}>
              退出观察模式
            </Button>
          </Paper>
        ) : null}

        {isMobile ? (
          <DeskBoardSurface
            workspaces={WORKSPACES}
            activeWorkspace={activeWorkspace}
            onSelectWorkspace={setActiveWorkspace}
            onRefreshAgentPanels={refreshAgentPanels}
            syncProgress={syncProgress}
            contacts={contacts}
            onContactClick={setSelectedContact}
            onCardLayoutChange={handleCardLayoutChange}
            workspace={activeWorkspace}
            pinRecommendations={pinRecommendations?.items ?? []}
            onCardAction={handleCardAction}
            highlightContactId={highlightContactId}
          />
        ) : (
          <Box
            ref={desktopHostRef}
            sx={{
              position: "relative",
              contain: "layout paint",
              minHeight: boardScaledHeight,
              overflow: "clip",
            }}
          >
            <Box
              sx={{
                height: boardScaledHeight,
              }}
            >
              <Box
                ref={boardNaturalRef}
                sx={{
                  width: hasDesktopMeasure ? boardBaseWidth : "100%",
                  transform: `translate3d(0, 0, 0) scale(${boardScale})`,
                  transformOrigin: "top left",
                  transition: boardTransition,
                  willChange: "transform",
                  backfaceVisibility: "hidden",
                }}
              >
                <DeskBoardSurface
                  workspaces={WORKSPACES}
                  activeWorkspace={activeWorkspace}
                  onSelectWorkspace={setActiveWorkspace}
                  onRefreshAgentPanels={refreshAgentPanels}
                  syncProgress={syncProgress}
                  contacts={contacts}
                  onContactClick={setSelectedContact}
                  onCardLayoutChange={handleCardLayoutChange}
                  workspace={activeWorkspace}
                  pinRecommendations={pinRecommendations?.items ?? []}
                  onCardAction={handleCardAction}
                  highlightContactId={highlightContactId}
                />
                `n{" "}
              </Box>
            </Box>

            <Box
              sx={{
                position: "absolute",
                right: 0,
                top: 0,
                width: desktopSidebarBaseWidth,
                opacity: desktopSidebarOpen ? 1 : 0,
                pointerEvents: desktopSidebarOpen ? "auto" : "none",
                transform: desktopSidebarOpen
                  ? "translate3d(0, 0, 0)"
                  : "translate3d(calc(100% + 8px), 0, 0)",
                transition: sidebarTransition,
                willChange: "transform, opacity",
                contain: "layout paint",
              }}
            >
              <Paper
                sx={{
                  p: 0.5,
                  maxHeight: "calc(100vh - 96px)",
                  overflowY: "auto",
                  borderRadius: 3,
                  boxShadow:
                    theme.palette.mode === "light"
                      ? "0 8px 18px rgba(20,20,19,0.08)"
                      : "0 10px 22px rgba(0,0,0,0.24)",
                }}
              >
                {panelSection}
              </Paper>
            </Box>
          </Box>
        )}
      </Container>

      <DashboardHandoffBanner handoffFX={handoffFX} />

      {!embedded ? (
        <Tooltip
          title={
            isMobile
              ? mobilePanelOpen
                ? "收起 AI 面板"
                : "展开 AI 面板"
              : desktopSidebarOpen
                ? "收起 AI 右边栏"
                : "展开 AI 右边栏"
          }
        >
          <Button
            size="small"
            variant={panelToggleOpen ? "contained" : "outlined"}
            aria-label={
              isMobile
                ? mobilePanelOpen
                  ? "收起 AI 面板"
                  : "展开 AI 面板"
                : desktopSidebarOpen
                  ? "收起 AI 右边栏"
                  : "展开 AI 右边栏"
            }
            onClick={() => {
              if (isMobile) {
                setMobilePanelOpen((prev) => !prev);
                return;
              }
              setDesktopSidebarOpen((prev) => !prev);
            }}
            sx={{
              position: "fixed",
              right: { xs: 10, lg: 12 },
              top: { xs: "auto", lg: "50%" },
              bottom: { xs: 88, lg: "auto" },
              transform: { xs: "none", lg: "translateY(-50%)" },
              zIndex: 1320,
              minWidth: 0,
              width: 44,
              height: 44,
              px: 0,
              borderRadius: 999,
              boxShadow: "0 6px 16px rgba(0,0,0,0.14)",
              transition: prefersReducedMotion
                ? "none"
                : "transform 200ms ease, box-shadow 200ms ease",
              "&:hover": {
                transform: {
                  xs: "none",
                  lg: "translateY(-50%) translateX(-1px)",
                },
              },
            }}
          >
            {panelToggleOpen ? (
              <ChevronRightIcon />
            ) : (
              <Box
                component="img"
                src="/logo.png"
                alt="Aelin"
                sx={{
                  width: 22,
                  height: 22,
                  objectFit: "cover",
                  objectPosition: "center 24%",
                }}
              />
            )}
          </Button>
        </Tooltip>
      ) : null}

      {!embedded &&
      bridgeContext &&
      (bridgeContext.fromAelin || Boolean(bridgeContext.sessionId)) ? (
        <Tooltip title="回到 Aelin 并继续当前主题">
          <Button
            size="small"
            variant="outlined"
            onClick={returnToAelin}
            sx={{
              position: "fixed",
              right: { xs: 10, lg: 66 },
              top: { xs: "auto", lg: "50%" },
              bottom: { xs: 140, lg: "auto" },
              transform: { xs: "none", lg: "translateY(-50%)" },
              zIndex: 1320,
              minWidth: 0,
              width: 44,
              height: 44,
              px: 0,
              borderRadius: 999,
              borderColor: alpha(theme.palette.primary.main, 0.55),
              bgcolor: alpha(theme.palette.background.paper, 0.9),
              boxShadow: "0 6px 16px rgba(0,0,0,0.14)",
            }}
          >
            <KeyboardReturnIcon fontSize="small" />
          </Button>
        </Tooltip>
      ) : null}

      <Drawer
        anchor="right"
        open={mobilePanelOpen}
        onClose={() => setMobilePanelOpen(false)}
        PaperProps={{ sx: { width: "min(94vw, 420px)", p: 0.4 } }}
      >
        {panelSection}
      </Drawer>

      <ConversationDrawer
        open={!!selectedContact}
        contact={drawerContact}
        focusMessageId={bridgeContext?.focusMessageId ?? null}
        onClose={() => {
          setSelectedContact(null);
          mutateContacts();
        }}
      />

      <GmailBindDialog
        open={gmailPromptOpen}
        binding={bindingGmail}
        onClose={deferGmailBinding}
        onConfirm={connectGmailFromPrompt}
      />

      <FirstRunGuideDialog
        open={firstRunGuideOpen}
        hasAccounts={!!accounts?.length}
        syncing={syncing}
        onClose={handleCloseFirstRunGuide}
        onOpenSettings={() => {
          handleCloseFirstRunGuide();
          navigate("/settings");
        }}
        onSync={handleSyncAll}
      />

      <Dialog
        open={!!quickActionOutput}
        fullWidth
        maxWidth="md"
        onClose={() => setQuickActionOutput(null)}
      >
        <DialogTitle>{quickActionOutput?.title || "AI 输出"}</DialogTitle>
        <DialogContent dividers>
          <Typography
            component="pre"
            sx={{ whiteSpace: "pre-wrap", m: 0, fontFamily: "inherit" }}
          >
            {quickActionOutput?.content || ""}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setQuickActionOutput(null)}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
