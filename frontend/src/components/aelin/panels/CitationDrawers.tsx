import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import type { AelinCitation, MessageDetail } from "../../../api";

export type CitationPreviewState = {
  open: boolean;
  citation: AelinCitation | null;
  url: string;
  loading: boolean;
  error: string;
};

export type CitationDrawerState = {
  open: boolean;
  citation: AelinCitation | null;
  detail: MessageDetail | null;
  loading: boolean;
  error: string;
};

type AelinCitationDrawersProps = {
  citationPreview: CitationPreviewState;
  citationDrawer: CitationDrawerState;
  onClosePreview: () => void;
  onCloseDrawer: () => void;
  onOpenCitationWeb: (citation: AelinCitation) => void;
  onOpenDeskFromCitation: (citation: AelinCitation) => void;
  onCopyText: (text: string) => void;
};

export function AelinCitationDrawers({
  citationPreview,
  citationDrawer,
  onClosePreview,
  onCloseDrawer,
  onOpenCitationWeb,
  onOpenDeskFromCitation,
  onCopyText,
}: AelinCitationDrawersProps) {
  return (
    <>
      <Drawer
        anchor="right"
        open={citationPreview.open}
        onClose={onClosePreview}
        PaperProps={{
          sx: {
            width: {
              xs: "100vw",
              sm: "min(100vw, 92vw)",
              md: "min(100vw, 88vw)",
              lg: "min(100vw, 1240px)",
            },
            maxWidth: "100vw",
            p: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          },
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ px: 1.1, py: 0.9, borderBottom: "1px solid", borderColor: "divider", gap: 0.8 }}
        >
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 800, lineHeight: 1.2 }}>
              网页预览
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {citationPreview.citation?.title || citationPreview.url || "来源链接"}
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.4} sx={{ flexShrink: 0 }}>
            {citationPreview.url ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  window.open(citationPreview.url, "_blank", "noopener,noreferrer");
                }}
              >
                外部打开
              </Button>
            ) : null}
            <IconButton size="small" onClick={onClosePreview}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
        <Box sx={{ p: 1.05, flex: 1, minHeight: 0 }}>
          {citationPreview.loading ? (
            <Stack spacing={0.9}>
              <Skeleton variant="rounded" height={24} />
              <Skeleton variant="rounded" height={24} />
              <Skeleton variant="rounded" height={420} />
            </Stack>
          ) : citationPreview.error ? (
            <Alert severity="warning" sx={{ borderRadius: 1.2 }}>
              {citationPreview.error}
            </Alert>
          ) : citationPreview.url ? (
            <Box
              component="iframe"
              src={citationPreview.url}
              title={citationPreview.citation?.title || "citation-preview"}
              sx={{
                width: "100%",
                height: "100%",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1.1,
                bgcolor: "background.paper",
              }}
            />
          ) : (
            <Alert severity="info" sx={{ borderRadius: 1.2 }}>
              未解析到可预览网页，请在证据详情中查看原文。
            </Alert>
          )}
        </Box>
      </Drawer>

      <Drawer
        anchor="right"
        open={citationDrawer.open}
        onClose={onCloseDrawer}
        PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 1.2 } }}
      >
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.9 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
            证据详情
          </Typography>
          <IconButton size="small" onClick={onCloseDrawer}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
        {citationDrawer.citation ? (
          <Box sx={{ p: 0.9, borderRadius: 1.4, mb: 0.95, border: "1px solid", borderColor: "divider" }}>
            <Typography variant="caption" color="text.secondary">
              {citationDrawer.citation.source_label} 路 {citationDrawer.citation.sender} 路 {citationDrawer.citation.received_at}
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.35, fontWeight: 700, lineHeight: 1.4 }}>
              {citationDrawer.citation.title}
            </Typography>
          </Box>
        ) : null}
        {citationDrawer.loading ? (
          <Stack direction="row" spacing={0.7} alignItems="center" sx={{ py: 1 }}>
            <Typography variant="body2" color="text.secondary">
              正在加载原文...
            </Typography>
          </Stack>
        ) : citationDrawer.error ? (
          <Typography variant="body2" color="error.main">
            {citationDrawer.error}
          </Typography>
        ) : (
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.62 }}>
            {citationDrawer.detail?.body || "暂无正文内容。"}
          </Typography>
        )}
        <Divider sx={{ my: 1 }} />
        <Stack direction="row" spacing={0.7}>
          <Button
            size="small"
            variant="contained"
            onClick={() => {
              if (!citationDrawer.citation) return;
              onOpenCitationWeb(citationDrawer.citation);
            }}
          >
            打开网页
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => {
              const citation = citationDrawer.citation;
              if (!citation?.message_id) return;
              onOpenDeskFromCitation(citation);
            }}
          >
            在 Desk 查看
          </Button>
          <Button
            size="small"
            variant="text"
            onClick={() => {
              const text = citationDrawer.detail?.body || citationDrawer.citation?.title || "";
              onCopyText(text);
            }}
          >
            复制内容
          </Button>
        </Stack>
      </Drawer>
    </>
  );
}
