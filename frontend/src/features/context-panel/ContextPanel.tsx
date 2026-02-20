import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
import { agentApi } from '@/shared/api/agent'
import { cn } from '@/shared/utils/cn'
import { relativeTime, severityColor } from '@/shared/utils/format'
import { Brain, Crosshair, CheckSquare, Bell, Plus, Trash2, X } from 'lucide-react'
import toast from 'react-hot-toast'
import type { AelinTodoItem, AelinNotificationItem, AgentMemoryNoteOut, AgentFocusItemOut, AelinMemoryLayerItem } from '@/shared/api/types'

type Tab = 'memory' | 'focus' | 'todos' | 'notif'

interface Props { onClose?: () => void }

export function ContextPanel({ onClose }: Props = {}) {
  const [tab, setTab] = useState<Tab>('focus')

  const tabs: { key: Tab; label: string; icon: typeof Brain }[] = [
    { key: 'focus', label: '焦点', icon: Crosshair },
    { key: 'memory', label: '记忆', icon: Brain },
    { key: 'todos', label: '待办', icon: CheckSquare },
    { key: 'notif', label: '通知', icon: Bell },
  ]

  return (
    <div className="flex flex-col h-full bg-[var(--color-panel)] border-l border-[var(--color-border)]">
      {/* Tabs */}
      <div className="flex items-center border-b border-[var(--color-border)] shrink-0">
        {onClose && (
          <button onClick={onClose} className="p-2 ml-1 rounded-md hover:bg-[var(--color-accent-soft)]">
            <X size={16} />
          </button>
        )}
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={cn('flex-1 flex items-center justify-center gap-1 py-2.5 text-[11px] font-medium transition-colors',
              tab === t.key ? 'text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
            )}>
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3">
        {tab === 'focus' && <FocusContent />}
        {tab === 'memory' && <MemoryContent />}
        {tab === 'todos' && <TodosContent />}
        {tab === 'notif' && <NotifContent />}
      </div>
    </div>
  )
}

/* ─── Focus ─── */
function FocusContent() {
  const { data } = useQuery({
    queryKey: ['context'],
    queryFn: () => aelinApi.context(),
    refetchInterval: 60_000,
  })

  const focusItems = data?.focus_items ?? []
  const brief = data?.daily_brief

  return (
    <div className="space-y-4">
      {brief && (
        <div className="bg-[var(--color-accent-soft)] rounded-xl p-3 text-xs">
          <div className="font-medium mb-1" style={{ fontFamily: 'var(--font-heading)' }}>📋 每日简报</div>
          <p className="text-[var(--color-text-muted)] leading-relaxed">{brief.summary}</p>
        </div>
      )}

      <div className="text-[11px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider">重点关注</div>
      {focusItems.length === 0 && <div className="text-xs text-[var(--color-text-muted)]">暂无焦点事项</div>}
      {focusItems.map((item: AgentFocusItemOut, i: number) => (
        <div key={i} className="border border-[var(--color-border)] rounded-lg p-2.5 space-y-1">
          <div className="text-[11px] text-[var(--color-text-muted)]">{item.source_label} · {item.sender}</div>
          <div className="text-xs font-medium">{item.title}</div>
          <div className="text-[11px] text-[var(--color-text-muted)]">{relativeTime(item.received_at)}</div>
        </div>
      ))}

      {data?.pin_recommendations && data.pin_recommendations.length > 0 && (
        <>
          <div className="text-[11px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider mt-4">关注推荐</div>
          {data.pin_recommendations.map((r, i) => (
            <div key={i} className="text-xs border border-dashed border-[var(--color-border)] rounded-lg p-2.5">
              <span className="font-medium">{r.display_name}</span>
              <span className="text-[var(--color-text-muted)]"> · {r.reasons.join(', ')}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

/* ─── Memory ─── */
function MemoryContent() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['context'], queryFn: () => aelinApi.context(), refetchInterval: 60_000 })
  const [newNote, setNewNote] = useState('')

  const addNote = useMutation({
    mutationFn: (content: string) => agentApi.addNote(content),
    onSuccess: () => { setNewNote(''); toast.success('已添加'); qc.invalidateQueries({ queryKey: ['context'] }) },
  })

  const delNote = useMutation({
    mutationFn: (id: number) => agentApi.deleteNote(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['context'] }),
  })

  const notes = data?.notes ?? []
  const layers = data?.memory_layers

  return (
    <div className="space-y-4">
      {/* Add Note */}
      <div className="flex gap-2">
        <input value={newNote} onChange={e => setNewNote(e.target.value)} placeholder="添加笔记…"
          className="flex-1 px-2.5 py-1.5 text-xs rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]"
          onKeyDown={e => e.key === 'Enter' && newNote.trim() && addNote.mutate(newNote.trim())} />
        <button onClick={() => newNote.trim() && addNote.mutate(newNote.trim())} disabled={!newNote.trim()}
          className="p-1.5 rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] disabled:opacity-50">
          <Plus size={14} />
        </button>
      </div>

      {/* Notes */}
      <div className="text-[11px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider">笔记 ({notes.length})</div>
      {notes.map((note: AgentMemoryNoteOut) => (
        <div key={note.id} className="flex items-start gap-2 text-xs border border-[var(--color-border)] rounded-lg p-2.5">
          <div className="flex-1">
            <div className="text-[var(--color-text-muted)] mb-0.5">{note.kind} · {relativeTime(note.updated_at)}</div>
            <div>{note.content}</div>
          </div>
          <button onClick={() => delNote.mutate(note.id)} className="p-0.5 rounded hover:bg-[var(--color-accent-soft)] shrink-0">
            <Trash2 size={12} className="text-[var(--color-text-muted)]" />
          </button>
        </div>
      ))}

      {/* Memory Layers */}
      {layers && (
        <>
          {renderLayer('事实', layers.facts)}
          {renderLayer('偏好', layers.preferences)}
          {renderLayer('进行中', layers.in_progress)}
        </>
      )}
    </div>
  )
}

function renderLayer(title: string, items: AelinMemoryLayerItem[]) {
  if (!items.length) return null
  return (
    <div className="mt-3">
      <div className="text-[11px] text-[var(--color-text-muted)] font-medium uppercase tracking-wider">{title} ({items.length})</div>
      <div className="mt-1 space-y-1.5">
        {items.map(item => (
          <div key={item.id} className="text-xs bg-[var(--color-accent-soft)] rounded-lg px-2.5 py-1.5">
            <span className="font-medium">{item.title}</span>
            {item.detail && <span className="text-[var(--color-text-muted)]"> — {item.detail}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ─── Todos ─── */
function TodosContent() {
  const qc = useQueryClient()
  const { data: todos = [] } = useQuery({ queryKey: ['todos'], queryFn: agentApi.todos })
  const [newTitle, setNewTitle] = useState('')

  const create = useMutation({
    mutationFn: (title: string) => agentApi.createTodo({ title }),
    onSuccess: () => { setNewTitle(''); qc.invalidateQueries({ queryKey: ['todos'] }) },
  })

  const toggle = useMutation({
    mutationFn: (t: AelinTodoItem) => agentApi.updateTodo(t.id, { done: !t.done }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['todos'] }),
  })

  const del = useMutation({
    mutationFn: (id: number) => agentApi.deleteTodo(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['todos'] }),
  })

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="添加待办…"
          className="flex-1 px-2.5 py-1.5 text-xs rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]"
          onKeyDown={e => e.key === 'Enter' && newTitle.trim() && create.mutate(newTitle.trim())} />
        <button onClick={() => newTitle.trim() && create.mutate(newTitle.trim())} disabled={!newTitle.trim()}
          className="p-1.5 rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] disabled:opacity-50">
          <Plus size={14} />
        </button>
      </div>

      {(todos as AelinTodoItem[]).map(t => (
        <div key={t.id} className="flex items-center gap-2 text-xs">
          <button onClick={() => toggle.mutate(t)}
            className={cn('w-4 h-4 rounded border shrink-0 flex items-center justify-center',
              t.done ? 'bg-[var(--color-accent)] border-[var(--color-accent)] text-[var(--color-bg)]' : 'border-[var(--color-border)]')}>
            {t.done && '✓'}
          </button>
          <span className={cn('flex-1', t.done && 'line-through text-[var(--color-text-muted)]')}>{t.title}</span>
          {t.priority && t.priority !== 'normal' && (
            <span className="text-[10px] text-[var(--color-orange)]">{t.priority}</span>
          )}
          <button onClick={() => del.mutate(t.id)} className="p-0.5 rounded hover:bg-[var(--color-accent-soft)]">
            <X size={12} className="text-[var(--color-text-muted)]" />
          </button>
        </div>
      ))}

      {(todos as AelinTodoItem[]).length === 0 && (
        <div className="text-xs text-[var(--color-text-muted)] text-center py-4">暂无待办</div>
      )}
    </div>
  )
}

/* ─── Notifications ─── */
function NotifContent() {
  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => aelinApi.notifications(),
    refetchInterval: 30_000,
  })

  const items: AelinNotificationItem[] = data?.items ?? []

  return (
    <div className="space-y-2">
      {items.length === 0 && <div className="text-xs text-[var(--color-text-muted)] text-center py-4">暂无通知</div>}
      {items.map((n, i) => (
        <div key={n.id ?? i} className={cn('border rounded-lg p-2.5 text-xs',
          n.level === 'critical' ? 'border-[var(--color-danger)] bg-[color-mix(in_srgb,var(--color-danger)_6%,transparent)]'
          : n.level === 'warning' ? 'border-[var(--color-orange)] bg-[color-mix(in_srgb,var(--color-orange)_6%,transparent)]'
          : 'border-[var(--color-border)]'
        )}>
          <div className="font-medium">{n.title}</div>
          {n.detail && <div className="text-[var(--color-text-muted)] mt-0.5">{n.detail}</div>}
          <div className="text-[10px] text-[var(--color-text-muted)] mt-1">
            {n.source && <span>{n.source} · </span>}
            {n.ts && <span>{relativeTime(n.ts)}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}
