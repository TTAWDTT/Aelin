import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TrackChangesIcon from "@mui/icons-material/TrackChanges";
import { alpha, useTheme } from "@mui/material/styles";

import type { TrackingSheetState } from "../types";

type TrackingChoice = "track" | "once" | "dismiss";

type AelinTrackingChoiceSheetProps = {
  trackingSheet: TrackingSheetState | null;
  onChoice: (choice: TrackingChoice) => void;
};

export function AelinTrackingChoiceSheet({
  trackingSheet,
  onChoice,
}: AelinTrackingChoiceSheetProps) {
  const theme = useTheme();
  if (!trackingSheet) return null;

  return (
    <Paper
      variant="outlined"
      sx={{
        position: "fixed",
        left: "50%",
        transform: "translateX(-50%)",
        bottom: 112,
        zIndex: 1300,
        width: "min(760px, calc(100vw - 24px))",
        px: 1.1,
        py: 0.95,
        borderRadius: 2,
        borderColor: alpha(theme.palette.primary.main, 0.4),
        bgcolor: alpha(theme.palette.background.paper, 0.96),
        backdropFilter: "blur(10px)",
        boxShadow: "0 16px 32px rgba(0,0,0,0.16)",
        "@keyframes sheetIn": {
          from: { opacity: 0, transform: "translateX(-50%) translateY(8px)" },
          to: { opacity: 1, transform: "translateX(-50%) translateY(0)" },
        },
        animation: "sheetIn 180ms ease",
      }}
    >
      <Stack direction={{ xs: "column", sm: "row" }} spacing={0.9} alignItems={{ xs: "flex-start", sm: "center" }} justifyContent="space-between">
        <Stack direction="row" spacing={0.7} alignItems="center">
          <TrackChangesIcon sx={{ fontSize: 17, color: "primary.main" }} />
          <Typography variant="body2" sx={{ fontWeight: 700 }}>
            {trackingSheet.action.title || "是否开启持续跟踪？"}
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap>
          <Button size="small" variant="contained" onClick={() => onChoice("track")}>
            跟踪 7 天
          </Button>
          <Button size="small" variant="outlined" onClick={() => onChoice("once")}>
            仅这次
          </Button>
          <Button size="small" color="inherit" onClick={() => onChoice("dismiss")}>
            不再提示
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
