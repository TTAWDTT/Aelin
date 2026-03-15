import { NavLink, useLocation } from 'react-router-dom'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { ChevronLeft, ChevronRight, SunMoon } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { MODULE_NAV_ITEMS } from './moduleNav'

export function NavigationRail() {
  const location = useLocation()
  const { theme, navRailExpanded, setTheme, setNavRailExpanded, applyTheme } = useLayoutStore()

  const handleThemeToggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
  }

  const handleRailToggle = () => {
    setNavRailExpanded(!navRailExpanded)
  }

  return (
    <nav
      className={cn(
        'aelin-sidebar flex shrink-0 flex-col py-5 transition-[width,padding] duration-300',
        navRailExpanded ? 'px-3.5' : 'items-center px-1'
      )}
      style={{ width: navRailExpanded ? 224 : 74 }}
    >
      <div className={cn('mb-8 flex', navRailExpanded ? 'items-center gap-3 px-2' : 'justify-center')}>
        <AelinAvatar size="md" pulse title="Aelin" />
        {navRailExpanded && (
          <div className="min-w-0">
            <div className="truncate font-heading text-[15px] font-semibold text-[var(--color-text)]">Aelin</div>
            <div className="truncate text-[11px] text-[var(--color-text-muted)]">私人信息管家</div>
          </div>
        )}
      </div>

      <div className={cn('flex flex-1 flex-col gap-1.5', navRailExpanded && 'w-full')}>
        {MODULE_NAV_ITEMS.map(({ to, icon: Icon, label, match }) => {
          const active = match ? match(location.pathname) : location.pathname.startsWith(to)
          return (
            <NavLink
              key={to}
              to={to}
              title={label}
              className={cn(
                'aelin-rail-nav-item relative flex h-12 items-center rounded-[22px] border transition-colors',
                navRailExpanded ? 'w-full gap-3 px-3.5 justify-start' : 'w-12 justify-center self-center',
                active
                  ? 'border-[var(--color-nav-active-border)] bg-[var(--color-nav-active-bg)] text-[var(--color-nav-active-text)] shadow-[0_16px_35px_-26px_var(--color-nav-active-shadow)]'
                  : 'border-transparent text-[var(--color-text-muted)] hover:border-[var(--color-border)] hover:bg-[var(--color-accent-soft)]'
              )}
            >
              <Icon size={18} />
              {navRailExpanded && <span className="text-sm font-medium">{label}</span>}
            </NavLink>
          )
        })}
      </div>

      <div className={cn('mt-auto flex flex-col gap-3', navRailExpanded ? 'w-full px-1' : 'items-center')}>
        <button
          onClick={handleRailToggle}
          title={navRailExpanded ? '收起左栏' : '展开左栏'}
          aria-label={navRailExpanded ? '收起左栏' : '展开左栏'}
          className="aelin-rail-control"
        >
          {navRailExpanded ? <ChevronLeft size={22} /> : <ChevronRight size={22} />}
        </button>
        <button
          onClick={handleThemeToggle}
          title="切换深浅色"
          aria-label="切换深浅色"
          className="aelin-rail-control"
        >
          <SunMoon size={18} />
        </button>
      </div>
    </nav>
  )
}
