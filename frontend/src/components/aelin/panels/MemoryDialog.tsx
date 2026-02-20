import React from "react";
import ReactMarkdown from "react-markdown";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import LayersIcon from "@mui/icons-material/Layers";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import TuneIcon from "@mui/icons-material/Tune";
import { alpha, useTheme } from "@mui/material/styles";

import type { AelinMemoryLayerItem } from "../../../api";
import { formatIsoTime } from "../helpers";

type MemoryLayersData = {
  facts: AelinMemoryLayerItem[];
  preferences: AelinMemoryLayerItem[];
  in_progress: AelinMemoryLayerItem[];
  generated_at: string;
};

type MemoryLayerTabValue = "facts" | "preferences" | "in_progress";

type AelinMemoryDialogProps = {
  open: boolean;
  onClose: () => void;
  layerTab: MemoryLayerTabValue;
  onLayerTabChange: (value: MemoryLayerTabValue) => void;
  memoryLayers: MemoryLayersData;
  layerItems: AelinMemoryLayerItem[];
};

export function AelinMemoryDialog({
  open,
  onClose,
  layerTab,
  onLayerTabChange,
  memoryLayers,
  layerItems,
}: AelinMemoryDialogProps) {
  const theme = useTheme();

  return (
    <Dialog
      open={open}
      onClose={onClose}
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
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
        <Tabs
          value={layerTab}
          onChange={(_event, value) => onLayerTabChange(value as MemoryLayerTabValue)}
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
          {layerItems.length ? (
            layerItems.map((item) => (
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
  );
}
