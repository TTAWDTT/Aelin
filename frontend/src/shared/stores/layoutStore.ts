import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark'

interface LayoutStore {
  theme: ThemeMode
  navRailExpanded: boolean
  sessionsVisible: boolean
  setTheme: (v: ThemeMode) => void
  setNavRailExpanded: (v: boolean) => void
  toggleNavRailExpanded: () => void
  setSessionsVisible: (v: boolean) => void
  applyTheme: (v: ThemeMode) => void
}

function normalizeThemeMode(mode: unknown): ThemeMode {
  return mode === 'dark' ? 'dark' : 'light'
}

export function applyTheme(mode: ThemeMode | unknown) {
  document.documentElement.setAttribute('data-theme', normalizeThemeMode(mode))
}

export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      theme: 'light',
      navRailExpanded: false,
      sessionsVisible: true,
      setTheme: (v) => set({ theme: v }),
      setNavRailExpanded: (v) => set({ navRailExpanded: v }),
      toggleNavRailExpanded: () => set((state) => ({ navRailExpanded: !state.navRailExpanded })),
      setSessionsVisible: (v) => set({ sessionsVisible: v }),
      applyTheme: (v) => applyTheme(v),
    }),
    {
      name: 'aelin-layout',
      version: 2,
      migrate: (persistedState) => {
        if (!persistedState || typeof persistedState !== 'object') {
          return {}
        }
        const state = persistedState as Record<string, unknown>
        return {
          ...state,
          theme: normalizeThemeMode(state.theme),
        }
      },
    }
  )
)
