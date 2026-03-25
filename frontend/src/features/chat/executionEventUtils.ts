import type {
  DeepAgentsRunState,
  DeepAgentsExecutionEvent,
  DeepAgentsExecutionEventKind,
  DeepAgentsStreamPart,
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

function summarizeScalar(value: unknown, max = 220): unknown {
  if (typeof value === 'string') return compactText(value, max)
  if (typeof value === 'number' || typeof value === 'boolean' || value == null) return value
  return undefined
}

function summarizeUnknown(value: unknown, depth = 0): unknown {
  const scalar = summarizeScalar(value)
  if (scalar !== undefined) return scalar
  if (depth >= 2) {
    if (Array.isArray(value)) return `items=${value.length}`
    return `keys=${Object.keys(asRecord(value)).length}`
  }
  if (Array.isArray(value)) {
    return value.slice(0, 4).map((item) => summarizeUnknown(item, depth + 1))
  }
  const record = asRecord(value)
  const out: Record<string, unknown> = {}
  for (const key of Object.keys(record).slice(0, 8)) {
    out[key] = summarizeUnknown(record[key], depth + 1)
  }
  if (Object.keys(record).length > 8) out.__truncated = true
  return out
}

function normalizePartPayload(event: string, payload: Record<string, unknown>): Record<string, unknown> {
  const ns = Array.isArray(payload.ns) ? payload.ns.map((item) => String(item)) : undefined
  const data = payload.data
  const base: Record<string, unknown> = {
    type: payload.type ?? event,
  }
  if (typeof payload.run_id === 'string' && payload.run_id) base.run_id = payload.run_id
  if (typeof payload.seq === 'number') base.seq = payload.seq
  if (ns?.length) base.ns = ns

  if (event === 'messages') {
    const dataRecord = asRecord(data)
    base.data = {
      content: compactText(dataRecord.content, 800),
      metadata: summarizeUnknown(dataRecord.metadata),
    }
    return base
  }

  if (event === 'tasks') {
    const dataRecord = asRecord(data)
    base.data = {
      id: dataRecord.id,
      name: dataRecord.name,
      status: dataRecord.status,
      interrupts: Array.isArray(dataRecord.interrupts) ? dataRecord.interrupts.length : 0,
      triggers: Array.isArray(dataRecord.triggers) ? dataRecord.triggers.length : 0,
      error: summarizeScalar(dataRecord.error, 160),
    }
    return base
  }

  if (event === 'values') {
    const dataRecord = asRecord(data)
    const todos = Array.isArray(dataRecord.todos) ? dataRecord.todos : []
    const messages = Array.isArray(dataRecord.messages) ? dataRecord.messages : []
    base.data = {
      answer: compactText(dataRecord.answer, 800),
      todos: todos.slice(0, 6).map((item) => summarizeUnknown(item, 1)),
      todos_count: todos.length,
      messages_count: messages.length,
      plan: summarizeUnknown(dataRecord.plan),
    }
    return base
  }

  if (event === 'updates') {
    const summary = summarizeUnknown(data)
    base.data = typeof summary === 'object' && summary != null ? summary : { summary }
    return base
  }

  if (event === 'final') {
    const dataRecord = asRecord(data)
    base.data = {
      answer: compactText(dataRecord.answer, 800),
      finished_at: dataRecord.finished_at,
      usage: summarizeUnknown(dataRecord.usage),
    }
    return base
  }

  if (event === 'error') {
    const dataRecord = asRecord(data)
    base.data = {
      message: compactText(dataRecord.message, 300),
      code: dataRecord.code,
    }
    return base
  }

  if (event === 'start') {
    const dataRecord = asRecord(data)
    base.data = {
      query: compactText(dataRecord.query, 300),
      workspace: dataRecord.workspace,
      source: dataRecord.source,
    }
    return base
  }

  base.data = summarizeUnknown(data)
  return base
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

function streamPartId(event: string, payload: Record<string, unknown>, ts: number): string {
  const nsRaw = Array.isArray(payload.ns) ? payload.ns.join('/') : ''
  return `${event}:${nsRaw}:${ts}:${Math.random().toString(36).slice(2, 8)}`
}

export function createStreamPart(event: string, payload: unknown): DeepAgentsStreamPart | null {
  const record = asRecord(payload)
  if (!event || !Object.keys(record).length) return null
  const normalized = normalizePartPayload(event, record)
  const ts = Date.now()
  const ns = Array.isArray(normalized.ns) ? normalized.ns.map((item) => String(item)) : undefined
  return {
    id: streamPartId(event, normalized, ts),
    event,
    ts,
    runId: typeof normalized.run_id === 'string' ? normalized.run_id : undefined,
    seq: typeof normalized.seq === 'number' ? normalized.seq : undefined,
    ns,
    payload: normalized,
    data: normalized.data,
  }
}

export function appendRunStatePart(
  current: DeepAgentsRunState | undefined,
  part: DeepAgentsStreamPart,
): DeepAgentsRunState {
  const next: DeepAgentsRunState = {
    parts: [...(current?.parts ?? []), part],
    runId: current?.runId ?? part.runId,
    latestValues: current?.latestValues,
    final: current?.final,
  }
  if (part.event === 'values') {
    const values = asRecord(part.data)
    if (Object.keys(values).length) next.latestValues = values
  }
  if (part.event === 'final') {
    const final = asRecord(part.data ?? part.payload)
    if (Object.keys(final).length) next.final = final
  }
  return next
}

export function createExecutionEvent(type: string, payload: unknown, ts = Date.now()): DeepAgentsExecutionEvent | null {
  const record = asRecord(payload)
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

export function createExecutionEventFromPart(part: DeepAgentsStreamPart): DeepAgentsExecutionEvent | null {
  if (part.event === 'ping' || part.event === 'done') return null
  const payload =
    part.data != null
      ? { ...asRecord(part.data), ns: part.ns ?? [] }
      : part.payload
  return createExecutionEvent(part.event, payload, part.ts)
}

export function executionEventsFromRunState(
  runState: DeepAgentsRunState | undefined,
): DeepAgentsExecutionEvent[] {
  return (runState?.parts ?? [])
    .map((part) => createExecutionEventFromPart(part))
    .filter((event): event is DeepAgentsExecutionEvent => event != null)
}

export interface RunTaskSnapshot {
  key: string
  id: string
  name: string
  status: string
  summary: string
  ns: string[]
  updates: number
  lastTs: number
  error?: string
}

export interface RunSubagentSnapshot {
  key: string
  label: string
  ns: string[]
  status: string
  taskCount: number
  lastTs: number
}

function formatNsLabel(ns: string[] | undefined): string {
  const clean = (ns ?? [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .filter((item) => !item.startsWith('__pregel'))
  return clean.length ? clean.join(' / ') : 'root'
}

function coerceTaskName(data: Record<string, unknown>): string {
  return compactText(data.name ?? data.id ?? 'Task', 80) || 'Task'
}

export function taskSnapshotsFromRunState(
  runState: DeepAgentsRunState | undefined,
): RunTaskSnapshot[] {
  const byKey = new Map<string, RunTaskSnapshot>()

  for (const part of runState?.parts ?? []) {
    if (part.event !== 'tasks') continue
    const data = asRecord(part.data)
    const ns = part.ns ?? []
    const rawId = compactText(data.id, 80) || ''
    const name = coerceTaskName(data)
    const key = `${formatNsLabel(ns)}::${rawId || name}`
    const summaryBits = [
      compactText(data.status, 40),
      rawId ? `id=${rawId}` : '',
      Number(data.interrupts || 0) > 0 ? `interrupts=${Number(data.interrupts)}` : '',
      Number(data.triggers || 0) > 0 ? `triggers=${Number(data.triggers)}` : '',
    ].filter(Boolean)
    const existing = byKey.get(key)
    byKey.set(key, {
      key,
      id: rawId || name,
      name,
      status: compactText(data.status, 40) || existing?.status || 'unknown',
      summary: summaryBits.join(' · '),
      ns,
      updates: (existing?.updates ?? 0) + 1,
      lastTs: part.ts,
      error: compactText(data.error, 160) || existing?.error,
    })
  }

  return [...byKey.values()].sort((a, b) => a.lastTs - b.lastTs)
}

export function subagentSnapshotsFromRunState(
  runState: DeepAgentsRunState | undefined,
): RunSubagentSnapshot[] {
  const taskSnapshots = taskSnapshotsFromRunState(runState)
  const byNs = new Map<string, RunSubagentSnapshot>()

  for (const task of taskSnapshots) {
    if (!task.ns.length) continue
    const label = formatNsLabel(task.ns)
    const existing = byNs.get(label)
    byNs.set(label, {
      key: label,
      label,
      ns: task.ns,
      status: task.status || existing?.status || 'unknown',
      taskCount: (existing?.taskCount ?? 0) + 1,
      lastTs: Math.max(existing?.lastTs ?? 0, task.lastTs),
    })
  }

  return [...byNs.values()].sort((a, b) => a.lastTs - b.lastTs)
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
