import { create } from 'zustand'

interface ExecutionPaneState {
  open: boolean
  setOpen: (open: boolean) => void
  suppressAutoOpen: boolean
  setSuppressAutoOpen: (suppress: boolean) => void
}

export const useExecutionPaneStore = create<ExecutionPaneState>()((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  suppressAutoOpen: false,
  setSuppressAutoOpen: (suppress) => set({ suppressAutoOpen: suppress }),
}))
