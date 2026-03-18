import { create } from 'zustand'

interface ExecutionPaneState {
  open: boolean
  focusedMessageId: string | null
  setOpen: (open: boolean) => void
  openForMessage: (messageId: string | null) => void
  setFocusedMessageId: (messageId: string | null) => void
}

export const useExecutionPaneStore = create<ExecutionPaneState>()((set) => ({
  open: false,
  focusedMessageId: null,
  setOpen: (open) => set({ open }),
  openForMessage: (messageId) =>
    set({
      open: true,
      focusedMessageId: messageId ?? null,
    }),
  setFocusedMessageId: (messageId) => set({ focusedMessageId: messageId ?? null }),
}))
