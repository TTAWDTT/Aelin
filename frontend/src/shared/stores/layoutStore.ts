import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark' | 'system'

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
      focusModeEnabled: false,
      navRailExpanded: false,
      setTheme: (v) => set({ theme: v }),
      setFocusModeEnabled: (v) => set({ focusModeEnabled: v }),
      setNavRailExpanded: (v) => set({ navRailExpanded: v }),
      toggleNavRailExpanded: () => set((state) => ({ navRailExpanded: !state.navRailExpanded })),
      applyTheme: (v) => applyTheme(v),
    }),
    { name: 'aelin-layout' }
  )
)
