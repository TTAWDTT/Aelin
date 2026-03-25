import { useEffect, useState } from 'react'
import {
  Bot,
  CheckCircle2,
  CircleDashed,
  Hammer,
  Sparkles,
  Workflow,
  Wrench,
  XCircle,
} from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'
import type {
  ChatRuntimeStream,
  ExecutionTurn,
  ExecutionSubagent,
  ExecutionToolCall,
  ExecutionTopologyNode,
} from '../executionStreamUtils'
import {
  getExecutionTurns,
  getExecutionTopology,
  hasExecutionData,
} from '../executionStreamUtils'
import { useExecutionPaneStore } from '../stores/executionPaneStore'

interface ExecutionPaneProps {
  stream: ChatRuntimeStream
  isStreaming: boolean
  compact?: boolean
}

type ExecutionTab = 'graph' | 'tools' | 'state'

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function compactText(value: unknown, max = 220): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function stableJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value ?? '')
  }
}

function truncateBlock(value: string, max = 8000): string {
  const text = String(value || '').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max - 1)}…`
}

function statusIcon(status?: string) {
  const lowered = String(status || '').toLowerCase()
  if (lowered === 'completed' || lowered === 'success') {
    return <CheckCircle2 size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'failed' || lowered === 'error') {
    return <XCircle size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'running' || lowered === 'pending' || lowered === 'streaming') {
    return <CircleDashed size={13} className="animate-spin text-[var(--color-text)]" />
  }
  return <Sparkles size={13} className="text-[var(--color-text-muted)]" />
}

function nodeIcon(kind: string) {
  const lowered = String(kind || '').toLowerCase()
  if (lowered.includes('tool')) return <Hammer size={12} className="text-[var(--color-text)]" />
  if (lowered.includes('model')) return <Bot size={12} className="text-[var(--color-text)]" />
  if (lowered.includes('middleware')) return <Workflow size={12} className="text-[var(--color-text)]" />
  if (lowered.includes('end') || lowered.includes('final')) return <CheckCircle2 size={12} className="text-[var(--color-text)]" />
  return <Wrench size={12} className="text-[var(--color-text)]" />
}

export function ExecutionPane({
  stream,
  isStreaming,
  compact = false,
}: ExecutionPaneProps) {
  const { t, locale } = useChatI18n()
  const { open } = useExecutionPaneStore()
  const topology = getExecutionTopology(stream)
  const turns = getExecutionTurns(stream)
  const tools = turns.flatMap((turn) => turn.toolCalls)
  const values = asRecord(stream.values)
  const todos = Array.isArray(values.todos) ? values.todos : []
  const hasStateSnapshot = Object.keys(values).some((key) => key !== 'messages')
  const hasExecution = hasExecutionData(stream)
  const [tab, setTab] = useState<ExecutionTab>('graph')

  useEffect(() => {
    if (hasExecution) setTab('graph')
  }, [hasExecution])

  const label = hasExecution ? t('trace.executionPane.title') : t('trace.executionPane.empty')

  return (
    <aside
      aria-label={label}
      className={cn(
        'flex shrink-0 flex-col overflow-hidden bg-[var(--color-bg)] text-[var(--color-text)] transition-[width,height] duration-200',
        compact ? 'mt-1 w-full border-t border-[var(--color-border)]' : 'hidden min-w-0 max-w-md lg:flex',
        compact
          ? open
            ? 'h-72'
            : 'h-7'
          : open
            ? 'w-[380px]'
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
                  id="graph"
                  active={tab === 'graph'}
                  label="Graph"
                  onClick={() => setTab('graph')}
                />
                <ExecutionTabButton
                  id="tools"
                  active={tab === 'tools'}
                  label={t('trace.tab.tools')}
                  disabled={tools.length === 0}
                  onClick={() => tools.length > 0 && setTab('tools')}
                />
                <ExecutionTabButton
                  id="state"
                  active={tab === 'state'}
                  label="State"
                  disabled={!hasStateSnapshot}
                  onClick={() => hasStateSnapshot && setTab('state')}
                />
              </div>

              <div className="relative mt-1 flex-1 pr-1">
                <div className={tabClassName(tab === 'graph')}>
                  <div id="execution-pane-graph" className="space-y-2.5 text-[11px]">
                    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
                      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                        <span className="font-medium">Topology</span>
                        <span>{topology.nodes.length} nodes · {topology.edges.length} edges</span>
                      </div>
                      <TopologyBoard nodes={topology.nodes} edges={topology.edges} isStreaming={isStreaming} />
                    </section>

                    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
                      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                        <span className="font-medium">Runtime</span>
                        <span>{locale === 'zh' ? (isStreaming ? '实时' : '已结束') : (isStreaming ? 'live' : 'settled')}</span>
                      </div>
                      <div className="mt-2 space-y-2">
                        {turns.length === 0 ? (
                          <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
                            {t('trace.executionPane.emptyDetail')}
                          </p>
                        ) : (
                          turns.slice(-6).reverse().map((turn) => (
                            <TurnCard key={turn.key} turn={turn} />
                          ))
                        )}
                      </div>
                    </section>
                  </div>
                </div>

                <div className={tabClassName(tab === 'tools')}>
                  <div id="execution-pane-tools" className="space-y-2 text-[11px]">
                    {tools.length === 0 ? (
                      <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
                        {t('trace.tools.empty')}
                      </p>
                    ) : (
                      turns
                        .filter((turn) => turn.toolCalls.length > 0)
                        .map((turn) => (
                          <section key={`tools:${turn.key}`} className="space-y-2 rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
                            <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                              <span className="font-medium">{turn.node}</span>
                              <span>{turn.toolCalls.length} calls</span>
                            </div>
                            {turn.toolCalls.map((tool) => <ToolCard key={tool.key} tool={tool} />)}
                          </section>
                        ))
                    )}
                  </div>
                </div>

                <div className={tabClassName(tab === 'state')}>
                  <div id="execution-pane-state" className="space-y-2 text-[11px]">
                    {todos.length > 0 && (
                      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
                        <div className="mb-2 text-[11px] font-medium text-[var(--color-text-muted)]">
                          Todos
                        </div>
                        <div className="space-y-1.5">
                          {todos.map((item, index) => {
                            const record = asRecord(item)
                            const title = String(record.title || record.content || `Todo ${index + 1}`)
                            const done = Boolean(record.done)
                            return (
                              <div
                                key={`${title}:${index}`}
                                className="flex items-start gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5"
                              >
                                <span className="pt-0.5">{statusIcon(done ? 'completed' : 'pending')}</span>
                                <div className="min-w-0 flex-1">
                                  <div className="break-words text-[12px] text-[var(--color-text)]">
                                    {title}
                                  </div>
                                  {Boolean(record.detail) && (
                                    <div className="mt-0.5 break-words text-[11px] text-[var(--color-text-muted)]">
                                      {compactText(String(record.detail))}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </section>
                    )}

                    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
                      <div className="mb-2 text-[11px] font-medium text-[var(--color-text-muted)]">
                        Snapshot
                      </div>
                      <JsonBlock value={values} />
                    </section>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

function tabClassName(active: boolean) {
  return cn(
    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
    active
      ? 'pointer-events-auto translate-y-0 opacity-100'
      : 'pointer-events-none translate-y-1 opacity-0',
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

function TurnCard({ turn }: { turn: ExecutionTurn }) {
  return (
    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-2.5">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)]">
          {nodeIcon(turn.node)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
              {turn.node}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              {turn.status}
            </span>
          </div>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            {turn.namespace}
          </div>
          {turn.preview && (
            <div className="mt-1 break-words text-[11px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              {turn.preview}
            </div>
          )}
        </div>
        <span className="pt-0.5">{statusIcon(turn.status)}</span>
      </div>

      {(turn.toolCalls.length > 0 || turn.subagents.length > 0) && (
        <div className="mt-2 space-y-2 border-t border-[var(--color-border)] pt-2">
          {turn.toolCalls.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
                Tools
              </div>
              {turn.toolCalls.map((tool) => <ToolCard key={tool.key} tool={tool} compact />)}
            </div>
          )}

          {turn.subagents.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
                Subagents
              </div>
              {turn.subagents.map((subagent) => (
                <SubagentCard key={subagent.key} subagent={subagent} compact />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function TopologyBoard({
  nodes,
  edges,
  isStreaming,
}: {
  nodes: ExecutionTopologyNode[]
  edges: Array<{ source: string; target: string; active?: boolean; traversed?: number; conditional?: boolean }>
  isStreaming: boolean
}) {
  if (nodes.length === 0) {
    return (
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        No topology yet.
      </p>
    )
  }

  const columns = Array.from(
    nodes.reduce((map, node) => {
      const bucket = map.get(node.depth) ?? []
      bucket.push(node)
      map.set(node.depth, bucket)
      return map
    }, new Map<number, ExecutionTopologyNode[]>()),
  )
    .sort((a, b) => a[0] - b[0])
    .map(([, bucket]) => bucket.sort((a, b) => a.name.localeCompare(b.name)))

  const maxRows = Math.max(...columns.map((column) => column.length))
  const width = Math.max(columns.length, 1) * 220
  const height = Math.max(maxRows, 1) * 116
  const positionById = new Map<string, { x: number; y: number }>()

  columns.forEach((column, colIndex) => {
    column.forEach((node, rowIndex) => {
      positionById.set(node.id, {
        x: colIndex * 220 + 100,
        y: rowIndex * 116 + 54,
      })
    })
  })

  return (
    <div className="mt-2 overflow-x-auto pb-1">
      <div
        className="relative rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-3"
        style={{ minWidth: `${Math.max(width + 20, 280)}px` }}
      >
        <svg
          className="absolute left-3 top-3 pointer-events-none"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          fill="none"
        >
          {edges.map((edge) => {
            const from = positionById.get(edge.source)
            const to = positionById.get(edge.target)
            if (!from || !to) return null
            const midX = (from.x + to.x) / 2
            return (
              <path
                key={`${edge.source}:${edge.target}`}
                d={`M ${from.x + 48} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${to.x - 48} ${to.y}`}
                stroke={edge.active ? 'var(--color-text)' : 'var(--color-border)'}
                strokeWidth={edge.active ? 2.6 : 2}
                strokeLinecap="round"
                strokeDasharray={edge.conditional ? '6 6' : undefined}
                opacity={edge.active ? 0.92 : 0.45}
              />
            )
          })}
        </svg>

        <div
          className="relative grid gap-4"
          style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(180px, 1fr))` }}
        >
          {columns.map((column, columnIndex) => (
            <div key={`column:${columnIndex}`} className="space-y-4">
              {column.map((node) => (
                <div
                  key={node.id}
                  className={cn(
                    'relative overflow-hidden rounded-2xl border px-3 py-2.5 shadow-[0_12px_32px_rgba(15,23,42,0.06)]',
                    node.status === 'running'
                      ? 'border-[var(--color-text)] bg-[var(--color-panel)]'
                      : node.status === 'completed'
                        ? 'border-[var(--color-border)] bg-[var(--color-panel)]'
                        : 'border-[var(--color-border)] bg-[var(--color-panel)] opacity-80',
                  )}
                >
                  {node.status !== 'idle' && (
                    <div
                      className={cn(
                        'absolute inset-x-0 top-0 h-0.5',
                        node.status === 'running'
                          ? 'bg-[var(--color-text)]'
                          : 'bg-[var(--color-border)]',
                      )}
                    />
                  )}
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
                      {nodeIcon(node.kind)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                        {node.name}
                      </div>
                      <div className="mt-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
                        {node.kind}
                      </div>
                      {(node.visits > 0 || node.toolCalls > 0 || node.subagents > 0) && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {node.visits > 0 && (
                            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                              {node.visits} hits
                            </span>
                          )}
                          {node.toolCalls > 0 && (
                            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                              {node.toolCalls} tools
                            </span>
                          )}
                          {node.subagents > 0 && (
                            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                              {node.subagents} subagents
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    {statusIcon(node.status === 'running' ? (isStreaming ? 'running' : 'completed') : node.status)}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ToolCard({ tool, compact = false }: { tool: ExecutionToolCall; compact?: boolean }) {
  return (
    <section className={cn(
      'rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)]',
      compact ? 'p-2' : 'p-2.5',
    )}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
          <Hammer size={12} className="text-[var(--color-text)]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
              {tool.name}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              {tool.state}
            </span>
          </div>
          {tool.args && (
            <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              args: {tool.args}
            </div>
          )}
          {tool.result && (
            <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              result: {tool.result}
            </div>
          )}
        </div>
        <span className="pt-0.5">{statusIcon(tool.state)}</span>
      </div>
    </section>
  )
}

function SubagentCard({ subagent, compact = false }: { subagent: ExecutionSubagent; compact?: boolean }) {
  return (
    <section className={cn(
      'rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)]',
      compact ? 'p-2' : 'p-2.5',
    )}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)]">
          <Workflow size={12} className="text-[var(--color-text)]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
              {subagent.name}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              {subagent.status}
            </span>
          </div>
          <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">
            {subagent.type} · depth {subagent.depth} · {subagent.messageCount} messages
          </div>
        </div>
        <span className="pt-0.5">{statusIcon(subagent.status)}</span>
      </div>
    </section>
  )
}

function JsonBlock({ value }: { value: unknown }) {
  const text = truncateBlock(stableJson(value))
  return (
    <pre className="overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-2.5 text-[10px] leading-relaxed text-[var(--color-text-muted)]">
      {text}
    </pre>
  )
}
