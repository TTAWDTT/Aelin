import { useChatStore } from '../stores/chatStore'
import { Plus, X } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export function SessionTabs({ className }: { className?: string }) {
  const { sessions, activeSessionId, switchSession, createSession, deleteSession } = useChatStore()

  return (
    <div className={cn('flex w-full items-center gap-1.5 overflow-x-auto', className)}>
        {sessions.map(s => (
          <button
            key={s.id}
            onClick={() => switchSession(s.id)}
            className={cn(
              'group flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-xs transition-colors',
              s.id === activeSessionId
                ? 'bg-[var(--color-panel-alt)] text-[var(--color-text)]'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
            )}
          >
            <span className="max-w-[140px] truncate">{s.title}</span>
            {sessions.length > 1 && (
              <span
                onClick={(e) => {
                  e.stopPropagation()
                  deleteSession(s.id)
                }}
                className="opacity-0 transition-opacity group-hover:opacity-60 hover:opacity-100"
              >
                <X size={12} />
              </span>
            )}
          </button>
        ))}
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
