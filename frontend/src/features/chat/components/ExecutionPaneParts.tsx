import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import dagre from 'dagre'
import { Hammer, Workflow } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import type {
  ExecutionGraphNode,
  ExecutionNamespaceLane,
  ExecutionSubagent,
  ExecutionToolCall,
} from '../executionStreamUtils'
import {
  formatExecutionStatus,
  surfaceTint,
  stableJson,
  statusIcon,
  toneColor,
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
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const element = viewportRef.current
    if (!element) return

    const updateViewport = () => {
      setViewportSize({
        width: element.clientWidth,
        height: element.clientHeight,
      })
    }

    updateViewport()
    const observer = new ResizeObserver(updateViewport)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  if (nodes.length === 0) {
    return (
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        Runtime did not publish a graph.
      </p>
    )
  }

  const graphNodes = nodes.map((node) => ({
    node,
    ...measureGraphNode(node),
  }))

  const graph = new dagre.graphlib.Graph()
  graph.setGraph({
    rankdir: 'TB',
    align: 'UL',
    ranksep: 76,
    nodesep: 34,
    edgesep: 22,
    marginx: 28,
    marginy: 28,
  })
  graph.setDefaultEdgeLabel(() => ({}))

  graphNodes.forEach(({ node, width, height }) => {
    graph.setNode(node.id, { width, height })
  })
  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target)
  })
  dagre.layout(graph)

  const width = Math.max(280, Math.ceil((graph.graph().width as number) || 0))
  const height = Math.max(180, Math.ceil((graph.graph().height as number) || 0))
  const fitScale = Math.min(
    1,
    viewportSize.width > 0 ? (viewportSize.width - 20) / width : 1,
    viewportSize.height > 0 ? (viewportSize.height - 20) / height : 1,
  )
  const scale = Number.isFinite(fitScale) && fitScale > 0 ? fitScale : 1
  const scaledWidth = Math.max(1, Math.round(width * scale))
  const scaledHeight = Math.max(1, Math.round(height * scale))
  const toneByNodeId = new Map(nodes.map((node) => [node.id, graphTone(node)]))

  return (
    <div
      ref={viewportRef}
      className="mt-3 overflow-auto rounded-[26px] border border-[color:var(--color-border)] bg-[var(--color-bg-elevated)] p-2"
      style={{ height: 'clamp(300px, 50vh, 620px)' }}
    >
      <div className="relative grid min-h-full min-w-full place-items-start justify-items-center overflow-hidden rounded-[22px] border border-[color:color-mix(in_srgb,var(--color-border)_78%,transparent)] bg-[var(--graph-surface-inner)] px-4 py-4">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.24),transparent_60%)] dark:bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.03),transparent_60%)]" />
        <div className="relative" style={{ width: `${scaledWidth}px`, height: `${scaledHeight}px` }}>
          <div
            className="relative"
            style={{
              width: `${width}px`,
              height: `${height}px`,
              transform: `scale(${scale})`,
              transformOrigin: 'top left',
            }}
          >
            <svg
              className="pointer-events-none absolute left-0 top-0"
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              fill="none"
            >
              {edges.map((edge) => {
                const layoutEdge = graph.edge(edge.source, edge.target)
                const points = Array.isArray(layoutEdge?.points) ? layoutEdge.points : []
                if (points.length < 2) return null
                const path = buildEdgePath(points)
                return (
                  <g key={`${edge.source}:${edge.target}`}>
                    <path
                      d={path}
                      stroke={edgeStroke(edge, toneByNodeId)}
                      strokeWidth={edge.active ? 2.1 : 1.25}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeDasharray={edge.conditional ? '5 4' : undefined}
                      opacity={edge.active ? 0.9 : 0.46}
                    />
                    {edge.active && (
                      <path
                        d={path}
                        className="aelin-graph-flow"
                        stroke="rgba(255,255,255,0.92)"
                        strokeWidth={0.95}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeDasharray="3 9"
                        opacity={0.86}
                      />
                    )}
                  </g>
                )
              })}
            </svg>

            <div className="relative" style={{ width: `${width}px`, height: `${height}px` }}>
              {graphNodes.map(({ node, width: currentWidth, height: currentHeight }) => {
                const layoutNode = graph.node(node.id)
                if (!layoutNode) return null
                const tone = graphTone(node)
                const isRunning = isStreaming && (node.status === 'running' || node.activeNamespaces > 0)
                const style: CSSProperties = {
                  left: `${layoutNode.x - currentWidth / 2}px`,
                  top: `${layoutNode.y - currentHeight / 2}px`,
                  width: `${currentWidth}px`,
                  height: `${currentHeight}px`,
                  borderColor: tone.border,
                  background: tone.background,
                  color: tone.text,
                  boxShadow: isRunning
                    ? `0 0 0 1px ${tone.glow}, 0 0 0 8px ${tone.halo}, 0 18px 34px -22px ${tone.shadow}`
                    : node.status === 'completed'
                      ? `0 12px 20px -22px ${tone.shadow}`
                      : '0 4px 10px -9px var(--graph-shadow)',
                  opacity: node.status === 'idle' ? 0.88 : 1,
                  transform: isRunning ? 'scale(1.03)' : 'scale(1)',
                }
                return (
                  <div
                    key={node.id}
                    className={cn(
                      'absolute flex items-center justify-center rounded-[18px] border px-4 py-3 text-center transition-all duration-200',
                      isRunning && 'aelin-graph-node--running',
                    )}
                    style={style}
                    title={buildGraphNodeTitle(node)}
                  >
                    <span className="line-clamp-2 text-[12px] font-semibold leading-snug tracking-[0.01em]">
                      {formatGraphNodeLabel(node.name)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function buildGraphNodeTitle(node: ExecutionGraphNode): string {
  const details = [
    node.name,
    `status: ${node.status}`,
    node.visits > 0 ? `visits: ${node.visits}` : '',
    node.toolCalls > 0 ? `tools: ${node.toolCalls}` : '',
    node.subagents > 0 ? `subagents: ${node.subagents}` : '',
  ].filter(Boolean)
  return details.join('\n')
}

function buildEdgePath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) return ''
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`

  let path = `M ${points[0].x} ${points[0].y}`
  for (let index = 1; index < points.length - 1; index += 1) {
    const prev = points[index - 1]
    const curr = points[index]
    const next = points[index + 1]
    const radius = Math.min(
      12,
      distanceBetween(prev, curr) / 2,
      distanceBetween(curr, next) / 2,
    )
    const start = moveToward(curr, prev, radius)
    const end = moveToward(curr, next, radius)
    path += ` L ${start.x} ${start.y}`
    path += ` Q ${curr.x} ${curr.y} ${end.x} ${end.y}`
  }
  const last = points[points.length - 1]
  path += ` L ${last.x} ${last.y}`
  return path
}

function distanceBetween(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function moveToward(
  source: { x: number; y: number },
  target: { x: number; y: number },
  distance: number,
) {
  const total = distanceBetween(source, target)
  if (total === 0) return { x: source.x, y: source.y }
  const ratio = distance / total
  return {
    x: source.x + (target.x - source.x) * ratio,
    y: source.y + (target.y - source.y) * ratio,
  }
}

function formatGraphNodeLabel(name: string): string {
  const text = String(name || '').trim()
  if (text.length <= 30) return text
  return `${text.slice(0, 27)}…`
}

function measureGraphNode(node: ExecutionGraphNode): { width: number; height: number } {
  const lowered = `${node.id} ${node.name} ${node.kind}`.toLowerCase()
  if (lowered.includes('__start__') || lowered.includes('__end__')) {
    return { width: 180, height: 72 }
  }
  if (lowered.includes('model')) {
    return { width: 192, height: 74 }
  }
  const width = Math.min(220, Math.max(156, 52 + Math.round(formatGraphNodeLabel(node.name).length * 5.4)))
  return { width, height: 74 }
}

function edgeStroke(
  edge: { source: string; target: string; active?: boolean; conditional?: boolean },
  toneByNodeId: Map<string, ReturnType<typeof graphTone>>,
): string {
  const targetTone = toneByNodeId.get(edge.target)
  if (!targetTone) return edge.active ? 'rgba(255,255,255,0.72)' : 'rgba(255,255,255,0.28)'
  return edge.active
    ? targetTone.border.replace(/0\.\d+\)/, '0.78)')
    : targetTone.border.replace(/0\.\d+\)/, '0.34)')
}

function graphTone(node: ExecutionGraphNode) {
  const name = `${node.id} ${node.name} ${node.kind}`.toLowerCase()
  const makeTone = (token: string) => ({
    border: toneColor(token, node.status === 'running' ? 0.7 : 0.42),
    background: surfaceTint(token, node.status === 'running' ? 14 : node.status === 'completed' ? 11 : 7),
    text: surfaceTint(token, 76, 'var(--color-text)'),
    glow: toneColor(token, 0.16),
    halo: toneColor(token, 0.08),
    shadow: toneColor(token, 0.16),
    badgeBackground: toneColor(token, 0.08),
    badgeBorder: toneColor(token, 0.18),
  })
  if (name.includes('__start__') || name.includes('start')) {
    return makeTone('var(--graph-node-start)')
  }
  if (name.includes('__end__') || name.includes(' end') || name.includes('final')) {
    return makeTone('var(--graph-node-end)')
  }
  if (name.includes('tool')) {
    return makeTone('var(--graph-node-tool)')
  }
  if (name.includes('model')) {
    return makeTone('var(--graph-node-model)')
  }
  if (name.includes('patch')) {
    return makeTone('var(--graph-node-patch)')
  }
  if (name.includes('todo')) {
    return makeTone('var(--graph-node-middleware)')
  }
  if (name.includes('middleware')) {
    return makeTone('var(--graph-node-middleware)')
  }
  return makeTone('var(--graph-node-neutral)')
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
              {formatExecutionStatus(tool.state)}
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
              {formatExecutionStatus(subagent.status)}
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
