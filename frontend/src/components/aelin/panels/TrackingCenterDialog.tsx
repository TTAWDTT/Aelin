import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import RefreshIcon from "@mui/icons-material/Refresh";
import TrackChangesIcon from "@mui/icons-material/TrackChanges";
import { alpha, useTheme } from "@mui/material/styles";

import type {
  AelinTrackingChangeItem,
  AelinTrackingFileMemoryItem,
  AelinTrackingItem,
  AelinTrackingSnapshotItem,
} from "../../../api";
import { TRACKING_SOURCE_LABEL } from "../constants";
import { formatIsoTime, formatTrackingStatus } from "../helpers";
import { TRACKING_CHANGE_TYPE_LABEL, TRACKING_SEVERITY_META } from "../trackingMeta";
import type { TrackingAckFilter } from "../types";

type AelinTrackingCenterDialogProps = {
  trackingDialogOpen: boolean;
  setTrackingDialogOpen: (open: boolean) => void;
  refreshTracking: () => Promise<void> | void;
  activeTrackingItem: AelinTrackingItem | null;
  refreshTrackingDetail: (targetId: number, options?: { silent?: boolean }) => Promise<void> | void;
  trackingBusy: boolean;
  trackingItems: AelinTrackingItem[];
  trackingUnreadCount: number;
  trackingKeyword: string;
  setTrackingKeyword: (value: string) => void;
  trackingStatusFilter: string;
  setTrackingStatusFilter: (value: string) => void;
  trackingSourceFilter: string;
  setTrackingSourceFilter: (value: string) => void;
  filteredTrackingItems: AelinTrackingItem[];
  trackingError: string;
  trackingActiveTargetId: number | null;
  setTrackingActiveTargetId: (value: number | null) => void;
  patchTrackingTarget: (targetId: number, payload: { status?: "active" | "paused" | "error" | "deleted"; interval_seconds?: number; notify_level?: "all" | "important" | "critical"; mute_until?: string | null; description?: string; tags?: string[]; }, successMessage: string) => Promise<void> | void;
  trackingMutationBusy: number | null;
  runTrackingTargetNow: (targetId: number) => Promise<void> | void;
  workspaceScope: string;
  trackingChangeSeverityFilter: string;
  setTrackingChangeSeverityFilter: (value: string) => void;
  trackingChangeTypeFilter: string;
  setTrackingChangeTypeFilter: (value: string) => void;
  trackingAckFilter: TrackingAckFilter;
  setTrackingAckFilter: (value: TrackingAckFilter) => void;
  trackingDetailBusy: boolean;
  trackingDetailError: string;
  trackingChanges: AelinTrackingChangeItem[];
  trackingAckBusy: number | null;
  ackTrackingChange: (changeId: number) => Promise<void> | void;
  trackingSnapshots: AelinTrackingSnapshotItem[];
  trackingFileMemory: AelinTrackingFileMemoryItem[];
  copyText: (text: string) => Promise<void> | void;
};

export function AelinTrackingCenterDialog(props: AelinTrackingCenterDialogProps) {
  const theme = useTheme();
  const {
    trackingDialogOpen,
    setTrackingDialogOpen,
    refreshTracking,
    activeTrackingItem,
    refreshTrackingDetail,
    trackingBusy,
    trackingItems,
    trackingUnreadCount,
    trackingKeyword,
    setTrackingKeyword,
    trackingStatusFilter,
    setTrackingStatusFilter,
    trackingSourceFilter,
    setTrackingSourceFilter,
    filteredTrackingItems,
    trackingError,
    trackingActiveTargetId,
    setTrackingActiveTargetId,
    patchTrackingTarget,
    trackingMutationBusy,
    runTrackingTargetNow,
    workspaceScope,
    trackingChangeSeverityFilter,
    setTrackingChangeSeverityFilter,
    trackingChangeTypeFilter,
    setTrackingChangeTypeFilter,
    trackingAckFilter,
    setTrackingAckFilter,
    trackingDetailBusy,
    trackingDetailError,
    trackingChanges,
    trackingAckBusy,
    ackTrackingChange,
    trackingSnapshots,
    trackingFileMemory,
    copyText,
  } = props;

  return (<Dialog
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
  );
}
