import React from "react";
import { motion } from "framer-motion";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

type HandoffFXState = {
  title: string;
  detail: string;
};

type DashboardHandoffBannerProps = {
  handoffFX: HandoffFXState | null;
};

export function DashboardHandoffBanner({
  handoffFX,
}: DashboardHandoffBannerProps) {
  const theme = useTheme();
  if (!handoffFX) return null;

  return (
    <Box
      component={motion.div}
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.99 }}
      transition={{ duration: 0.2 }}
      sx={{
        position: "fixed",
        top: { xs: 72, md: 80 },
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1500,
        pointerEvents: "none",
        width: "min(680px, calc(100vw - 28px))",
      }}
    >
      <Paper
        elevation={0}
        sx={{
          px: 1.2,
          py: 0.95,
          borderRadius: 2,
          border: "1px solid",
          borderColor: alpha(theme.palette.primary.main, 0.34),
          bgcolor: alpha(theme.palette.background.paper, 0.94),
          backdropFilter: "blur(10px)",
          boxShadow: `0 12px 26px ${alpha(theme.palette.common.black, 0.14)}`,
        }}
      >
        <Typography variant="body2" sx={{ fontWeight: 800, lineHeight: 1.2 }}>
          {handoffFX.title}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ lineHeight: 1.3 }}
        >
          {handoffFX.detail}
        </Typography>
      </Paper>
    </Box>
  );
}
