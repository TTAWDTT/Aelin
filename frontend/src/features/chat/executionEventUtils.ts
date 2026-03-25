import type {
  DeepAgentsRunState,
  DeepAgentsStreamPart,
} from '@/shared/api/types'

export type RunTaskKind = 'tool' | 'model' | 'middleware' | 'task'
export type RunGraphNodeKind = 'start' | 'tool' | 'model' | 'middleware' | 'final' | 'error'

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

function humanizeTaskName(value: unknown): string {
  const raw = String(value ?? '').trim()
  if (!raw) return 'Task'
  if (raw === 'model') return 'Model'
  if (raw === 'tools') return 'Tool runtime'
  if (raw.endsWith('.before_agent')) {
    return raw
      .replace(/Middleware\.before_agent$/, '')
      .replace(/_/g, ' ')
      .trim() || 'Runtime prep'
  }
  if (raw.endsWith('.after_model')) {
    return raw
      .replace(/Middleware\.after_model$/, '')
      .replace(/_/g, ' ')
      .trim() || 'Post-process'
  }
  return raw.replace(/_/g, ' ')
}

function classifyTaskRecord(data: Record<string, unknown>): RunTaskKind {
  const toolName = String(data.tool_name ?? '').trim()
  if (toolName) return 'tool'
  const name = String(data.name ?? '').trim().toLowerCase()
  if (name === 'model') return 'model'
  if (name.includes('middleware')) return 'middleware'
  return 'task'
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
      tool_name: dataRecord.tool_name,
      tool_call: summarizeUnknown(dataRecord.tool_call),
      tool_calls: summarizeUnknown(dataRecord.tool_calls),
      result_summary: summarizeScalar(dataRecord.result_summary, 220),
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

export interface RunTaskSnapshot {
  key: string
  id: string
  name: string
  kind: RunTaskKind
  status: string
  summary: string
  ns: string[]
  updates: number
  lastTs: number
  error?: string
  toolName?: string
}

export interface RunSubagentSnapshot {
  key: string
  label: string
  ns: string[]
  status: string
  taskCount: number
  lastTs: number
}

export interface RunGraphNode {
  key: string
  kind: RunGraphNodeKind
  title: string
  summary: string
  status: string
  ts: number
}

function formatNsLabel(ns: string[] | undefined): string {
  const clean = (ns ?? [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .filter((item) => !item.startsWith('__pregel'))
  return clean.length ? clean.join(' / ') : 'root'
}

function coerceTaskName(data: Record<string, unknown>): string {
  const toolName = compactText(data.tool_name, 80)
  if (toolName) return `Tool · ${toolName}`
  return humanizeTaskName(data.name ?? data.id ?? 'Task')
}

function summarizeTaskData(data: Record<string, unknown>): string {
  const rawId = compactText(data.id, 40)
  const toolCall = asRecord(data.tool_call)
  const toolArgs = compactText(stableStringify(toolCall.args), 180)
  return [
    compactText(data.status, 40),
    compactText(data.result_summary, 180),
    toolArgs ? `args=${toolArgs}` : '',
    rawId ? `id=${rawId}` : '',
    Number(data.interrupts || 0) > 0 ? `interrupts=${Number(data.interrupts)}` : '',
    Number(data.triggers || 0) > 0 ? `triggers=${Number(data.triggers)}` : '',
  ].filter(Boolean).join(' · ')
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
    const kind = classifyTaskRecord(data)
    const key = `${formatNsLabel(ns)}::${rawId || name}`
    const existing = byKey.get(key)
    byKey.set(key, {
      key,
      id: rawId || name,
      name,
      kind,
      status: compactText(data.status, 40) || existing?.status || 'unknown',
      summary: summarizeTaskData(data),
      ns,
      updates: (existing?.updates ?? 0) + 1,
      lastTs: part.ts,
      error: compactText(data.error, 160) || existing?.error,
      toolName: compactText(data.tool_name, 80) || existing?.toolName,
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

export function graphNodesFromRunState(
  runState: DeepAgentsRunState | undefined,
): RunGraphNode[] {
  const nodes: RunGraphNode[] = []
  const parts = runState?.parts ?? []
  const startPart = parts.find((part) => part.event === 'start')

  if (startPart) {
    nodes.push({
      key: `start:${startPart.id}`,
      kind: 'start',
      title: 'Run started',
      summary: compactText(asRecord(startPart.data).query, 140),
      status: 'completed',
      ts: startPart.ts,
    })
  }

  for (const task of taskSnapshotsFromRunState(runState)) {
    if (!['tool', 'model', 'middleware'].includes(task.kind)) continue
    nodes.push({
      key: `task:${task.key}`,
      kind: task.kind === 'tool' ? 'tool' : task.kind === 'model' ? 'model' : 'middleware',
      title: task.name,
      summary: task.summary,
      status: task.status || 'unknown',
      ts: task.lastTs,
    })
  }

  for (const part of parts) {
    if (part.event === 'error') {
      const data = asRecord(part.data)
      nodes.push({
        key: `error:${part.id}`,
        kind: 'error',
        title: 'Run error',
        summary: compactText(data.message, 160),
        status: 'failed',
        ts: part.ts,
      })
    }
    if (part.event === 'final') {
      const data = asRecord(part.data)
      nodes.push({
        key: `final:${part.id}`,
        kind: 'final',
        title: 'Final answer',
        summary: compactText(data.answer, 180),
        status: 'completed',
        ts: part.ts,
      })
    }
  }

  return nodes.sort((a, b) => a.ts - b.ts)
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

export function toolCallsFromRunState(
  runState: DeepAgentsRunState | undefined,
): ExecutionToolCall[] {
  return taskSnapshotsFromRunState(runState)
    .filter((task) => task.kind === 'tool')
    .map((task, index) => ({
      key: `${task.key}-${index}`,
      name: task.name.replace(/^Tool\s*·\s*/i, '') || task.name,
      status: String(task.status || 'unknown'),
      summary: String(task.summary || ''),
      provider: inferProvider(task.toolName || task.name),
      latencyMs: 0,
      isWrite: false,
    }))
}

export function summarizeStreamPartStatus(part: DeepAgentsStreamPart): string {
  if (part.event === 'tasks') {
    const data = asRecord(part.data)
    const name = coerceTaskName(data)
    const status = compactText(data.status, 40)
    return [name, status && status !== 'completed' ? status : ''].filter(Boolean).join(' · ')
  }
  if (part.event === 'error') {
    return compactText(asRecord(part.data).message, 220) || 'Run error'
  }
  if (part.event === 'final') {
    return 'Final answer ready'
  }
  if (part.event === 'start') {
    return 'Run started'
  }
  return ''
}

export function summarizeRunStateStatus(
  runState: DeepAgentsRunState | undefined,
  isStreaming: boolean,
): string {
  const lastTask = taskSnapshotsFromRunState(runState).at(-1)
  if (lastTask) {
    if (isStreaming) {
      const status = String(lastTask.status || '').toLowerCase()
      return [lastTask.name, status && status !== 'completed' ? lastTask.status : ''].filter(Boolean).join(' · ')
    }
    return lastTask.summary || lastTask.name
  }

  const last = [...(runState?.parts ?? [])]
    .reverse()
    .find((part) => part.event === 'error' || part.event === 'final' || part.event === 'start')

  if (!last) return isStreaming ? 'Generating' : ''
  return summarizeStreamPartStatus(last)
}
