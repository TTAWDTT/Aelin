import { Outlet } from 'react-router-dom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { NavigationRail } from './NavigationRail'
import { BottomTabBar } from './BottomTabBar'

export function RootLayout() {
  const isTablet = useMediaQuery('(min-width: 820px)')
  const isMobile = !isTablet

  return (
    <div className="aelin-app">
      <div className="flex h-full overflow-hidden">
        {isTablet && <NavigationRail />}
        <main className="flex min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
      {isMobile && <BottomTabBar />}
    </div>
  )
}
