import { Outlet } from 'react-router-dom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { NavigationRail } from './NavigationRail'
import { BottomTabBar } from './BottomTabBar'
import { ContextPanel } from '@/features/context-panel/ContextPanel'

export function RootLayout() {
  const isDesktop = useMediaQuery('(min-width: 1280px)')
  const isTablet = useMediaQuery('(min-width: 768px)')
  const isMobile = !isTablet
  const { contextPanelOpen, toggleContextPanel } = useLayoutStore()

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg)] text-[var(--color-text)]">
      {isTablet && <NavigationRail compact={!isDesktop} />}

      <main className="flex-1 min-w-0 overflow-hidden flex flex-col">
        <Outlet />
      </main>

      {isDesktop && contextPanelOpen && (
        <aside className="w-[360px] border-l border-[var(--color-border)] overflow-y-auto bg-[var(--color-panel)]">
          <ContextPanel />
        </aside>
      )}

      {!isDesktop && contextPanelOpen && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={toggleContextPanel}>
          <div className="w-[360px] max-w-full bg-[var(--color-panel)] border-l border-[var(--color-border)] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <ContextPanel onClose={toggleContextPanel} />
          </div>
        </div>
      )}

      {isMobile && <BottomTabBar />}
    </div>
  )
}
