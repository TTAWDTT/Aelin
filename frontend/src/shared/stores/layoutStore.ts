import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark' | 'system'

interface LayoutStore {
  theme: ThemeMode
  contextPanelOpen: boolean
  sidebarCollapsed: boolean
  setTheme: (v: ThemeMode) => void
  toggleContextPanel: () => void
  setContextPanelOpen: (v: boolean) => void
  setSidebarCollapsed: (v: boolean) => void
  applyTheme: (v: ThemeMode) => void
}

export function applyTheme(mode: ThemeMode) {
  const resolved = mode === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : mode
  document.documentElement.setAttribute('data-theme', resolved)
}

export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      theme: 'system',
      contextPanelOpen: false,
      sidebarCollapsed: false,
      setTheme: (v) => set({ theme: v }),
      toggleContextPanel: () => set(s => ({ contextPanelOpen: !s.contextPanelOpen })),
      setContextPanelOpen: (v) => set({ contextPanelOpen: v }),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      applyTheme: (v) => applyTheme(v),
    }),
    { name: 'aelin-layout' }
  )
)
