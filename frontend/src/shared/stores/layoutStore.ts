import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark' | 'system'

interface LayoutStore {
  theme: ThemeMode
  navRailExpanded: boolean
  setTheme: (v: ThemeMode) => void
  setNavRailExpanded: (v: boolean) => void
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
      navRailExpanded: false,
      setTheme: (v) => set({ theme: v }),
      setNavRailExpanded: (v) => set({ navRailExpanded: v }),
      applyTheme: (v) => applyTheme(v),
    }),
    { name: 'aelin-layout' }
  )
)
