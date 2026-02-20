export const TRACKING_CHANGE_TYPE_LABEL: Record<string, string> = {
  new_item: "新增",
  updated_item: "更新",
  removed_item: "移除",
  metric_spike: "波动",
  fetch_error: "抓取失败",
  status_change: "状态变更",
  recovered: "恢复",
};

export const TRACKING_SEVERITY_META: Record<
  string,
  { label: string; color: "default" | "info" | "success" | "warning" | "error" }
> = {
  low: { label: "低", color: "default" },
  medium: { label: "中", color: "info" },
  high: { label: "高", color: "warning" },
  critical: { label: "严重", color: "error" },
};
