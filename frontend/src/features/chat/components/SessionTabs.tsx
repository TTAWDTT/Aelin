import { useEffect, useRef } from 'react'
import { ChevronLeft, ChevronRight, Plus, X } from 'lucide-react'
import { useChatStore } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'

interface SessionTabsProps {
  className?: string
  wrap?: boolean
}

export function SessionTabs({ className, wrap = false }: SessionTabsProps) {
  const { sessions, activeSessionId, switchSession, createSession, deleteSession, sessionRuntimeById } = useChatStore()
  const activeTabRef = useRef<HTMLButtonElement | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const scrollBehavior: ScrollBehavior = prefersReducedMotion ? 'auto' : 'smooth'
  const { t } = useChatI18n()

  useEffect(() => {
    activeTabRef.current?.scrollIntoView({
      behavior: scrollBehavior,
      block: 'nearest',
      inline: 'nearest',
    })
  }, [activeSessionId, sessions.length, wrap, scrollBehavior])

  const scrollByDirection = (direction: -1 | 1) => {
    const viewport = viewportRef.current
    if (!viewport) return
    const delta = Math.max(160, Math.round(viewport.clientWidth * 0.75)) * direction
    viewport.scrollBy({ left: delta, behavior: scrollBehavior })
  }

  const renderSessionItems = (truncateTitle: boolean) => (
    <>
      {sessions.map((session) => {
        const runtime = sessionRuntimeById[session.id]
        const isRunning = runtime?.phase === 'streaming' || runtime?.phase === 'background'
        const sessionTitle = isRunning ? `${session.title} · ${t('session.running')}` : session.title

        return (
        <div
          key={session.id}
          className="group relative shrink-0"
        >
          <button
            type="button"
            ref={session.id === activeSessionId ? activeTabRef : null}
            onClick={() => switchSession(session.id)}
            className={cn(
              'flex items-center whitespace-nowrap rounded-full px-2.5 py-1.5 text-[11px] sm:px-3 sm:text-xs transition-colors',
              sessions.length > 1 && 'pr-9',
              session.id === activeSessionId
                ? 'bg-black text-white'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
            )}
            aria-label={t('session.switch', { title: session.title })}
            title={sessionTitle}
          >
            <span className="flex min-w-0 items-center gap-1.5">
              {isRunning && (
                <span
                  className={cn(
                    'h-1.5 w-1.5 shrink-0 rounded-full',
                    session.id === activeSessionId ? 'bg-current animate-pulse' : 'bg-[var(--color-accent)] animate-pulse',
                  )}
                  aria-hidden="true"
                />
              )}
              <span
                className={cn(
                  'min-w-0 text-left',
                  truncateTitle && 'max-w-[120px] truncate'
                )}
              >
                {session.title}
              </span>
            </span>
          </button>
          {sessions.length > 1 && (
            <button
              type="button"
              onClick={() => {
                deleteSession(session.id)
              }}
              className="absolute right-1 top-1/2 z-10 -translate-y-1/2 rounded-full p-0.5 opacity-0 transition-opacity pointer-events-none group-hover:pointer-events-auto group-hover:opacity-60 group-focus-within:pointer-events-auto group-focus-within:opacity-60 hover:opacity-100"
              aria-label={t('session.delete', { title: session.title })}
              title={t('session.delete', { title: session.title })}
            >
              <X size={12} />
            </button>
          )}
        </div>
        )
      })}
    </>
  )

  if (wrap) {
    return (
      <div className={cn('flex min-w-0 w-full items-start gap-1.5', className)}>
        <div ref={viewportRef} className="min-w-0 flex-1 max-h-24 overflow-y-auto pr-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {renderSessionItems(true)}
          </div>
        </div>
        <button
          type="button"
          onClick={() => createSession()}
          className="shrink-0 rounded-full border border-[var(--color-border)] p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
          title={t('session.new')}
          aria-label={t('session.new')}
        >
          <Plus size={16} />
        </button>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'grid min-w-0 w-full items-center gap-1.5 [grid-template-columns:auto_minmax(0,1fr)_auto_auto]',
        className
      )}
    >
      <button
        type="button"
        onClick={() => scrollByDirection(-1)}
        className="h-7 w-7 shrink-0 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        title={t('session.nav.prev')}
        aria-label={t('session.nav.prev')}
      >
        <ChevronLeft size={14} className="mx-auto" />
      </button>

      <div ref={viewportRef} className="min-w-0 overflow-x-auto">
        <div className="flex w-max min-w-0 items-center gap-1.5 pr-1">
          {renderSessionItems(false)}
        </div>
      </div>

      <button
        type="button"
        onClick={() => scrollByDirection(1)}
        className="h-7 w-7 shrink-0 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        title={t('session.nav.next')}
        aria-label={t('session.nav.next')}
      >
        <ChevronRight size={14} className="mx-auto" />
      </button>

      <button
        type="button"
        onClick={() => createSession()}
        className="h-8 w-8 shrink-0 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        title={t('session.new')}
        aria-label={t('session.new')}
      >
        <Plus size={16} className="mx-auto" />
      </button>
    </div>
  )
}
