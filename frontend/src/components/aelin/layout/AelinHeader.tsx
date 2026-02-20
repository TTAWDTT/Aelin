import React from "react";
import Avatar from "@mui/material/Avatar";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import ComputerIcon from "@mui/icons-material/Computer";
import LayersIcon from "@mui/icons-material/Layers";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import SettingsIcon from "@mui/icons-material/Settings";
import TimelineIcon from "@mui/icons-material/Timeline";
import TrackChangesIcon from "@mui/icons-material/TrackChanges";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import { alpha, useTheme } from "@mui/material/styles";

import { AELIN_LOGO_SRC } from "../constants";
import { formatTime } from "../helpers";
import type { ChatSession } from "../types";

type AelinHeaderProps = {
  compactMode: boolean;
  embedded: boolean;
  mainContainerMaxWidth: false | "md";
  activeSessionId: string;
  sortedSessions: ChatSession[];
  storyBusy: boolean;
  trackingUnreadCount: number;
  trackingItemsCount: number;
  unreadNotificationCount: number;
  onSessionChange: (sessionId: string) => void;
  onNewConversation: () => void;
  onRunStoryMode: () => void;
  onOpenTracking: () => void;
  onOpenNotification: () => void;
  onOpenDevice: () => void;
  onOpenMemory: () => void;
  onOpenDesk: () => void;
  onOpenSettings: () => void;
  onRequestClose?: () => void;
};

export function AelinHeader({
  compactMode,
  embedded,
  mainContainerMaxWidth,
  activeSessionId,
  sortedSessions,
  storyBusy,
  trackingUnreadCount,
  trackingItemsCount,
  unreadNotificationCount,
  onSessionChange,
  onNewConversation,
  onRunStoryMode,
  onOpenTracking,
  onOpenNotification,
  onOpenDevice,
  onOpenMemory,
  onOpenDesk,
  onOpenSettings,
  onRequestClose,
}: AelinHeaderProps) {
  const theme = useTheme();

  return (
    <Box
      sx={{
        height: compactMode ? "auto" : 64,
        minHeight: compactMode ? 74 : 64,
        py: compactMode ? 0.75 : 0,
        borderBottom: "1px solid",
        borderColor: "divider",
        display: "flex",
        alignItems: "center",
        flexShrink: 0,
        position: "relative",
        zIndex: 2,
        bgcolor: alpha(theme.palette.background.default, 0.82),
        backdropFilter: "blur(8px)",
      }}
    >
      <Container
        maxWidth={mainContainerMaxWidth}
        sx={{
          display: "flex",
          flexDirection: compactMode ? "column" : "row",
          alignItems: compactMode ? "stretch" : "center",
          justifyContent: "space-between",
          rowGap: compactMode ? 0.65 : 0,
          px: { xs: 0.9, sm: compactMode ? 1.3 : 2.2 },
        }}
      >
        <Stack
          direction="row"
          spacing={1.1}
          alignItems="center"
          sx={{ width: compactMode ? "100%" : "auto" }}
        >
          <Avatar
            src={AELIN_LOGO_SRC}
            sx={{
              width: 34,
              height: 34,
              borderRadius: 1.2,
              bgcolor: "transparent",
              border: "none",
              boxShadow: "none",
            }}
            imgProps={{
              style: { objectFit: "cover", objectPosition: "center 24%" },
            }}
          />
          <Box>
            <Typography
              variant="subtitle1"
              sx={{ fontWeight: 700, lineHeight: 1.06, fontSize: "1.03rem" }}
            >
              Aelin
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ fontSize: "0.8rem" }}
            >
              Chat
            </Typography>
          </Box>
        </Stack>

        <Stack
          direction="row"
          spacing={0.55}
          alignItems="center"
          flexWrap={compactMode ? "wrap" : "nowrap"}
          useFlexGap
          sx={{
            width: compactMode ? "100%" : "auto",
            justifyContent: compactMode ? "flex-start" : "flex-end",
            rowGap: compactMode ? 0.5 : 0,
          }}
        >
          <FormControl
            size="small"
            sx={{
              minWidth: compactMode ? 150 : 170,
              width: compactMode ? "100%" : "auto",
              flex: compactMode ? "1 1 210px" : "0 0 auto",
            }}
          >
            <Select
              value={activeSessionId}
              onChange={(event) =>
                onSessionChange(String(event.target.value || ""))
              }
              displayEmpty
              sx={{
                borderRadius: 1.4,
                fontSize: "0.85rem",
                "& .MuiSelect-select": {
                  py: compactMode ? 0.58 : 0.6,
                  pr: 2.2,
                },
              }}
            >
              {sortedSessions.map((session) => (
                <MenuItem key={session.id} value={session.id}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      width: "100%",
                      gap: 1,
                    }}
                  >
                    <Typography
                      variant="body2"
                      sx={{
                        maxWidth: 132,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {session.title || "新对话"}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {formatTime(session.updated_at)}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Tooltip title="新对话">
            <IconButton onClick={onNewConversation}>
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="故事模式">
            <span>
              <IconButton onClick={onRunStoryMode} disabled={storyBusy}>
                <TimelineIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="跟踪列表">
            <IconButton onClick={onOpenTracking}>
              <Badge
                color="primary"
                badgeContent={Math.min(
                  99,
                  trackingUnreadCount || trackingItemsCount,
                )}
                invisible={!trackingUnreadCount && !trackingItemsCount}
                overlap="circular"
              >
                <TrackChangesIcon fontSize="small" />
              </Badge>
            </IconButton>
          </Tooltip>
          <Tooltip title="通知中心">
            <IconButton onClick={onOpenNotification}>
              <Badge
                color="error"
                badgeContent={unreadNotificationCount}
                invisible={!unreadNotificationCount}
                overlap="circular"
              >
                <NotificationsNoneIcon fontSize="small" />
              </Badge>
            </IconButton>
          </Tooltip>
          <Tooltip title="设备中心">
            <IconButton onClick={onOpenDevice}>
              <ComputerIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="分层记忆">
            <IconButton onClick={onOpenMemory}>
              <LayersIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="打开观察台">
            <IconButton onClick={onOpenDesk}>
              <TravelExploreIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="设置">
            <IconButton onClick={onOpenSettings}>
              <SettingsIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {embedded && onRequestClose ? (
            <Tooltip title="收起 Aelin">
              <IconButton onClick={onRequestClose}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : null}
        </Stack>
      </Container>
    </Box>
  );
}
