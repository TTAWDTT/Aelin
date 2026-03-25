import { useEffect, useMemo, useState } from 'react'
import {
  Bot,
  CheckCircle2,
  CircleDashed,
  Hammer,
  PanelRightOpen,
  Workflow,
  XCircle,
} from 'lucide-react'
import type { DeepAgentsExecutionEvent } from '@/shared/api/types'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'
import { extractToolCalls } from '../executionEventUtils'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import { ProviderIcon } from './ProviderIcon'

interface ExecutionPaneProps {
  executionEvents: DeepAgentsExecutionEvent[]
  isStreaming: boolean
  compact?: boolean
}

type ExecutionTab = 'timeline' | 'tools'

export function ExecutionPane({
  executionEvents,
  isStreaming,
  compact = false,
}: ExecutionPaneProps) {
  const { t } = useChatI18n()
  const { open } = useExecutionPaneStore()
  const hasExecution = executionEvents.length > 0
  const toolCalls = useMemo(
    () => extractToolCalls(executionEvents),
    [executionEvents],
  )
  const [tab, setTab] = useState<ExecutionTab>('timeline')

  useEffect(() => {
    if (!hasExecution) return
    setTab('timeline')
  }, [hasExecution])

  const label = hasExecution ? t('trace.executionPane.title') : t('trace.executionPane.empty')

  return (
    <aside
      aria-label={label}
      className={cn(
        'flex shrink-0 flex-col overflow-hidden bg-[var(--color-bg)] text-[var(--color-text)] transition-[width,height] duration-200',
        compact ? 'mt-1 w-full border-t border-[var(--color-border)]' : 'hidden min-w-0 max-w-sm lg:flex',
        compact
          ? open
            ? 'h-56'
            : 'h-7'
          : open
            ? 'w-[320px]'
            : 'w-0',
      )}
    >
      {open && (
        <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1">
          {!hasExecution && (
            <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {t('trace.executionPane.emptyDetail')}
            </p>
          )}

          {hasExecution && (
            <div className="flex h-full flex-col">
              <div
                role="tablist"
                aria-label={t('trace.executionPane.title')}
                className="mb-1.5 flex gap-1 rounded-lg bg-[var(--color-bg)] p-0.5"
              >
                <ExecutionTabButton
                  id="timeline"
                  active={tab === 'timeline'}
                  label="Timeline"
                  onClick={() => setTab('timeline')}
                />
                <ExecutionTabButton
                  id="tools"
                  active={tab === 'tools'}
                  label={t('trace.tab.tools')}
                  disabled={toolCalls.length === 0}
                  onClick={() => toolCalls.length > 0 && setTab('tools')}
                />
              </div>

              <div className="relative mt-1 flex-1 pr-1">
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'timeline'
                      ? 'pointer-events-auto translate-y-0 opacity-100'
                      : 'pointer-events-none translate-y-1 opacity-0',
                  )}
                >
                  <ExecutionTimeline events={executionEvents} live={isStreaming} />
                </div>
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'tools'
                      ? 'pointer-events-auto translate-y-0 opacity-100'
                      : 'pointer-events-none translate-y-1 opacity-0',
                  )}
                >
                  <ToolCallsView toolCalls={toolCalls} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

interface ExecutionTabButtonProps {
  id: string
  active: boolean
  label: string
  disabled?: boolean
  onClick: () => void
}

function ExecutionTabButton({ id, active, label, disabled, onClick }: ExecutionTabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={`execution-pane-${id}`}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex-1 rounded-md px-1.5 py-1 text-[11px] transition-colors',
        active
          ? 'bg-[var(--color-panel)] text-[var(--color-text)]'
          : 'text-[var(--color-text-muted)] hover:bg-[var(--color-panel)] hover:text-[var(--color-text)]',
        disabled && 'opacity-50 hover:bg-transparent hover:text-[var(--color-text-muted)]',
      )}
    >
      <span className="block truncate">{label}</span>
    </button>
  )
}

function iconForEvent(event: DeepAgentsExecutionEvent) {
  if (event.kind === 'model') return Bot
  if (event.kind === 'tool') return Hammer
  if (event.kind === 'state' || event.kind === 'system') return Workflow
  return PanelRightOpen
}

function statusIcon(status?: string) {
  const lowered = String(status || '').toLowerCase()
  if (lowered === 'completed' || lowered === 'success') {
    return <CheckCircle2 size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'failed' || lowered === 'error') {
    return <XCircle size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'running' || lowered === 'pending') {
    return <CircleDashed size={13} className="animate-spin text-[var(--color-text)]" />
  }
  return null
}

function ExecutionTimeline({ events, live }: { events: DeepAgentsExecutionEvent[]; live: boolean }) {
  const { t } = useChatI18n()

  if (!events.length) {
    return (
      <p id="execution-pane-timeline" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {t('trace.executionPane.emptyDetail')}
      </p>
    )
  }

  return (
    <div id="execution-pane-timeline" className="space-y-2 text-[11px]">
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span className="font-medium">Runtime timeline</span>
        <span>{live ? t('trace.status.running') : `${events.length} events`}</span>
      </div>
      <ol className="space-y-1.5">
        {events.map((event, index) => {
          const Icon = iconForEvent(event)
          return (
            <li
              key={event.id}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2"
            >
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
                  <Icon size={12} className="text-[var(--color-text)]" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[var(--color-text-muted)]">{index + 1}.</span>
                    <div className="min-w-0 truncate text-[11px] font-semibold text-[var(--color-text)]">
                      {event.title}
                    </div>
                    {event.status && (
                      <span className="text-[10px] text-[var(--color-text-muted)]">{event.status}</span>
                    )}
                  </div>
                  {event.summary && (
                    <div className="mt-0.5 break-words text-[10px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                      {event.summary}
                    </div>
                  )}
                  {event.ns && event.ns.length > 0 && (
                    <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">
                      {event.ns.join(' / ')}
                    </div>
                  )}
                </div>
                <span className="pt-0.5">{statusIcon(event.status)}</span>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function ToolCallsView({
  toolCalls,
}: {
  toolCalls: ReturnType<typeof extractToolCalls>
}) {
  const { t } = useChatI18n()

  if (!toolCalls.length) {
    return (
      <p id="execution-pane-tools" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {t('trace.tools.empty')}
      </p>
    )
  }

  return (
    <div id="execution-pane-tools" className="space-y-2 text-[11px]">
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span className="font-medium">{t('trace.tab.tools')}</span>
        <span>{t('trace.tools.count', { count: toolCalls.length })}</span>
      </div>
      <ul className="space-y-1.5">
        {toolCalls.map((call) => (
          <li key={call.key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
            <div className="flex items-start gap-2">
              <ProviderIcon provider={call.provider} size="md" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                    {call.name}
                  </span>
                  <span className="text-[11px] text-[var(--color-text-muted)]">{call.status || '-'}</span>
                  {call.latencyMs > 0 && (
                    <span className="text-[10px] text-[var(--color-text-muted)]">{call.latencyMs} ms</span>
                  )}
                </div>
                {call.summary && (
                  <div className="mt-1 break-words text-[11px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                    {call.summary}
                  </div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
