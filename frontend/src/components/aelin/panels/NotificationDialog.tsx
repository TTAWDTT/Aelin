import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import RefreshIcon from "@mui/icons-material/Refresh";
import { alpha, useTheme } from "@mui/material/styles";

import type { AelinNotificationItem } from "../../../api";
import { formatIsoTime } from "../helpers";

type AelinNotificationDialogProps = {
  open: boolean;
  busy: boolean;
  items: AelinNotificationItem[];
  onClose: () => void;
  onRefresh: () => void;
  onAction: (item: AelinNotificationItem) => void;
};

export function AelinNotificationDialog({
  open,
  busy,
  items,
  onClose,
  onRefresh,
  onAction,
}: AelinNotificationDialogProps) {
  const theme = useTheme();

  return (
    <Dialog
      open={open}
      onClose={onClose}
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
                <IconButton size="small" onClick={onRefresh} disabled={busy}>
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <IconButton size="small" onClick={onClose}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
      </Box>

      <Box sx={{ px: 1.2, py: 1.1, maxHeight: "68vh", overflowY: "auto" }}>
        {busy ? (
          <Stack spacing={0.7}>
            <Skeleton variant="rounded" height={64} />
            <Skeleton variant="rounded" height={64} />
            <Skeleton variant="rounded" height={64} />
          </Stack>
        ) : items.length ? (
          <Stack spacing={0.72}>
            {items.map((item) => (
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
                      <Button size="small" variant="outlined" onClick={() => onAction(item)}>
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
  );
}
