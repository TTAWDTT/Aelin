import React from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemAvatar from "@mui/material/ListItemAvatar";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import SyncIcon from "@mui/icons-material/Sync";

import type { ConnectedAccount } from "../../../../api";

type ConnectedAccountsListProps = {
  accounts: ConnectedAccount[];
  syncingAccountId: number | null;
  accountIcon: (provider: string) => React.ReactNode;
  onSyncIncremental: (id: number) => void;
  onSyncFull: (id: number) => Promise<void> | void;
  onDelete: (id: number) => void;
};

export function ConnectedAccountsList({
  accounts,
  syncingAccountId,
  accountIcon,
  onSyncIncremental,
  onSyncFull,
  onDelete,
}: ConnectedAccountsListProps) {
  return (
    <List>
      {accounts.map((account) => (
        <React.Fragment key={account.id}>
          <ListItem
            secondaryAction={
              <Box>
                <Tooltip title="左键：增量同步 | 右键：全量重新同步" arrow>
                  <IconButton
                    edge="end"
                    onClick={() => onSyncIncremental(account.id)}
                    onContextMenu={async (event) => {
                      event.preventDefault();
                      await onSyncFull(account.id);
                    }}
                    disabled={syncingAccountId === account.id}
                    sx={{ mr: 1 }}
                  >
                    {syncingAccountId === account.id ? (
                      <CircularProgress size={20} />
                    ) : (
                      <SyncIcon />
                    )}
                  </IconButton>
                </Tooltip>
                <IconButton
                  edge="end"
                  onClick={() => onDelete(account.id)}
                  color="error"
                >
                  <DeleteIcon />
                </IconButton>
              </Box>
            }
          >
            <ListItemAvatar>
              <Avatar sx={{ bgcolor: "action.hover", color: "text.primary" }}>
                {accountIcon(account.provider)}
              </Avatar>
            </ListItemAvatar>
            <ListItemText
              primary={account.identifier}
              secondary={`类型：${account.provider} • 上次同步：${account.last_synced_at ? new Date(account.last_synced_at).toLocaleString() : "从未"}`}
            />
          </ListItem>
          <Divider variant="inset" component="li" />
        </React.Fragment>
      ))}
    </List>
  );
}
