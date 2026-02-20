import { useChatStore } from '../stores/chatStore'
import { Plus, X } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export function SessionTabs() {
  const { sessions, activeSessionId, switchSession, createSession, deleteSession } = useChatStore()

  return (
    <div className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-panel)]">
      <div className="mx-auto flex w-full max-w-4xl items-center gap-1 overflow-x-auto px-3 py-2">
        {sessions.map(s => (
          <button key={s.id} onClick={() => switchSession(s.id)}
            className={cn(
              'group flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm whitespace-nowrap transition-colors',
              s.id === activeSessionId
                ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
            )}>
            <span className="max-w-[140px] truncate">{s.title}</span>
            {sessions.length > 1 && (
              <span onClick={(e) => { e.stopPropagation(); deleteSession(s.id) }}
                className="opacity-0 transition-opacity group-hover:opacity-60 hover:opacity-100">
                <X size={12} />
              </span>
            )}
          </button>
        ))}
        <button onClick={() => createSession()}
          className="shrink-0 rounded-xl p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]">
          <Plus size={16} />
        </button>
      </div>
    </div>
  )
}
