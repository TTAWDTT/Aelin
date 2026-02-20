import React from "react";

import {
  applyAelinDeviceMode,
  type AelinDeviceCapabilitiesResponse,
  type AelinDeviceModeApplyResponse,
  type AelinDeviceOptimizeResponse,
  type AelinDeviceProcessItem,
  getAelinDeviceCapabilities,
  getAelinDeviceMode,
  getAelinDeviceProcesses,
  optimizeAelinDeviceProcesses,
  runAelinDeviceProcessAction,
} from "../../../api";
import type { DeviceMode, DeviceSortBy } from "../constants";

type ToastLevel = "success" | "error" | "warning" | "info";

type UseAelinDeviceCenterArgs = {
  showToast: (message: string, level?: ToastLevel) => void;
};

export type UseAelinDeviceCenterResult = {
  deviceDialogOpen: boolean;
  setDeviceDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  deviceBusy: boolean;
  deviceSortBy: DeviceSortBy;
  setDeviceSortBy: React.Dispatch<React.SetStateAction<DeviceSortBy>>;
  deviceProcesses: AelinDeviceProcessItem[];
  deviceCapabilities: AelinDeviceCapabilitiesResponse | null;
  deviceModeState: AelinDeviceModeApplyResponse | null;
  deviceActionBusyPid: number | null;
  deviceModeApplying: DeviceMode | null;
  deviceOptimizeBusy: boolean;
  deviceOptimizeResult: AelinDeviceOptimizeResponse | null;
  refreshDeviceMode: () => Promise<void>;
  refreshDeviceCapabilities: () => Promise<void>;
  refreshDeviceProcesses: () => Promise<void>;
  openDeviceDialog: () => void;
  applyDeviceModeAction: (mode: DeviceMode) => Promise<void>;
  handleDeviceProcessAction: (
    pid: number,
    action: "terminate" | "set_low_priority" | "set_high_priority",
  ) => Promise<void>;
  runDeviceOptimize: () => Promise<void>;
};

export function useAelinDeviceCenter({
  showToast,
}: UseAelinDeviceCenterArgs): UseAelinDeviceCenterResult {
  const [deviceDialogOpen, setDeviceDialogOpen] = React.useState(false);
  const [deviceBusy, setDeviceBusy] = React.useState(false);
  const [deviceSortBy, setDeviceSortBy] = React.useState<DeviceSortBy>("cpu");
  const [deviceProcesses, setDeviceProcesses] = React.useState<
    AelinDeviceProcessItem[]
  >([]);
  const [deviceCapabilities, setDeviceCapabilities] =
    React.useState<AelinDeviceCapabilitiesResponse | null>(null);
  const [deviceModeState, setDeviceModeState] =
    React.useState<AelinDeviceModeApplyResponse | null>(null);
  const [deviceActionBusyPid, setDeviceActionBusyPid] = React.useState<
    number | null
  >(null);
  const [deviceModeApplying, setDeviceModeApplying] =
    React.useState<DeviceMode | null>(null);
  const [deviceOptimizeBusy, setDeviceOptimizeBusy] = React.useState(false);
  const [deviceOptimizeResult, setDeviceOptimizeResult] =
    React.useState<AelinDeviceOptimizeResponse | null>(null);

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
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : "读取进程失败",
        "error",
      );
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
          warningText
            ? `${ret.summary || `模式已切换 ${mode}`} · ${warningText}`
            : ret.summary || `模式已切换 ${mode}`,
          severity,
        );
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "模式切换失败",
          "error",
        );
      } finally {
        setDeviceModeApplying(null);
      }
    },
    [showToast],
  );

  const handleDeviceProcessAction = React.useCallback(
    async (
      pid: number,
      action: "terminate" | "set_low_priority" | "set_high_priority",
    ) => {
      setDeviceActionBusyPid(pid);
      try {
        const ret = await runAelinDeviceProcessAction(pid, action);
        showToast(
          ret.ok
            ? `已执行：${ret.detail || action}`
            : `执行失败：${ret.detail || action}`,
          ret.ok ? "success" : "error",
        );
        await refreshDeviceProcesses();
      } catch (error) {
        showToast(
          error instanceof Error ? error.message : "进程操作失败",
          "error",
        );
      } finally {
        setDeviceActionBusyPid(null);
      }
    },
    [refreshDeviceProcesses, showToast],
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
        ret.optimized_count > 0 ? "success" : "info",
      );
      await refreshDeviceProcesses();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "优化失败", "error");
    } finally {
      setDeviceOptimizeBusy(false);
    }
  }, [refreshDeviceProcesses, showToast]);

  React.useEffect(() => {
    if (!deviceDialogOpen) return;
    void refreshDeviceProcesses();
  }, [deviceDialogOpen, refreshDeviceProcesses]);

  React.useEffect(() => {
    if (!deviceDialogOpen) return;
    void refreshDeviceMode();
  }, [deviceDialogOpen, refreshDeviceMode]);

  return {
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
    refreshDeviceMode,
    refreshDeviceCapabilities,
    refreshDeviceProcesses,
    openDeviceDialog,
    applyDeviceModeAction,
    handleDeviceProcessAction,
    runDeviceOptimize,
  };
}
