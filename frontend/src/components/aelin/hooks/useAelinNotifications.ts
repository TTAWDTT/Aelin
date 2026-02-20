import React from "react";

import {
  type AelinNotificationItem,
  getAelinNotifications,
  getAelinProactivePoll,
} from "../../../api";
import { AELIN_LOGO_SRC, PROACTIVE_POLL_MS } from "../constants";

type ToastLevel = "success" | "error" | "warning" | "info";

type UseAelinNotificationsArgs = {
  workspaceScope: string;
  contextNotifications: AelinNotificationItem[];
  showToast: (message: string, level?: ToastLevel) => void;
};

export type UseAelinNotificationsResult = {
  notificationDialogOpen: boolean;
  setNotificationDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  notificationBusy: boolean;
  allNotifications: AelinNotificationItem[];
  unreadNotificationCount: number;
  refreshNotifications: () => Promise<void>;
};

export function useAelinNotifications({
  workspaceScope,
  contextNotifications,
  showToast,
}: UseAelinNotificationsArgs): UseAelinNotificationsResult {
  const [notificationDialogOpen, setNotificationDialogOpen] =
    React.useState(false);
  const [notificationBusy, setNotificationBusy] = React.useState(false);
  const [notificationItems, setNotificationItems] = React.useState<
    AelinNotificationItem[]
  >([]);
  const proactiveSeenRef = React.useRef<Record<string, true>>({});

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
        const toastText = detail ? `${item.title} · ${detail}` : item.title;
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

  return {
    notificationDialogOpen,
    setNotificationDialogOpen,
    notificationBusy,
    allNotifications,
    unreadNotificationCount,
    refreshNotifications,
  };
}
