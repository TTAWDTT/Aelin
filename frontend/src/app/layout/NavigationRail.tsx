import { NavLink, useLocation } from 'react-router-dom'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { SunMoon } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { MODULE_NAV_ITEMS } from './moduleNav'

export function NavigationRail() {
  const location = useLocation()
  const { theme, setTheme, applyTheme } = useLayoutStore()

  const handleThemeToggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
  }

  return (
    <nav className="aelin-sidebar flex shrink-0 flex-col items-center py-4">
      <AelinAvatar size="md" pulse className="mb-7" title="Aelin" />

      <div className="flex flex-1 flex-col gap-1.5">
        {MODULE_NAV_ITEMS.map(({ to, icon: Icon, label, match }) => {
          const active = match ? match(location.pathname) : location.pathname.startsWith(to)
          return (
            <NavLink
              key={to}
              to={to}
              title={label}
              className={cn(
                'relative flex h-11 w-11 items-center justify-center rounded-2xl border border-transparent transition-colors',
                active ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              )}
            >
              <Icon size={18} />
            </NavLink>
          )
        })}
      </div>

      <div className="mt-auto flex flex-col gap-1.5">
        <button
          onClick={handleThemeToggle}
          title="切换深浅色"
          className="flex h-11 w-11 items-center justify-center rounded-2xl text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        >
          <SunMoon size={18} />
        </button>
      </div>
    </nav>
  )
}
