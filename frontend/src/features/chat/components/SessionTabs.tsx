import { useEffect, useRef } from 'react'
import { ChevronLeft, ChevronRight, Plus, X } from 'lucide-react'
import { useChatStore } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'

interface SessionTabsProps {
  className?: string
  wrap?: boolean
}

export function SessionTabs({ className, wrap = false }: SessionTabsProps) {
  const { sessions, activeSessionId, switchSession, createSession, deleteSession } = useChatStore()
  const activeTabRef = useRef<HTMLButtonElement | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const scrollBehavior: ScrollBehavior = prefersReducedMotion ? 'auto' : 'smooth'

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
      {sessions.map((session) => (
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
            aria-label={`切换会话：${session.title}`}
            title={session.title}
          >
            <span className={cn('min-w-0 text-left', truncateTitle && 'max-w-[120px] truncate')}>{session.title}</span>
          </button>
          {sessions.length > 1 && (
            <button
              type="button"
              onClick={() => {
                deleteSession(session.id)
              }}
              className="absolute right-1 top-1/2 z-10 -translate-y-1/2 rounded-full p-0.5 opacity-0 transition-opacity pointer-events-none group-hover:pointer-events-auto group-hover:opacity-60 group-focus-within:pointer-events-auto group-focus-within:opacity-60 hover:opacity-100"
              aria-label={`删除会话：${session.title}`}
              title="删除会话"
            >
              <X size={12} />
            </button>
          )}
        </div>
      ))}
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
          title="新建会话"
          aria-label="新建会话"
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
        title="向左查看会话"
        aria-label="向左查看会话"
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
        title="向右查看会话"
        aria-label="向右查看会话"
      >
        <ChevronRight size={14} className="mx-auto" />
      </button>

      <button
        type="button"
        onClick={() => createSession()}
        className="h-8 w-8 shrink-0 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        title="新建会话"
        aria-label="新建会话"
      >
        <Plus size={16} className="mx-auto" />
      </button>
    </div>
  )
}
