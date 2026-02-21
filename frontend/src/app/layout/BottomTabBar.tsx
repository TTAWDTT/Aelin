import { NavLink, useLocation } from 'react-router-dom'
import { cn } from '@/shared/utils/cn'
import { MODULE_NAV_ITEMS } from './moduleNav'

export function BottomTabBar() {
  const location = useLocation()

  return (
    <nav className="flex h-[62px] shrink-0 items-center justify-around border-t border-[var(--color-border)] bg-[var(--color-panel)] pb-[env(safe-area-inset-bottom)]">
      {MODULE_NAV_ITEMS.map(({ to, icon: Icon, label, mobileLabel, match }) => {
        const active = match ? match(location.pathname) : location.pathname.startsWith(to)
        return (
          <NavLink
            key={to}
            to={to}
            className={cn(
              'flex h-full flex-1 flex-col items-center justify-center gap-0.5 text-[10px]',
              active ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'
            )}
          >
            <Icon size={16} />
            <span>{mobileLabel ?? label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
