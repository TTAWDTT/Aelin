import type { ReactNode } from 'react'
import { Hammer, Workflow } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import type {
  ExecutionGraphNode,
  ExecutionNamespaceLane,
  ExecutionSubagent,
  ExecutionToolCall,
} from '../executionStreamUtils'
import {
  nodeIcon,
  stableJson,
  statusIcon,
  truncateBlock,
} from './executionPaneShared'

interface ExecutionTabButtonProps {
  id: string
  active: boolean
  label: string
  disabled?: boolean
  onClick: () => void
}

export function ExecutionTabButton({ id, active, label, disabled, onClick }: ExecutionTabButtonProps) {
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

export function GraphBoard({
  nodes,
  edges,
  isStreaming,
}: {
  nodes: ExecutionGraphNode[]
  edges: Array<{ source: string; target: string; active?: boolean; traversed?: number; conditional?: boolean }>
  isStreaming: boolean
}) {
  if (nodes.length === 0) {
    return (
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        Runtime did not publish a graph.
      </p>
    )
  }

  const columns = Array.from(
    nodes.reduce((map, node) => {
      const bucket = map.get(node.depth) ?? []
      bucket.push(node)
      map.set(node.depth, bucket)
      return map
    }, new Map<number, ExecutionGraphNode[]>()),
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
          className="pointer-events-none absolute left-3 top-3"
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
                    node.status === 'idle'
                      ? 'border-[var(--color-border)] bg-[var(--color-panel)] opacity-80'
                      : node.status === 'running'
                        ? 'border-[var(--color-text)] bg-[var(--color-panel)]'
                        : 'border-[var(--color-border)] bg-[var(--color-panel)]',
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
                          {node.visits > 0 && <GraphBadge>{node.visits} hits</GraphBadge>}
                          {node.toolCalls > 0 && <GraphBadge>{node.toolCalls} tools</GraphBadge>}
                          {node.subagents > 0 && <GraphBadge>{node.subagents} subagents</GraphBadge>}
                          {node.activeNamespaces > 0 && (
                            <GraphBadge>
                              {node.activeNamespaces} active path{node.activeNamespaces > 1 ? 's' : ''}
                            </GraphBadge>
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

function GraphBadge({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
      {children}
    </span>
  )
}

export function ToolCard({ tool, compact = false }: { tool: ExecutionToolCall; compact?: boolean }) {
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

export function NamespaceLaneCard({ lane }: { lane: ExecutionNamespaceLane }) {
  return (
    <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-2.5">
      <div className="flex items-center gap-2">
        <span>{statusIcon(lane.status)}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11px] font-medium text-[var(--color-text)]">
            {lane.label}
          </div>
          {lane.currentNode && (
            <div className="mt-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              current: {lane.currentNode}
            </div>
          )}
          <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
            {lane.nodes.join(' -> ') || 'idle'}
          </div>
          {(lane.toolCalls > 0 || lane.subagents > 0) && (
            <div className="mt-2 flex flex-wrap gap-1">
              {lane.toolCalls > 0 && <LaneBadge>{lane.toolCalls} tools</LaneBadge>}
              {lane.subagents > 0 && <LaneBadge>{lane.subagents} subagents</LaneBadge>}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function LaneBadge({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
      {children}
    </span>
  )
}

export function SubagentCard({ subagent, compact = false }: { subagent: ExecutionSubagent; compact?: boolean }) {
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
          {subagent.preview && (
            <div className="mt-1 break-words text-[11px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              {subagent.preview}
            </div>
          )}
          {subagent.namespace && (
            <div className="mt-0.5 break-words text-[10px] uppercase tracking-wide text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              {subagent.namespace}
            </div>
          )}
        </div>
        <span className="pt-0.5">{statusIcon(subagent.status)}</span>
      </div>
    </section>
  )
}

export function JsonBlock({ value }: { value: unknown }) {
  const text = truncateBlock(stableJson(value))
  return (
    <pre className="overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-2.5 text-[10px] leading-relaxed text-[var(--color-text-muted)]">
      {text}
    </pre>
  )
}
