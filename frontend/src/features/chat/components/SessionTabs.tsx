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

  useEffect(() => {
    activeTabRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'nearest',
    })
  }, [activeSessionId, sessions.length, wrap])

  const scrollByDelta = (delta: number) => {
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.scrollBy({ left: delta, behavior: 'smooth' })
  }

  const renderSessionItems = (truncateTitle: boolean) => (
    <>
      {sessions.map((session) => (
        <button
          key={session.id}
          ref={session.id === activeSessionId ? activeTabRef : null}
          onClick={() => switchSession(session.id)}
          className={cn(
            'group flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1.5 text-[11px] sm:px-3 sm:text-xs transition-colors',
            session.id === activeSessionId
              ? 'bg-[var(--color-panel-alt)] text-[var(--color-text)]'
              : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
          )}
          title={session.title}
        >
          <span className={cn(truncateTitle ? 'max-w-[120px] truncate' : 'max-w-none')}>{session.title}</span>
          {sessions.length > 1 && (
            <span
              onClick={(event) => {
                event.stopPropagation()
                deleteSession(session.id)
              }}
              className="opacity-0 transition-opacity group-hover:opacity-60 hover:opacity-100"
            >
              <X size={12} />
            </span>
          )}
        </button>
      ))}
    </>
  )

  if (wrap) {
    return (
      <div className={cn('flex min-w-0 w-full items-start gap-1.5', className)}>
        <div ref={viewportRef} className="min-w-0 flex-1 max-h-[88px] overflow-y-auto pr-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {renderSessionItems(true)}
          </div>
        </div>
        <button
          onClick={() => createSession()}
          className="shrink-0 rounded-full border border-[var(--color-border)] p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
          title="新建会话"
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
        onClick={() => scrollByDelta(-260)}
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
        onClick={() => scrollByDelta(260)}
        className="h-7 w-7 shrink-0 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        title="向右查看会话"
        aria-label="向右查看会话"
      >
        <ChevronRight size={14} className="mx-auto" />
      </button>

      <button
        onClick={() => createSession()}
        className="h-8 w-8 shrink-0 rounded-full border border-[var(--color-border)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
        title="新建会话"
      >
        <Plus size={16} className="mx-auto" />
      </button>
    </div>
  )
}
