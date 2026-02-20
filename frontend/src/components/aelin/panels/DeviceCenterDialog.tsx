import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ComputerIcon from "@mui/icons-material/Computer";
import MemoryIcon from "@mui/icons-material/Memory";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import RefreshIcon from "@mui/icons-material/Refresh";
import SpeedIcon from "@mui/icons-material/Speed";
import { alpha, useTheme } from "@mui/material/styles";

import type {
  AelinDeviceCapabilitiesResponse,
  AelinDeviceModeApplyResponse,
  AelinDeviceOptimizeResponse,
  AelinDeviceProcessItem,
} from "../../../api";
import {
  DEVICE_MODE_META,
  type DeviceMode,
  type DeviceSortBy,
} from "../constants";
import { formatIsoTime } from "../helpers";

type AelinDeviceCenterDialogProps = {
  deviceDialogOpen: boolean;
  setDeviceDialogOpen: (open: boolean) => void;
  refreshDeviceProcesses: () => Promise<void> | void;
  deviceBusy: boolean;
  deviceCapabilities: AelinDeviceCapabilitiesResponse | null;
  deviceModeState: AelinDeviceModeApplyResponse | null;
  deviceModeApplying: DeviceMode | null;
  applyDeviceModeAction: (mode: DeviceMode) => Promise<void> | void;
  deviceSortBy: DeviceSortBy;
  setDeviceSortBy: (sort: DeviceSortBy) => void;
  runDeviceOptimize: () => Promise<void> | void;
  deviceOptimizeBusy: boolean;
  deviceOptimizeResult: AelinDeviceOptimizeResponse | null;
  deviceProcesses: AelinDeviceProcessItem[];
  deviceActionBusyPid: number | null;
  handleDeviceProcessAction: (pid: number, action: "terminate" | "set_low_priority" | "set_high_priority") => Promise<void> | void;
};

export function AelinDeviceCenterDialog(props: AelinDeviceCenterDialogProps) {
  const theme = useTheme();
  const {
    deviceDialogOpen,
    setDeviceDialogOpen,
    refreshDeviceProcesses,
    deviceBusy,
    deviceCapabilities,
    deviceModeState,
    deviceModeApplying,
    applyDeviceModeAction,
    deviceSortBy,
    setDeviceSortBy,
    runDeviceOptimize,
    deviceOptimizeBusy,
    deviceOptimizeResult,
    deviceProcesses,
    deviceActionBusyPid,
    handleDeviceProcessAction,
  } = props;

  return (<Dialog
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
  );
}
