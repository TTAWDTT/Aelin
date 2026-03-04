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
  const activeTabRef = useRef<HTMLDivElement | null>(null)
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
        <div
          key={session.id}
          ref={session.id === activeSessionId ? activeTabRef : null}
          role="button"
          tabIndex={0}
          onClick={() => switchSession(session.id)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              switchSession(session.id)
            }
          }}
          className={cn(
            'group flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1.5 text-[11px] sm:px-3 sm:text-xs transition-colors',
            session.id === activeSessionId
              ? 'bg-[var(--color-panel-alt)] text-[var(--color-text)]'
              : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
          )}
          aria-label={`切换会话：${session.title}`}
          title={session.title}
        >
          <span className={cn('min-w-0 text-left', truncateTitle && 'max-w-[120px] truncate')}>{session.title}</span>
          {sessions.length > 1 && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                deleteSession(session.id)
              }}
              className="shrink-0 opacity-0 transition-opacity group-hover:opacity-60 group-focus-within:opacity-60 hover:opacity-100"
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
        <div ref={viewportRef} className="min-w-0 flex-1 max-h-[88px] overflow-y-auto pr-1">
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
