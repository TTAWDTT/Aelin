import { useLocation, useNavigate, NavLink } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { useChatStore } from '@/features/chat/stores/chatStore'
import { useChatI18n } from '@/features/chat/chatI18n'
import SettingsPage from '@/app/routes/SettingsPage'
import { ChevronLeft, ChevronRight, Plus, Settings as SettingsIcon, SunMoon, X } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { MODULE_NAV_ITEMS } from './moduleNav'

export function NavigationRail() {
  const location = useLocation()
  const navigate = useNavigate()
  const {
    theme,
    navRailExpanded,
    sessionsVisible,
    setTheme,
    setNavRailExpanded,
    toggleNavRailExpanded,
    setSessionsVisible,
    applyTheme,
  } = useLayoutStore()
  const { sessions, activeSessionId, switchSession, createSession, deleteSession } = useChatStore()
  const { t } = useChatI18n()

  const handleThemeToggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
  }

  const handleRailToggle = () => {
    toggleNavRailExpanded()
  }

  const handleChatNavClick = () => {
    const onChatRoute = location.pathname === '/'
    if (!navRailExpanded) {
      setNavRailExpanded(true)
      setSessionsVisible(true)
    } else {
      setSessionsVisible(!sessionsVisible)
    }
    if (!onChatRoute) {
      navigate('/')
    }
  }

  const showSessions = navRailExpanded && sessionsVisible
  const hasSessions = sessions.length > 0

  const handleChatNewSession = () => {
    if (!navRailExpanded) {
      setNavRailExpanded(true)
    }
    setSessionsVisible(true)
    createSession()
    if (location.pathname !== '/') {
      navigate('/')
    }
  }

  return (
    <nav
      className={cn(
        'aelin-sidebar flex shrink-0 flex-col py-5 transition-[width,padding] duration-300',
        navRailExpanded ? 'px-3.5' : 'items-center px-1'
      )}
      style={{ width: navRailExpanded ? 224 : 74 }}
    >
      <div className={cn('mb-6 flex', navRailExpanded ? 'items-center gap-3 px-2' : 'justify-center')}>
        <AelinAvatar size="md" pulse title="Aelin" />
        {navRailExpanded && (
          <div className="min-w-0">
            <div className="truncate font-heading text-[15px] font-semibold text-[var(--color-text)]">Aelin</div>
            <div className="truncate text-[11px] text-[var(--color-text-muted)]">私人信息管家</div>
          </div>
        )}
      </div>

      <div className={cn('flex flex-1 flex-col gap-2', navRailExpanded && 'w-full')}>
        <div id="aelin-nav-rail-links" className={cn('flex flex-col gap-1.5', navRailExpanded && 'w-full')}>
          {MODULE_NAV_ITEMS.map(({ to, icon: Icon, label, match }) => {
            if (to === '/settings') return null
            const active = match ? match(location.pathname) : location.pathname.startsWith(to)
            const isChat = to === '/'
            const sharedClasses = cn(
              'aelin-rail-nav-item relative flex h-12 items-center rounded-[22px] border transition-all duration-150',
              navRailExpanded ? 'w-full gap-3 px-3.5 justify-start' : 'w-12 justify-center self-center',
              active
                ? 'border-[var(--color-nav-active-border)] bg-[var(--color-nav-active-bg)] text-[var(--color-nav-active-text)] shadow-[0_16px_35px_-26px_var(--color-nav-active-shadow)]'
                : 'border-transparent text-[var(--color-text-muted)] hover:border-[var(--color-border)] hover:bg-[var(--color-accent-soft)] hover:-translate-y-[1px] hover:shadow-[0_10px_24px_-20px_rgba(0,0,0,0.75)]'
            )

            if (isChat) {
              const expanded = showSessions && active && navRailExpanded && hasSessions
              if (navRailExpanded) {
                return (
                  <div
                    key={to}
                    className={cn(
                      'relative flex flex-1 min-h-0 flex-col px-1.5 py-1.5 transition-all duration-200',
                      active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-muted)]'
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleChatNavClick}
                        title={label}
                        aria-label={label}
                        aria-expanded={expanded}
                        className={cn(
                          'flex flex-1 items-center gap-2 overflow-hidden text-left rounded-[999px] px-2 py-1 transition-colors duration-150',
                          expanded
                            ? 'bg-[var(--color-accent-soft)] text-[var(--color-text)]'
                            : 'hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-text)]'
                        )}
                      >
                        <Icon size={18} />
                        <span className="text-sm font-medium truncate">
                          {label}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={handleChatNewSession}
                        title={t('session.new')}
                        aria-label={t('session.new')}
                        className="ml-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-text)]"
                      >
                        <Plus size={12} />
                      </button>
                    </div>

                    {hasSessions && (
                      <div
                        className={cn(
                          'mt-1.5 min-h-0 flex-1 overflow-hidden transition-all duration-200 ease-out',
                          showSessions
                            ? 'opacity-100 translate-y-0'
                            : 'opacity-0 -translate-y-1 pointer-events-none'
                        )}
                      >
                        <div className="h-full overflow-y-auto pr-0.5 pt-0.5">
                          <div className="flex flex-col gap-0.5">
                            {sessions.map((session) => (
                              <div
                                key={session.id}
                                className="group relative"
                              >
                                <button
                                  type="button"
                                  onClick={() => switchSession(session.id)}
                                  className={cn(
                                    'flex w-full items-center justify-between rounded-[999px] px-2.5 py-1.5 text-[13px] font-medium transition-all duration-150',
                                    session.id === activeSessionId
                                      ? 'bg-[color-mix(in_srgb,var(--color-panel-alt)_56%,var(--color-panel)_44%)] text-[var(--color-text)] shadow-[0_12px_32px_-22px_rgba(0,0,0,0.85)]'
                                      : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-text)] hover:-translate-y-[1px] hover:shadow-[0_10px_24px_-20px_rgba(0,0,0,0.75)]'
                                  )}
                                  aria-label={t('session.switch', { title: session.title })}
                                  title={session.title}
                                >
                                  <span className="mr-1 min-w-0 flex-1 truncate text-left">{session.title}</span>
                                  {sessions.length > 1 && (
                                    <span className="ml-1 inline-flex items-center opacity-0 transition-opacity group-hover:opacity-70 group-focus-within:opacity-70">
                                      <X
                                        size={10}
                                        className="cursor-pointer"
                                        onClick={(event) => {
                                          event.stopPropagation()
                                          deleteSession(session.id)
                                        }}
                                        aria-label={t('session.delete', { title: session.title })}
                                      />
                                    </span>
                                  )}
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              }

              // Collapsed rail: keep a single round icon button.
              return (
                <button
                  key={to}
                  type="button"
                  onClick={handleChatNavClick}
                  title={label}
                  aria-label={label}
                  aria-expanded={expanded}
                  className={sharedClasses}
                >
                  <Icon size={18} />
                </button>
              )
            }

            return (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                title={label}
                aria-label={label}
                className={sharedClasses}
              >
                <Icon size={18} />
                {navRailExpanded && <span className="text-sm font-medium">{label}</span>}
              </NavLink>
            )
          })}
        </div>

        {/* sessions 列表现在完全挂在 Chat 导航项内部，这里不再额外渲染独立卡片 */}
      </div>

      <div className={cn('mt-auto flex flex-col gap-3', navRailExpanded ? 'w-full px-1' : 'items-center')}>
        <Dialog.Root>
          <Dialog.Trigger asChild>
            <button
              type="button"
              title={navRailExpanded ? '设置' : 'Settings'}
              aria-label={navRailExpanded ? '设置' : 'Settings'}
              className="aelin-rail-control"
            >
              <SettingsIcon size={18} />
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 data-[state=closed]:opacity-0 data-[state=open]:opacity-100 transition-opacity" />
            <Dialog.Content
              className={cn(
                'fixed inset-y-6 right-6 z-50 flex w-[min(520px,100%-2.5rem)] max-w-full flex-col rounded-[24px] bg-[var(--color-panel)] shadow-[0_20px_60px_rgba(0,0,0,0.45)]',
                'outline-none'
              )}
            >
              <div className="flex items-center justify-between px-5 py-3 border-b border-[color-mix(in_srgb,var(--color-border)_68%,transparent)]">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-[14px] bg-[var(--color-panel-alt)]">
                    <SettingsIcon size={16} />
                  </div>
                  <Dialog.Title className="text-sm font-semibold text-[var(--color-text)]">
                    {navRailExpanded ? '设置' : 'Settings'}
                  </Dialog.Title>
                </div>
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="aelin-rail-control h-8 w-8"
                    aria-label="关闭设置"
                  >
                    <X size={14} />
                  </button>
                </Dialog.Close>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <SettingsPage />
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>

        <button
          onClick={handleThemeToggle}
          title="切换深浅色"
          aria-label="切换深浅色"
          className="aelin-rail-control"
        >
          <SunMoon size={18} />
        </button>
        <button
          onClick={handleRailToggle}
          title={navRailExpanded ? '收起左栏' : '展开左栏'}
          aria-label={navRailExpanded ? '收起左栏' : '展开左栏'}
          aria-expanded={navRailExpanded}
          aria-controls="aelin-nav-rail-links"
          className="aelin-rail-control"
        >
          {navRailExpanded ? <ChevronLeft size={22} /> : <ChevronRight size={22} />}
        </button>
      </div>
    </nav>
  )
}
