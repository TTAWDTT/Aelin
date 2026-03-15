import { Outlet } from 'react-router-dom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { useAelinProactivePoll } from '@/shared/hooks/useAelinProactivePoll'
import { cn } from '@/shared/utils/cn'
import { NavigationRail } from './NavigationRail'
import { BottomTabBar } from './BottomTabBar'

export function RootLayout() {
  const isTablet = useMediaQuery('(min-width: 820px)')
  const isMobile = !isTablet
  useAelinProactivePoll('default')

  return (
    <div className="aelin-app flex min-h-0 flex-col">
      <div
        className={cn(
          'aelin-shell flex min-h-0 flex-1 overflow-hidden',
          isTablet ? 'gap-4 p-4' : 'px-3 pb-0 pt-3'
        )}
      >
        {isTablet && <NavigationRail />}
        <main className="aelin-shell-main flex min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
      {isMobile && <BottomTabBar />}
    </div>
  )
}
