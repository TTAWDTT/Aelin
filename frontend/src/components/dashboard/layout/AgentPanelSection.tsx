import React from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";

import type {
  AgentAdvancedSearchItem,
  AgentDailyBrief,
  AgentDailyBriefAction,
  AgentMemorySnapshot,
  AgentTodoItem,
  Contact,
} from "../../../api";
import { AgentBriefPanel } from "../AgentBriefPanel";
import { AgentMemoryPanel } from "../AgentMemoryPanel";
import { AgentSearchPanel } from "../AgentSearchPanel";
import { AgentTodoPanel } from "../AgentTodoPanel";

type PanelTab = "brief" | "todo" | "search" | "memory";

type AgentPanelSectionProps = {
  activePanel: PanelTab;
  setActivePanel: (panel: PanelTab) => void;
  todos: AgentTodoItem[];
  advancedItems: AgentAdvancedSearchItem[];
  memorySnapshot: AgentMemorySnapshot | null;
  dailyBrief: AgentDailyBrief | undefined;
  actionBusy: boolean;
  onApplyBriefAction: (action: AgentDailyBriefAction) => Promise<void> | void;
  todoInput: string;
  todoBusy: boolean;
  onTodoInputChange: (value: string) => void;
  onCreateTodo: () => Promise<void> | void;
  onToggleTodoDone: (
    todo: AgentTodoItem,
    done: boolean,
  ) => Promise<void> | void;
  onDeleteTodo: (todoId: number) => Promise<void> | void;
  onOpenContact: (contactId?: number | null) => void;
  advancedQuery: string;
  advancedSource: string;
  advancedUnreadOnly: boolean;
  advancedDays: number;
  advancedLimit: number;
  advancedBusy: boolean;
  onAdvancedQueryChange: (value: string) => void;
  onAdvancedSourceChange: (value: string) => void;
  onAdvancedUnreadOnlyChange: (value: boolean) => void;
  onAdvancedDaysChange: (value: number) => void;
  onAdvancedLimitChange: (value: number) => void;
  onAdvancedSearch: () => Promise<void> | void;
  memoryBusy: boolean;
  memoryCorrection: string;
  onMemoryCorrectionChange: (value: string) => void;
  onRefreshMemory: () => Promise<void> | void;
  onSaveMemoryCorrection: () => Promise<void> | void;
  onDeleteMemoryNote: (noteId: number) => Promise<void> | void;
};

export function AgentPanelSection({
  activePanel,
  setActivePanel,
  todos,
  advancedItems,
  memorySnapshot,
  dailyBrief,
  actionBusy,
  onApplyBriefAction,
  todoInput,
  todoBusy,
  onTodoInputChange,
  onCreateTodo,
  onToggleTodoDone,
  onDeleteTodo,
  onOpenContact,
  advancedQuery,
  advancedSource,
  advancedUnreadOnly,
  advancedDays,
  advancedLimit,
  advancedBusy,
  onAdvancedQueryChange,
  onAdvancedSourceChange,
  onAdvancedUnreadOnlyChange,
  onAdvancedDaysChange,
  onAdvancedLimitChange,
  onAdvancedSearch,
  memoryBusy,
  memoryCorrection,
  onMemoryCorrectionChange,
  onRefreshMemory,
  onSaveMemoryCorrection,
  onDeleteMemoryNote,
}: AgentPanelSectionProps) {
  return (
    <>
      <Tabs
        value={activePanel}
        onChange={(_, value) => setActivePanel(value)}
        variant="fullWidth"
        sx={{
          px: 0.6,
          pt: 0.6,
          minHeight: 34,
          "& .MuiTab-root": {
            minWidth: 0,
            minHeight: 34,
            px: 0.5,
            py: 0.25,
            fontSize: "0.77rem",
            lineHeight: 1.15,
            letterSpacing: 0,
            textTransform: "none",
          },
        }}
      >
        <Tab value="brief" label="简报" />
        <Tab
          value="todo"
          label={`待办${todos.length ? ` (${Math.min(20, todos.length)})` : ""}`}
        />
        <Tab
          value="search"
          label={`搜索${advancedItems.length ? ` (${Math.min(99, advancedItems.length)})` : ""}`}
        />
        <Tab
          value="memory"
          label={`记忆${memorySnapshot?.notes?.length ? ` (${Math.min(99, memorySnapshot.notes.length)})` : ""}`}
        />
      </Tabs>

      <Box
        sx={{
          px: 1.8,
          pb: 1.8,
          "& > *": {
            contentVisibility: "auto",
            containIntrinsicSize: "380px 520px",
          },
        }}
      >
        {activePanel === "brief" && (
          <AgentBriefPanel
            dailyBrief={dailyBrief}
            actionBusy={actionBusy}
            onApplyAction={onApplyBriefAction}
          />
        )}
        {activePanel === "todo" && (
          <AgentTodoPanel
            todos={todos}
            todoInput={todoInput}
            todoBusy={todoBusy}
            onTodoInputChange={onTodoInputChange}
            onCreateTodo={onCreateTodo}
            onToggleTodoDone={onToggleTodoDone}
            onDeleteTodo={onDeleteTodo}
            onOpenContact={onOpenContact}
          />
        )}
        {activePanel === "search" && (
          <AgentSearchPanel
            query={advancedQuery}
            source={advancedSource}
            unreadOnly={advancedUnreadOnly}
            days={advancedDays}
            limit={advancedLimit}
            busy={advancedBusy}
            items={advancedItems}
            onQueryChange={onAdvancedQueryChange}
            onSourceChange={onAdvancedSourceChange}
            onUnreadOnlyChange={onAdvancedUnreadOnlyChange}
            onDaysChange={onAdvancedDaysChange}
            onLimitChange={onAdvancedLimitChange}
            onSearch={onAdvancedSearch}
            onOpenContact={onOpenContact}
          />
        )}
        {activePanel === "memory" && (
          <AgentMemoryPanel
            memorySnapshot={memorySnapshot}
            memoryBusy={memoryBusy}
            memoryCorrection={memoryCorrection}
            onMemoryCorrectionChange={onMemoryCorrectionChange}
            onRefresh={onRefreshMemory}
            onSaveCorrection={onSaveMemoryCorrection}
            onDeleteNote={onDeleteMemoryNote}
          />
        )}
      </Box>
    </>
  );
}
