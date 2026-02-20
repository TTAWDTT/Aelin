import { NavLink, useLocation } from 'react-router-dom'
import { MessageCircle, Radio, Radar, Settings } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

const tabs = [
  { to: '/', icon: MessageCircle, label: 'Chat' },
  { to: '/signals', icon: Radio, label: 'Signals' },
  { to: '/tracking', icon: Radar, label: 'Tracking' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function BottomTabBar() {
  const location = useLocation()

  return (
    <nav className="flex items-center justify-around border-t border-[var(--color-border)] bg-[var(--color-panel)] h-14 shrink-0 pb-[env(safe-area-inset-bottom)]">
      {tabs.map(({ to, icon: Icon, label }) => {
        const active = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
        return (
          <NavLink key={to} to={to}
            className={cn(
              'flex flex-col items-center justify-center gap-0.5 flex-1 h-full text-[11px]',
              active ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'
            )}>
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
