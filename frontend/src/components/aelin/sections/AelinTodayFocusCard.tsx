import React from "react";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import BoltIcon from "@mui/icons-material/Bolt";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import type { AelinContextResponse } from "../../../api";
import { QUICK_PROMPTS } from "../constants";

type AelinTodayFocusCardProps = {
  contextSnapshot: AelinContextResponse | null;
  storyBusy: boolean;
  onRunStoryMode: () => void;
  onSendPrompt: (prompt: string) => void;
};

export function AelinTodayFocusCard({
  contextSnapshot,
  storyBusy,
  onRunStoryMode,
  onSendPrompt,
}: AelinTodayFocusCardProps) {
  const theme = useTheme();

  return (
    <Paper
      variant="outlined"
      sx={{
        px: 1.2,
        py: 1.1,
        borderRadius: 2.2,
        borderColor: alpha(theme.palette.primary.main, 0.28),
        background:
          theme.palette.mode === "light"
            ? "linear-gradient(135deg, rgba(255,255,255,0.96), rgba(245,249,255,0.86))"
            : "linear-gradient(135deg, rgba(34,34,34,0.96), rgba(22,28,36,0.86))",
        mb: 1.1,
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 0.8 }}
      >
        <Stack direction="row" spacing={0.8} alignItems="center">
          <BoltIcon sx={{ fontSize: 18, color: "primary.main" }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
            Today Focus
          </Typography>
        </Stack>
        <Button
          size="small"
          startIcon={<AutoStoriesIcon sx={{ fontSize: 16 }} />}
          onClick={onRunStoryMode}
          disabled={storyBusy}
        >
          {storyBusy ? "生成中..." : "故事模式"}
        </Button>
      </Stack>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.55 }}
      >
        {contextSnapshot?.daily_brief?.summary ||
          "正在读取你的每日简报与高价值信号..."}
      </Typography>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" },
          gap: 0.7,
          mt: 0.95,
        }}
      >
        {(contextSnapshot?.daily_brief?.top_updates || [])
          .slice(0, 3)
          .map((item, idx) => (
            <Paper
              key={`${item.message_id}-${idx}`}
              variant="outlined"
              onClick={() =>
                onSendPrompt(
                  `请详细解释这个更新并告诉我为什么重要：${item.title}`,
                )
              }
              sx={{
                px: 0.85,
                py: 0.72,
                borderRadius: 1.5,
                borderColor: alpha(theme.palette.primary.main, 0.24),
                bgcolor: alpha(theme.palette.primary.main, 0.06),
                cursor: "pointer",
                transition: "transform 160ms ease, box-shadow 200ms ease",
                "&:hover": {
                  transform: "translateY(-1px)",
                  boxShadow: "0 10px 20px rgba(0,0,0,0.08)",
                },
              }}
            >
              <Typography
                variant="caption"
                sx={{ fontWeight: 700, color: "primary.main" }}
              >
                {item.source_label}
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontWeight: 700, mt: 0.2, lineHeight: 1.35 }}
              >
                {item.title}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {item.sender} · {item.received_at}
              </Typography>
            </Paper>
          ))}
      </Box>

      <Divider sx={{ my: 0.95 }} />
      <Stack
        direction="row"
        spacing={0.7}
        flexWrap="wrap"
        useFlexGap
        sx={{ py: 0.2 }}
      >
        {QUICK_PROMPTS.map((prompt) => (
          <Chip
            key={prompt}
            size="small"
            variant="outlined"
            clickable
            onClick={() => onSendPrompt(prompt)}
            label={prompt}
          />
        ))}
      </Stack>
    </Paper>
  );
}
