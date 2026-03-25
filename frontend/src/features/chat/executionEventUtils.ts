import type {
  DeepAgentsExecutionEvent,
  DeepAgentsExecutionEventKind,
} from '@/shared/api/types'

function compactText(value: unknown, max = 180): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function stableStringify(value: unknown): string {
  try {
    return JSON.stringify(value)
  } catch {
    return String(value ?? '')
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function detectKind(type: string, payload: Record<string, unknown>): DeepAgentsExecutionEventKind {
  if (type === 'error') return 'error'
  if (type === 'final') return 'final'
  if (type === 'messages') return 'model'
  if (type === 'updates' || type === 'values') return 'state'
  if (type === 'tasks') {
    const name = String(payload.name ?? payload.id ?? '').toLowerCase()
    return name ? 'tool' : 'task'
  }
  return 'system'
}

function deriveStatus(type: string, payload: Record<string, unknown>): string {
  const direct = String(payload.status ?? '').trim().toLowerCase()
  if (direct) return direct
  if (type === 'start') return 'running'
  if (type === 'final') return 'completed'
  if (type === 'error') return 'failed'
  return ''
}

function deriveTitle(type: string, payload: Record<string, unknown>): string {
  if (type === 'start') return 'Run started'
  if (type === 'final') return 'Run finished'
  if (type === 'error') return 'Run error'
  if (type === 'messages') {
    const metadata = asRecord(payload.metadata)
    const node = compactText(metadata.langgraph_node, 40)
    return node ? `Model · ${node}` : 'Model output'
  }
  if (type === 'tasks') {
    return compactText(payload.name ?? payload.id ?? 'Task', 80) || 'Task'
  }
  if (type === 'updates') {
    const keys = Object.keys(asRecord(payload))
    return keys.length ? `State update · ${keys.join(', ')}` : 'State update'
  }
  if (type === 'values') return 'State snapshot'
  return type || 'Event'
}

function deriveSummary(type: string, payload: Record<string, unknown>): string {
  if (type === 'start') {
    const query = compactText(payload.query, 120)
    const workspace = compactText(payload.workspace, 32)
    return [query, workspace && `workspace=${workspace}`].filter(Boolean).join(' · ')
  }
  if (type === 'messages') return compactText(payload.content, 220)
  if (type === 'tasks') {
    const status = compactText(payload.status, 40)
    const id = compactText(payload.id, 40)
    return [status, id && `id=${id}`].filter(Boolean).join(' · ')
  }
  if (type === 'updates') return compactText(stableStringify(payload), 220)
  if (type === 'values') {
    const todos = Array.isArray(payload.todos) ? payload.todos.length : 0
    const answer = compactText(payload.answer, 160)
    if (answer) return answer
    if (todos > 0) return `todos=${todos}`
    const messages = Array.isArray(payload.messages) ? payload.messages.length : 0
    if (messages > 0) return `messages=${messages}`
    return compactText(stableStringify(payload), 220)
  }
  if (type === 'final') {
    const answer = compactText(payload.answer, 180)
    const usage = asRecord(payload.usage)
    const totalCalls = Number(usage.total_calls ?? 0)
    return [answer, totalCalls > 0 ? `tools=${totalCalls}` : ''].filter(Boolean).join(' · ')
  }
  if (type === 'error') return compactText(payload.message, 220)
  return compactText(stableStringify(payload), 220)
}

function eventId(type: string, payload: Record<string, unknown>, ts: number): string {
  const nsRaw = Array.isArray(payload.ns) ? payload.ns.join('/') : ''
  const node = compactText(payload.node ?? payload.title ?? payload.name ?? '', 60)
  return `${type}:${nsRaw}:${node}:${ts}:${Math.random().toString(36).slice(2, 8)}`
}

export function createExecutionEvent(type: string, payload: unknown): DeepAgentsExecutionEvent | null {
  const record = asRecord(payload)
  const ts = Date.now()
  const ns = Array.isArray(record.ns) ? record.ns.map((item) => String(item)) : undefined
  const metadata = asRecord(record.metadata)

  const event: DeepAgentsExecutionEvent = {
    id: eventId(type, record, ts),
    type,
    kind: detectKind(type, record),
    title: deriveTitle(type, record),
    summary: deriveSummary(type, record) || undefined,
    status: deriveStatus(type, record) || undefined,
    node: compactText(record.node ?? metadata.langgraph_node, 60) || undefined,
    ns,
    ts,
    metadata: Object.keys(metadata).length ? metadata : undefined,
  }

  if (!event.title && !event.summary) return null
  return event
}

export interface ExecutionToolCall {
  key: string
  name: string
  status: string
  summary: string
  provider: string
  latencyMs: number
  isWrite: boolean
}

function inferProvider(name: string): string {
  const lowered = String(name || '').toLowerCase()
  if (lowered.startsWith('gws') || lowered.startsWith('google') || lowered.startsWith('gmail')) return 'google'
  if (lowered.startsWith('device') || lowered.startsWith('screen')) return 'device'
  if (lowered.startsWith('web')) return 'web'
  return 'core'
}

export function extractToolCalls(
  executionEvents: DeepAgentsExecutionEvent[] | undefined,
): ExecutionToolCall[] {
  return (executionEvents || [])
    .filter((event) => event.type === 'tasks')
    .map((event, index) => ({
      key: `${event.id}-${index}`,
      name: event.title.replace(/^Task\s*·\s*/i, '') || event.title,
      status: String(event.status || 'unknown'),
      summary: String(event.summary || ''),
      provider: inferProvider(event.title),
      latencyMs: 0,
      isWrite: false,
    }))
}

export function summarizeExecutionStatus(
  executionEvents: DeepAgentsExecutionEvent[] | undefined,
  isStreaming: boolean,
): string {
  const events = executionEvents || []
  const last = events.at(-1)
  if (!last) return isStreaming ? 'Generating' : ''
  if (isStreaming) {
    if (last.kind === 'tool' || last.kind === 'task') return last.title
    if (last.kind === 'model' && last.summary) return 'Generating reply'
    return last.title
  }
  return last.summary || last.title
}
