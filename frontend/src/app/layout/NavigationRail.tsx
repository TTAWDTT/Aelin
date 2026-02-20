import { NavLink, useLocation } from 'react-router-dom'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { useNotifStore } from '@/shared/stores/notifStore'
import { MessageCircle, Radio, Radar, Settings, PanelRight, SunMoon } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'

const mainNav = [
  { to: '/', icon: MessageCircle, label: 'Chat' },
  { to: '/signals', icon: Radio, label: 'Signals' },
  { to: '/tracking', icon: Radar, label: 'Tracking' },
]

export function NavigationRail({ compact }: { compact?: boolean }) {
  const location = useLocation()
  const { toggleContextPanel, contextPanelOpen, theme, setTheme, applyTheme } = useLayoutStore()
  const unread = useNotifStore(s => s.unreadCount)
  const hasUnread = unread > 0

  const handleThemeToggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
  }

  return (
    <nav className={cn(
      'flex flex-col items-center border-r border-[var(--color-border)] bg-[var(--color-bg)] py-4 shrink-0',
      compact ? 'w-16' : 'w-[76px]'
    )}>
      <AelinAvatar size="sm" className="mb-6" title="Aelin" />

      <div className="flex flex-col gap-1 flex-1">
        {mainNav.map(({ to, icon: Icon, label }) => {
          const active = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)
          return (
            <NavLink key={to} to={to} title={label}
              className={cn(
                'relative flex h-10 w-10 items-center justify-center rounded-xl transition-colors',
                active ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              )}
            >
              <Icon size={20} />
              {to === '/signals' && hasUnread && (
                <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[var(--color-text)]" />
              )}
            </NavLink>
          )
        })}
      </div>

      <div className="flex flex-col gap-1 mt-auto">
        <button onClick={toggleContextPanel} title="上下文"
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-xl transition-colors',
            contextPanelOpen ? 'bg-[var(--color-accent-soft)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
          )}>
          <PanelRight size={20} />
        </button>
        <button
          onClick={handleThemeToggle}
          title="切换深浅色"
          className="flex h-10 w-10 items-center justify-center rounded-xl text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        >
          <SunMoon size={18} />
        </button>
        <NavLink to="/settings" title="Settings"
          className={({ isActive }) => cn(
            'flex h-10 w-10 items-center justify-center rounded-xl transition-colors',
            isActive ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
          )}>
          <Settings size={20} />
        </NavLink>
      </div>
    </nav>
  )
}
