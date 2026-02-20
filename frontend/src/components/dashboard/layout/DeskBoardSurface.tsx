import React from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import { useTheme } from "@mui/material/styles";

import type {
  AgentCardLayoutItem,
  AgentPinRecommendationResponse,
  Contact,
} from "../../../api";
import { boardDark, boardLight } from "../../../theme";
import { ContactGrid } from "../../ContactGrid";
import { BoardWorkspaceHeader } from "../BoardWorkspaceHeader";
import { DashboardSyncProgress, SyncProgressPanel } from "../SyncProgressPanel";

type WorkspaceItem = {
  key: string;
  label: string;
};

type DeskBoardSurfaceProps = {
  workspaces: WorkspaceItem[];
  activeWorkspace: string;
  onSelectWorkspace: (workspace: string) => void;
  onRefreshAgentPanels: () => Promise<void> | void;
  syncProgress: DashboardSyncProgress | null;
  contacts: Contact[] | undefined;
  onContactClick: (contact: Contact | null) => void;
  onCardLayoutChange: (cards: AgentCardLayoutItem[]) => void;
  workspace: string;
  pinRecommendations: AgentPinRecommendationResponse["items"];
  onCardAction: (
    contact: Contact,
    action: "summarize" | "draft" | "todo",
  ) => Promise<void> | void;
  highlightContactId: number | null;
  sx?: Record<string, unknown>;
};

export function DeskBoardSurface({
  workspaces,
  activeWorkspace,
  onSelectWorkspace,
  onRefreshAgentPanels,
  syncProgress,
  contacts,
  onContactClick,
  onCardLayoutChange,
  workspace,
  pinRecommendations,
  onCardAction,
  highlightContactId,
  sx,
}: DeskBoardSurfaceProps) {
  const theme = useTheme();

  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: 4,
        bgcolor: theme.palette.mode === "light" ? boardLight : boardDark,
        backdropFilter: "blur(4px)",
        minHeight: "70vh",
        border: "1px solid",
        borderColor: "divider",
        overflow: "hidden",
        boxShadow:
          theme.palette.mode === "light"
            ? "0 8px 18px rgba(20,20,19,0.06)"
            : "0 10px 22px rgba(0,0,0,0.24)",
        ...(sx || {}),
      }}
    >
      <BoardWorkspaceHeader
        workspaces={workspaces}
        activeWorkspace={activeWorkspace}
        onSelectWorkspace={onSelectWorkspace}
        onRefreshAgentPanels={onRefreshAgentPanels}
      />

      {syncProgress && (
        <>
          <Box p={{ xs: 2, md: 2.5 }}>
            <SyncProgressPanel progress={syncProgress} />
          </Box>
          <Divider />
        </>
      )}

      <ContactGrid
        contacts={contacts}
        loading={!contacts}
        onContactClick={onContactClick}
        onCardLayoutChange={onCardLayoutChange}
        workspace={workspace}
        pinRecommendations={pinRecommendations}
        onCardAction={onCardAction}
        highlightContactId={highlightContactId}
        focusContactId={highlightContactId}
      />
    </Paper>
  );
}
