import { useEffect, useMemo, useState } from 'react'
import type { AelinToolStep } from '@/shared/api/types'
import { AgentTracePanel } from './AgentTracePanel'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'
import {
  buildRunNodes,
  extractToolCalls,
  type RunNode,
  type ToolCallMeta,
} from '../traceUtils'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import { ProviderIcon } from './ProviderIcon'

interface ExecutionPaneProps {
  trace: AelinToolStep[]
  isStreaming: boolean
  compact?: boolean
}

type ExecutionTab = 'aelin' | 'tools'

export function ExecutionPane({ trace, isStreaming, compact = false }: ExecutionPaneProps) {
  const { t } = useChatI18n()
  const { open } = useExecutionPaneStore()
  const hasTrace = useMemo(() => trace && trace.length > 0, [trace])
  const runNodes = useMemo<RunNode[]>(() => buildRunNodes(trace), [trace])
  const toolCalls = useMemo(() => extractToolCalls(trace), [trace])

  const agentNodes = useMemo(
    () => runNodes.filter((n) => n.type === 'preflight' || n.type === 'agent' || n.type === 'plan' || n.type === 'error'),
    [runNodes],
  )

  const [tab, setTab] = useState<ExecutionTab>('aelin')

  useEffect(() => {
    if (!hasTrace) return
    setTab('aelin')
  }, [hasTrace])

  const label = hasTrace ? t('trace.executionPane.title') : t('trace.executionPane.empty')
  const showTabs = hasTrace

  return (
    <aside
      aria-label={label}
      className={cn(
        'flex shrink-0 flex-col bg-[var(--color-bg)] text-[var(--color-text)] transition-[width,height] duration-200 overflow-hidden',
        compact
          ? 'mt-1 w-full border-t border-[var(--color-border)]'
          : 'hidden min-w-0 max-w-sm lg:flex',
        compact
          ? open
            ? 'h-48'
            : 'h-7'
          : open
            ? 'w-[280px]'
            : 'w-0',
      )}
    >
      {open && (
        <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1">
          {!hasTrace && (
            <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {t('trace.executionPane.emptyDetail')}
            </p>
          )}

          {hasTrace && (
            <div className="flex h-full flex-col">
              {showTabs && (
                <div
                  role="tablist"
                  aria-label={t('trace.executionPane.title')}
                  className="mb-1.5 flex gap-1 rounded-lg bg-[var(--color-bg)] p-0.5"
                >
                  <ExecutionTabButton
                    id="aelin"
                    active={tab === 'aelin'}
                    label={t('trace.tab.aelin')}
                    onClick={() => setTab('aelin')}
                  />
                  <ExecutionTabButton
                    id="tools"
                    active={tab === 'tools'}
                    label={t('trace.tab.tools')}
                    disabled={toolCalls.length === 0}
                    onClick={() => toolCalls.length > 0 && setTab('tools')}
                  />
                </div>
              )}

              <div className="mt-1 relative flex-1 pr-1">
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'aelin'
                      ? 'opacity-100 pointer-events-auto translate-y-0'
                      : 'opacity-0 pointer-events-none translate-y-1',
                  )}
                >
                  <AgentTracePanel nodes={agentNodes} live={isStreaming} />
                </div>
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'tools'
                      ? 'opacity-100 pointer-events-auto translate-y-0'
                      : 'opacity-0 pointer-events-none translate-y-1',
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
        disabled && 'opacity-50 hover:bg-transparent hover:text-[var(--color-text-muted)]'
      )}
    >
      <span className="block truncate">{label}</span>
    </button>
  )
}

function ToolCallsView({ toolCalls }: { toolCalls: ToolCallMeta[] }) {
  const { t } = useChatI18n()
  const calls = toolCalls

  if (!calls.length) {
    return (
      <p
        id="execution-pane-tools"
        className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]"
      >
        {t('trace.tools.empty')}
      </p>
    )
  }

  const grouped = groupToolCallsByRound(calls)

  return (
    <div id="execution-pane-tools" className="space-y-2 text-[11px]">
      {grouped.map(({ round, items }) => (
        <section key={`round-${round}`} className="space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
            <span className="font-medium">
              {t('trace.tools.round', { round })}
            </span>
            <span>
              {t('trace.tools.count', { count: items.length })}
            </span>
          </div>
          <ul className="space-y-1.5">
            {items.map((call, idx) => (
              <ToolCallCard key={`${round}-${call.name}-${idx}-${call.status}`} call={call} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function groupToolCallsByRound(calls: ToolCallMeta[]): Array<{ round: number; items: ToolCallMeta[] }> {
  const byRound = new Map<number, ToolCallMeta[]>()
  for (const call of calls) {
    const round = call.round || 1
    if (!byRound.has(round)) byRound.set(round, [])
    byRound.get(round)!.push(call)
  }
  return Array.from(byRound.entries())
    .sort(([a], [b]) => a - b)
    .map(([round, items]) => ({
      round,
      items,
    }))
}

function ToolCallCard({ call }: { call: ToolCallMeta }) {
  const { t } = useChatI18n()
  const [open, setOpen] = useState(false)

  const writeBadge = call.isWrite
    ? (
        <span className="rounded-full border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text)]">
          {t('trace.tools.write')}
        </span>
      )
    : (
        <span className="rounded-full border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {t('trace.tools.read')}
        </span>
      )

  const latencyLabel = call.latencyMs > 0 ? `${call.latencyMs} ms` : ''

  const providerLabel = (() => {
    const p = call.provider.toLowerCase()
    if (p === 'google') return 'Google'
    if (p === 'device') return 'Device'
    if (p === 'plane') return 'Plane'
    if (p === 'web') return 'Web'
    return 'Core'
  })()

  const summary = useMemo(() => {
    const detail = String(call.detail || '')
    const firstLine = detail.split('\n', 1)[0]
    const afterColon = firstLine.split(':', 2)[1]?.trim()
    if (afterColon) return afterColon
    // fallback to truncated detail
    return detail.length > 120 ? `${detail.slice(0, 117)}…` : detail
  }, [call.detail])

  const urls = useMemo(() => {
    const text = String(call.detail || '')
    const matches = text.match(/https?:\/\/[^\s]+/g) ?? []
    // 去重并截断一下显示长度
    const unique = Array.from(new Set(matches))
    return unique.map((u) => u.replace(/[),.;]+$/, ''))
  }, [call.detail])

  return (
    <li className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 text-left"
      >
        <ProviderIcon provider={providerLabel} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
              {call.name}
            </span>
            <span className="text-[11px] text-[var(--color-text-muted)]">
              {call.status || '-'}
            </span>
            {latencyLabel && (
              <span className="text-[10px] text-[var(--color-text-muted)]">
                {latencyLabel}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--color-text-muted)]">
            {writeBadge}
            <span>{providerLabel}</span>
          </div>
          {summary && (
            <div className="mt-1 break-words text-[11px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              {summary}
            </div>
          )}
        </div>
        <span className="mt-0.5 text-[12px] text-[var(--color-text-muted)]">
          {open ? '−' : '+'}
        </span>
      </button>

      {call.detail && (
        <div
          className={cn(
            'mt-1 overflow-hidden border-t border-[var(--color-border)] transition-[max-height,opacity] duration-250 ease-out',
            open ? 'max-h-40 opacity-100 pt-1' : 'max-h-0 opacity-0 pt-0 border-transparent',
          )}
        >
          <div className="space-y-1 text-[10px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
            <div>{call.detail}</div>
            {urls.length > 0 && (
              <div className="space-y-0.5">
                {urls.map((url) => (
                  <div key={url}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[var(--color-text)] underline underline-offset-2"
                    >
                      {url}
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </li>
  )
}
