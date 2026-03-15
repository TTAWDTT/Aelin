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

export function applyTheme(mode: ThemeMode) {
  document.documentElement.setAttribute('data-theme', mode)
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
    { name: 'aelin-layout' }
  )
)
