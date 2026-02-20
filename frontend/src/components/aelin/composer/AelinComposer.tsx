import React from "react";
import CloseIcon from "@mui/icons-material/Close";
import ImageIcon from "@mui/icons-material/Image";
import SendIcon from "@mui/icons-material/Send";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import type { AelinCitation } from "../../../api";
import type { PendingImage } from "../types";

type AelinComposerProps = {
  compactMode: boolean;
  mainContainerMaxWidth: false | "md";
  input: string;
  busy: boolean;
  pendingImages: PendingImage[];
  lastAssistantCitation: AelinCitation | null;
  onInputChange: (value: string) => void;
  onSend: (value: string) => void;
  onAppendFiles: (files: File[]) => Promise<void>;
  onRemovePendingImage: (id: string) => void;
  onOpenDeskObserve: () => void;
};

export function AelinComposer({
  compactMode,
  mainContainerMaxWidth,
  input,
  busy,
  pendingImages,
  lastAssistantCitation,
  onInputChange,
  onSend,
  onAppendFiles,
  onRemovePendingImage,
  onOpenDeskObserve,
}: AelinComposerProps) {
  const theme = useTheme();
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  return (
    <Box
      sx={{
        flexShrink: 0,
        pt: compactMode ? 0.7 : 1.1,
        pb: compactMode ? 1.0 : 1.35,
        px: 1.1,
        borderTop: "1px solid",
        borderColor: alpha(theme.palette.divider, 0.9),
        backdropFilter: "blur(8px)",
        background:
          theme.palette.mode === "light"
            ? "linear-gradient(to top, rgba(250,249,245,1), rgba(250,249,245,0.96), rgba(250,249,245,0.56), rgba(250,249,245,0))"
            : "linear-gradient(to top, rgba(20,20,19,1), rgba(20,20,19,0.96), rgba(20,20,19,0.52), rgba(20,20,19,0))",
      }}
    >
      <Container
        maxWidth={mainContainerMaxWidth}
        sx={{ px: { xs: 0.5, sm: compactMode ? 1.0 : 0.4 } }}
      >
        <Paper
          variant="outlined"
          sx={{
            p: compactMode ? 0.72 : 0.9,
            borderRadius: 2.4,
            borderColor: alpha(theme.palette.divider, 0.95),
          }}
        >
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 0.65, px: 0.1 }}
          >
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ fontWeight: 700 }}
            >
              观察联动
            </Typography>
            <Button
              size="small"
              variant="text"
              startIcon={<TravelExploreIcon sx={{ fontSize: 15 }} />}
              onClick={onOpenDeskObserve}
            >
              在 Desk 观察
            </Button>
          </Stack>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: "none" }}
            onChange={async (event) => {
              const files = Array.from(event.target.files || []);
              if (!files.length) return;
              await onAppendFiles(files);
              event.target.value = "";
            }}
          />

          {pendingImages.length ? (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(88px, 1fr))",
                gap: 0.7,
                mb: 0.8,
              }}
            >
              {pendingImages.map((img) => (
                <Box key={img.id} sx={{ position: "relative" }}>
                  <Box
                    component="img"
                    src={img.dataUrl}
                    alt={img.name}
                    sx={{
                      width: "100%",
                      height: 88,
                      objectFit: "cover",
                      borderRadius: 1.1,
                      border: "1px solid",
                      borderColor: "divider",
                    }}
                  />
                  <IconButton
                    size="small"
                    onClick={() => onRemovePendingImage(img.id)}
                    sx={{
                      position: "absolute",
                      right: 4,
                      top: 4,
                      bgcolor: alpha(theme.palette.background.paper, 0.88),
                      "&:hover": {
                        bgcolor: alpha(theme.palette.background.paper, 1),
                      },
                    }}
                  >
                    <CloseIcon sx={{ fontSize: 14 }} />
                  </IconButton>
                </Box>
              ))}
            </Box>
          ) : null}

          <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.8 }}>
            <Tooltip title="上传图片">
              <span>
                <IconButton
                  onClick={() => fileInputRef.current?.click()}
                  disabled={busy || pendingImages.length >= 4}
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: 1.1,
                    border: "1px solid",
                    borderColor: "divider",
                    alignSelf: "flex-end",
                    mb: 0.2,
                  }}
                >
                  <ImageIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <InputBase
              fullWidth
              multiline
              minRows={1}
              maxRows={8}
              placeholder="发送消息..."
              value={input}
              onChange={(event) => onInputChange(event.target.value)}
              onPaste={async (event) => {
                const items = Array.from(event.clipboardData?.items || []);
                const imageFiles: File[] = [];
                for (const item of items) {
                  if (item.type.startsWith("image/")) {
                    const file = item.getAsFile();
                    if (file) imageFiles.push(file);
                  }
                }
                if (!imageFiles.length) return;
                event.preventDefault();
                await onAppendFiles(imageFiles);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  onSend(input);
                }
              }}
              sx={{
                flex: 1,
                px: 1,
                py: 0.75,
                fontSize: "1rem",
                lineHeight: 1.6,
                borderRadius: 1.6,
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "background.paper",
                "& textarea": {
                  resize: "none",
                  p: 0,
                },
                "&.Mui-focused": {
                  borderColor: "primary.main",
                },
              }}
            />
            <Button
              variant="contained"
              onClick={() => onSend(input)}
              disabled={busy || (!input.trim() && pendingImages.length === 0)}
              sx={{
                minWidth: 36,
                width: 36,
                height: 36,
                borderRadius: "50%",
                p: 0,
                alignSelf: "flex-end",
                mb: 0.2,
                transition: "transform 180ms ease, box-shadow 200ms ease",
                boxShadow: `0 6px 14px ${alpha(theme.palette.primary.main, 0.24)}`,
                "&:hover": {
                  transform: "translateY(-1px) scale(1.03)",
                  boxShadow: `0 10px 20px ${alpha(theme.palette.primary.main, 0.32)}`,
                },
              }}
            >
              <SendIcon sx={{ fontSize: 18 }} />
            </Button>
          </Box>

          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.55, px: 0.6 }}
          >
            Enter 发送，Shift+Enter 换行
          </Typography>
          {lastAssistantCitation ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.35, px: 0.6 }}
            >
              最近证据：
              {lastAssistantCitation.source_label ||
                lastAssistantCitation.source}{" "}
              · {lastAssistantCitation.title}
            </Typography>
          ) : null}
        </Paper>
      </Container>
    </Box>
  );
}
