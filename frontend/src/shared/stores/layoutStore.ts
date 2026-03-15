import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark'

interface LayoutStore {
  theme: ThemeMode
  focusModeEnabled: boolean
  navRailExpanded: boolean
  setTheme: (v: ThemeMode) => void
  setFocusModeEnabled: (v: boolean) => void
  setNavRailExpanded: (v: boolean) => void
  toggleNavRailExpanded: () => void
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
      focusModeEnabled: false,
      navRailExpanded: false,
      setTheme: (v) => set({ theme: v }),
      setFocusModeEnabled: (v) => set({ focusModeEnabled: v }),
      setNavRailExpanded: (v) => set({ navRailExpanded: v }),
      toggleNavRailExpanded: () => set((state) => ({ navRailExpanded: !state.navRailExpanded })),
      applyTheme: (v) => applyTheme(v),
    }),
    {
      name: 'aelin-layout',
      version: 2,
      migrate: (persistedState) => {
        if (!persistedState || typeof persistedState !== 'object') {
          return persistedState
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
