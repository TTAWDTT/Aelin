import React from "react";

import {
  ackAelinTrackingChange,
  type AelinTrackingChangeItem,
  type AelinTrackingFileMemoryItem,
  type AelinTrackingItem,
  type AelinTrackingSnapshotItem,
  getAelinTracking,
  listAelinTrackingChanges,
  listAelinTrackingFileMemory,
  listAelinTrackingSnapshots,
  runAelinTrackingTarget,
  updateAelinTrackingTarget,
} from "../../../api";
import type { TrackingAckFilter } from "../types";

type ToastLevel = "success" | "error" | "warning" | "info";

type UseAelinTrackingCenterArgs = {
  workspaceScope: string;
  showToast: (message: string, level?: ToastLevel) => void;
};

export type UseAelinTrackingCenterResult = {
  trackingDialogOpen: boolean;
  setTrackingDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  trackingItems: AelinTrackingItem[];
  trackingBusy: boolean;
  trackingError: string;
  trackingStatusFilter: string;
  setTrackingStatusFilter: React.Dispatch<React.SetStateAction<string>>;
  trackingSourceFilter: string;
  setTrackingSourceFilter: React.Dispatch<React.SetStateAction<string>>;
  trackingKeyword: string;
  setTrackingKeyword: React.Dispatch<React.SetStateAction<string>>;
  trackingActiveTargetId: number | null;
  setTrackingActiveTargetId: React.Dispatch<
    React.SetStateAction<number | null>
  >;
  trackingChanges: AelinTrackingChangeItem[];
  trackingSnapshots: AelinTrackingSnapshotItem[];
  trackingFileMemory: AelinTrackingFileMemoryItem[];
  trackingDetailBusy: boolean;
  trackingDetailError: string;
  trackingMutationBusy: number | null;
  trackingAckBusy: number | null;
  trackingChangeSeverityFilter: string;
  setTrackingChangeSeverityFilter: React.Dispatch<React.SetStateAction<string>>;
  trackingChangeTypeFilter: string;
  setTrackingChangeTypeFilter: React.Dispatch<React.SetStateAction<string>>;
  trackingAckFilter: TrackingAckFilter;
  setTrackingAckFilter: React.Dispatch<React.SetStateAction<TrackingAckFilter>>;
  filteredTrackingItems: AelinTrackingItem[];
  trackingUnreadCount: number;
  activeTrackingItem: AelinTrackingItem | null;
  refreshTracking: () => Promise<void>;
  refreshTrackingDetail: (
    targetId: number,
    options?: { silent?: boolean },
  ) => Promise<void>;
  patchTrackingTarget: (
    targetId: number,
    payload: {
      status?: "active" | "paused" | "error" | "deleted";
      interval_seconds?: number;
      notify_level?: "all" | "important" | "critical";
      mute_until?: string | null;
      description?: string;
      tags?: string[];
    },
    successMessage: string,
  ) => Promise<void>;
  runTrackingTargetNow: (targetId: number) => Promise<void>;
  ackTrackingChange: (changeId: number) => Promise<void>;
};

export function useAelinTrackingCenter({
  workspaceScope,
  showToast,
}: UseAelinTrackingCenterArgs): UseAelinTrackingCenterResult {
  const [trackingDialogOpen, setTrackingDialogOpen] = React.useState(false);
  const [trackingItems, setTrackingItems] = React.useState<AelinTrackingItem[]>(
    [],
  );
  const [trackingBusy, setTrackingBusy] = React.useState(false);
  const [trackingError, setTrackingError] = React.useState("");
  const [trackingStatusFilter, setTrackingStatusFilter] = React.useState("all");
  const [trackingSourceFilter, setTrackingSourceFilter] = React.useState("all");
  const [trackingKeyword, setTrackingKeyword] = React.useState("");
  const [trackingActiveTargetId, setTrackingActiveTargetId] = React.useState<
    number | null
  >(null);
  const [trackingChanges, setTrackingChanges] = React.useState<
    AelinTrackingChangeItem[]
  >([]);
  const [trackingSnapshots, setTrackingSnapshots] = React.useState<
    AelinTrackingSnapshotItem[]
  >([]);
  const [trackingFileMemory, setTrackingFileMemory] = React.useState<
    AelinTrackingFileMemoryItem[]
  >([]);
  const [trackingDetailBusy, setTrackingDetailBusy] = React.useState(false);
  const [trackingDetailError, setTrackingDetailError] = React.useState("");
  const [trackingMutationBusy, setTrackingMutationBusy] = React.useState<
    number | null
  >(null);
  const [trackingAckBusy, setTrackingAckBusy] = React.useState<number | null>(
    null,
  );
  const [trackingChangeSeverityFilter, setTrackingChangeSeverityFilter] =
    React.useState("all");
  const [trackingChangeTypeFilter, setTrackingChangeTypeFilter] =
    React.useState("all");
  const [trackingAckFilter, setTrackingAckFilter] =
    React.useState<TrackingAckFilter>("unacked");

  const filteredTrackingItems = React.useMemo(() => {
    const kw = trackingKeyword.trim().toLowerCase();
    return trackingItems.filter((item) => {
      if (
        trackingStatusFilter !== "all" &&
        String(item.status || "").toLowerCase() !== trackingStatusFilter
      )
        return false;
      if (
        trackingSourceFilter !== "all" &&
        String(item.source || "").toLowerCase() !== trackingSourceFilter
      )
        return false;
      if (!kw) return true;
      const blob =
        `${item.target} ${item.query} ${item.source} ${item.status}`.toLowerCase();
      return blob.includes(kw);
    });
  }, [
    trackingItems,
    trackingStatusFilter,
    trackingSourceFilter,
    trackingKeyword,
  ]);

  const trackingUnreadCount = React.useMemo(
    () =>
      trackingItems.reduce(
        (sum, item) => sum + Math.max(0, Number(item.unread_changes || 0)),
        0,
      ),
    [trackingItems],
  );

  const activeTrackingItem = React.useMemo(() => {
    if (!trackingItems.length) return null;
    if (trackingActiveTargetId !== null) {
      const matched = trackingItems.find(
        (item) => Number(item.target_id || 0) === trackingActiveTargetId,
      );
      if (matched) return matched;
    }
    return trackingItems[0] || null;
  }, [trackingActiveTargetId, trackingItems]);

  const refreshTracking = React.useCallback(async () => {
    setTrackingBusy(true);
    setTrackingError("");
    try {
      const ret = await getAelinTracking({
        limit: 120,
        workspace: workspaceScope,
        status:
          trackingStatusFilter !== "all" ? trackingStatusFilter : undefined,
      });
      const items = ret.items || [];
      setTrackingItems(items);
      setTrackingActiveTargetId((prev) => {
        if (
          prev !== null &&
          items.some((item) => Number(item.target_id || 0) === prev)
        )
          return prev;
        const first = items.find((item) => Number(item.target_id || 0) > 0);
        return first ? Number(first.target_id || 0) : null;
      });
    } catch (error) {
      setTrackingError(
        error instanceof Error ? error.message : "跟踪列表加载失败",
      );
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
        const acked =
          trackingAckFilter === "all"
            ? undefined
            : trackingAckFilter === "acked";
        const targetMeta =
          trackingItems.find(
            (item) => Number(item.target_id || 0) === safeTargetId,
          ) || null;
        const memoryQuery = String(
          targetMeta?.query || targetMeta?.target || "",
        ).trim();
        const [changesRet, snapshotsRet, fileMemoryRet] = await Promise.all([
          listAelinTrackingChanges(safeTargetId, {
            limit: 120,
            severity:
              trackingChangeSeverityFilter !== "all"
                ? trackingChangeSeverityFilter
                : undefined,
            change_type:
              trackingChangeTypeFilter !== "all"
                ? trackingChangeTypeFilter
                : undefined,
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
        setTrackingDetailError(
          error instanceof Error ? error.message : "追踪详情加载失败",
        );
        setTrackingFileMemory([]);
      } finally {
        if (!options?.silent) {
          setTrackingDetailBusy(false);
        }
      }
    },
    [
      trackingAckFilter,
      trackingChangeSeverityFilter,
      trackingChangeTypeFilter,
      trackingItems,
      workspaceScope,
    ],
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
      successMessage: string,
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
        showToast(
          error instanceof Error ? error.message : "追踪项更新失败",
          "error",
        );
      } finally {
        setTrackingMutationBusy(null);
      }
    },
    [refreshTracking, refreshTrackingDetail, showToast],
  );

  const runTrackingTargetNow = React.useCallback(
    async (targetId: number) => {
      const safeTargetId = Number(targetId || 0);
      if (!safeTargetId) return;
      setTrackingMutationBusy(safeTargetId);
      try {
        const ret = await runAelinTrackingTarget(safeTargetId);
        showToast(
          ret.message || "已触发立即执行",
          ret.ok ? "success" : "warning",
        );
        await refreshTracking();
        await refreshTrackingDetail(safeTargetId, { silent: true });
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "手动执行失败",
          "error",
        );
      } finally {
        setTrackingMutationBusy(null);
      }
    },
    [refreshTracking, refreshTrackingDetail, showToast],
  );

  const ackTrackingChange = React.useCallback(
    async (changeId: number) => {
      const safeChangeId = Number(changeId || 0);
      const targetId = Number(activeTrackingItem?.target_id || 0);
      if (!safeChangeId || !targetId) return;
      setTrackingAckBusy(safeChangeId);
      try {
        await ackAelinTrackingChange(safeChangeId);
        await Promise.all([
          refreshTracking(),
          refreshTrackingDetail(targetId, { silent: true }),
        ]);
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "标记已读失败",
          "error",
        );
      } finally {
        setTrackingAckBusy(null);
      }
    },
    [
      activeTrackingItem?.target_id,
      refreshTracking,
      refreshTrackingDetail,
      showToast,
    ],
  );

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
    if (
      trackingActiveTargetId === null ||
      !trackingItems.some(
        (item) => Number(item.target_id || 0) === trackingActiveTargetId,
      )
    ) {
      const first = trackingItems.find(
        (item) => Number(item.target_id || 0) > 0,
      );
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
  }, [
    activeTrackingItem?.target_id,
    refreshTrackingDetail,
    trackingDialogOpen,
  ]);

  return {
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
  };
}
