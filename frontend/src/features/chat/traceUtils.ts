import type { AelinToolStep } from '@/shared/api/types'

export type PlaneTaskState =
  | 'queued'
  | 'running'
  | 'waiting_user'
  | 'blocked'
  | 'completed'
  | 'failed'
  | 'unknown'

export interface PlaneTaskMeta {
  plane: string
  state: PlaneTaskState
  summary?: string
  requiresUserInput?: boolean
}

export type ToolCallKind =
  | 'core'
  | 'llm_tool'
  | 'plane_tool'
  | 'gws'
  | 'device'
  | 'web'

export interface ToolCallMeta {
  name: string
  provider: string
  status: string
  detail: string
  round: number
  isWrite: boolean
  latencyMs: number
  kind: ToolCallKind
}

export type RunNodeType =
  | 'preflight'
  | 'agent'
  | 'plan'
  | 'tool'
  | 'plane'
  | 'memory'
  | 'fs'
  | 'error'
  | 'other'

export interface RunNode {
  id: string
  index: number
  type: RunNodeType
  label: string
  status: string
  round?: number
  parentId?: string
  groupId?: string
  provider?: string
  meta?: Record<string, unknown>
  raw: AelinToolStep
}

function normalizeStage(stage: string | undefined): string {
  return String(stage || '').trim()
}

function normalizeStatus(status: string | undefined): string {
  return String(status || '').trim().toLowerCase() || 'unknown'
}

export function formatStageLabel(stage: string | undefined): string {
  const s = String(stage || '').trim()
  if (!s) return 'Step'
  return s
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (m) => m.toUpperCase())
}

function inferProviderFromToolName(name: string): string {
  const n = String(name || '').toLowerCase()
  if (!n) return 'aelin-core'
  if (n === 'plane' || n.startsWith('plane_') || n.includes('pinchtab')) return 'plane'
  if (
    n.startsWith('gws') ||
    n.startsWith('gmail') ||
    n.startsWith('drive') ||
    n.startsWith('sheets') ||
    n.startsWith('calendar')
  ) {
    return 'google'
  }
  if (n === 'web_search' || n.startsWith('web_')) return 'web'
  if (n.startsWith('device') || n.startsWith('screen_')) return 'device'
  return 'aelin-core'
}

function inferKindFromToolName(name: string): ToolCallKind {
  const n = String(name || '').toLowerCase()
  if (!n) return 'llm_tool'
  if (n === 'plane' || n.startsWith('plane_') || n.includes('pinchtab')) return 'plane_tool'
  if (
    n === 'google_workspace' ||
    n.startsWith('gws') ||
    n.startsWith('gmail') ||
    n.startsWith('drive') ||
    n.startsWith('sheets') ||
    n.startsWith('calendar')
  ) {
    return 'gws'
  }
  if (n === 'web_search' || n.startsWith('web_')) return 'web'
  if (n.startsWith('device') || n.startsWith('screen_')) return 'device'
  return 'llm_tool'
}

function looksLikeWriteCall(name: string, detail: string): boolean {
  const n = String(name || '').toLowerCase()
  const d = String(detail || '').toLowerCase()
  if (!n) return false
  if (n === 'device' && d.includes('open_url')) return true
  if (n === 'google_workspace') {
    if (d.includes('docs_create')) return true
    if (d.includes('gmail_send')) return true
    if (d.includes('gmail_draft')) return true
    if (d.includes('calendar_create_event')) return true
  }
  if (n === 'plane' || n.startsWith('plane_') || n.includes('pinchtab')) return true
  return false
}

function extractRoundFromDetail(detail: string): number {
  const text = String(detail || '')
  const idx = text.indexOf('round=')
  if (idx < 0) return 1
  const after = text.slice(idx + 'round='.length)
  const token = after.split(/[\s;:,]/, 1)[0]
  const num = Number.parseInt(token || '', 10)
  if (!Number.isFinite(num) || num <= 0) return 1
  return num
}

function extractLatencyFromDetail(detail: string): number {
  const text = String(detail || '').toLowerCase()
  const key = 'latency_ms='
  const idx = text.indexOf(key)
  if (idx < 0) return 0
  const after = text.slice(idx + key.length)
  const token = after.split(/[\s;:,]/, 1)[0]
  const num = Number.parseInt(token || '', 10)
  if (!Number.isFinite(num) || num < 0) return 0
  return num
}

interface PlaneDetailMeta {
  taskId?: string
  state?: PlaneTaskState
  goal?: string
  requiresUserInput?: boolean
}

function parsePlaneDetail(detail: string): PlaneDetailMeta {
  const text = String(detail || '')
  const meta: PlaneDetailMeta = {}

  const stateIndex = text.indexOf('state=')
  if (stateIndex >= 0) {
    const after = text.slice(stateIndex + 'state='.length)
    const token = after.split(/[;,\s]/, 1)[0]?.trim() || ''
    const lowered = token.toLowerCase()
    if (lowered === 'waiting_user') meta.state = 'waiting_user'
    else if (lowered === 'running') meta.state = 'running'
    else if (lowered === 'queued') meta.state = 'queued'
    else if (lowered === 'blocked') meta.state = 'blocked'
    else if (lowered === 'completed') meta.state = 'completed'
    else if (lowered === 'failed') meta.state = 'failed'
  }

  const taskIndex = text.indexOf('task_id=')
  if (taskIndex >= 0) {
    const after = text.slice(taskIndex + 'task_id='.length)
    meta.taskId = after.split(/[;,\s]/, 1)[0]?.trim() || undefined
  }

  const goalIndex = text.indexOf('goal=')
  if (goalIndex >= 0) {
    const after = text.slice(goalIndex + 'goal='.length)
    meta.goal = after.split('\n', 1)[0]?.trim() || undefined
  }

  const loweredText = text.toLowerCase()
  if (loweredText.includes('waiting_user') || loweredText.includes('waiting for user')) {
    meta.requiresUserInput = true
  }

  return meta
}

export function buildRunNodes(trace: AelinToolStep[] | undefined): RunNode[] {
  if (!trace || trace.length === 0) return []

  const nodes: RunNode[] = []

  trace.forEach((step, index) => {
    const stage = normalizeStage(step.stage)
    const status = normalizeStatus(step.status)
    const detail = String(step.detail || '')

    let type: RunNodeType = 'other'
    let label = formatStageLabel(stage)
    let provider: string | undefined
    const meta: Record<string, unknown> = {}
    let round: number | undefined
    let groupId: string | undefined

    if (stage.startsWith('preflight_')) {
      type = 'preflight'
    } else if (
      stage === 'plane_delegate' ||
      stage === 'plane_status' ||
      stage === 'plane_continue' ||
      stage === 'plane_close' ||
      stage === 'plane_catalog'
    ) {
      type = 'plane'
      provider = 'plane'
      const planeMeta = parsePlaneDetail(detail)
      meta.state = planeMeta.state ?? 'unknown'
      meta.taskId = planeMeta.taskId
      meta.goal = planeMeta.goal
      meta.requiresUserInput = planeMeta.requiresUserInput ?? false
      groupId = planeMeta.taskId
      round = extractRoundFromDetail(detail)
      label = formatStageLabel(stage)
    } else if (stage === 'agent_loop_tool') {
      const head = detail.split(':', 1)[0]?.trim() || ''
      const toolName = head || 'tool'
      const kind = inferKindFromToolName(toolName)
      provider = inferProviderFromToolName(toolName)
      const latencyMs = extractLatencyFromDetail(detail)
      const isWrite = looksLikeWriteCall(toolName, detail)

      meta.toolName = toolName
      meta.kind = kind
      meta.isWrite = isWrite
      meta.latencyMs = latencyMs

      label = toolName
      round = extractRoundFromDetail(detail)

      if (kind === 'plane_tool') {
        type = 'tool'
      } else if (toolName.startsWith('memory') || toolName.includes('memory')) {
        type = 'memory'
      } else if (toolName.startsWith('file') || toolName.startsWith('fs_')) {
        type = 'fs'
      } else {
        type = 'tool'
      }
    } else if (stage === 'agent_loop_read_batch' || stage === 'attachment_prefetch') {
      type = 'tool'
      provider = 'aelin-core'
      meta.kind = 'core'
      meta.isWrite = false
      meta.latencyMs = extractLatencyFromDetail(detail)
      round = extractRoundFromDetail(detail)
      label = formatStageLabel(stage)
    } else if (
      stage.startsWith('agent_') ||
      (stage.startsWith('agent_loop_') && stage !== 'agent_loop_read_batch' && stage !== 'agent_loop_tool') ||
      stage.startsWith('deepagents_')
    ) {
      type = stage.includes('plan') ? 'plan' : 'agent'
      label = formatStageLabel(stage)
    }

    if (status === 'failed' || status.includes('error')) {
      if (type === 'other') type = 'error'
    }

    const node: RunNode = {
      id: `node-${index}-${stage || 'step'}`,
      index,
      type,
      label,
      status,
      round,
      groupId,
      provider,
      meta: Object.keys(meta).length ? meta : undefined,
      raw: step,
    }

    nodes.push(node)
  })

  return nodes
}

export function extractPlaneTaskMeta(trace: AelinToolStep[] | undefined): PlaneTaskMeta | null {
  if (!trace || trace.length === 0) return null

  const planeSteps = trace.filter((step) => {
    const stage = normalizeStage(step.stage)
    return (
      stage === 'plane_delegate' ||
      stage === 'plane_status' ||
      stage === 'plane_continue' ||
      stage === 'plane_close' ||
      stage === 'plane_catalog'
    )
  })
  if (planeSteps.length === 0) return null

  const last = planeSteps[planeSteps.length - 1]
  const detail = String(last.detail || '')

  let stateText = ''
  const stateIndex = detail.indexOf('state=')
  if (stateIndex >= 0) {
    const after = detail.slice(stateIndex + 'state='.length)
    stateText = after.split(';', 1)[0]?.trim() || ''
  }

  let state: PlaneTaskState = 'unknown'
  const lowered = stateText.toLowerCase()
  if (lowered === 'waiting_user') state = 'waiting_user'
  else if (lowered === 'running') state = 'running'
  else if (lowered === 'queued') state = 'queued'
  else if (lowered === 'blocked') state = 'blocked'
  else if (lowered === 'completed') state = 'completed'
  else if (lowered === 'failed') state = 'failed'

  const requiresUserInput = detail.includes('waiting_user') || lowered === 'waiting_user'

  // 当前仅有 browser plane，后续可根据 trace 中的更多字段扩展。
  const plane = 'browser'

  return {
    plane,
    state,
    summary: detail || undefined,
    requiresUserInput,
  }
}

export function extractToolCalls(trace: AelinToolStep[] | undefined): ToolCallMeta[] {
  if (!trace || trace.length === 0) return []

  const calls: ToolCallMeta[] = []
  for (const step of trace) {
    const stage = normalizeStage(step.stage)
    const status = normalizeStatus(step.status)
    const detail = String(step.detail || '')

    if (stage === 'agent_loop_tool') {
      const head = detail.split(':', 1)[0]?.trim() || ''
      const name = head || 'tool'
      calls.push({
        name,
        provider: inferProviderFromToolName(name),
        status,
        detail,
        round: extractRoundFromDetail(detail),
        isWrite: looksLikeWriteCall(name, detail),
        latencyMs: extractLatencyFromDetail(detail),
        kind: inferKindFromToolName(name),
      })
      continue
    }

    if (stage === 'agent_loop_read_batch') {
      calls.push({
        name: 'read_batch',
        provider: 'aelin-core',
        status,
        detail,
        round: extractRoundFromDetail(detail),
        isWrite: false,
        latencyMs: extractLatencyFromDetail(detail),
        kind: 'core',
      })
      continue
    }

    if (stage === 'attachment_prefetch') {
      calls.push({
        name: 'attachment_search',
        provider: 'aelin-core',
        status,
        detail,
        round: extractRoundFromDetail(detail),
        isWrite: false,
        latencyMs: extractLatencyFromDetail(detail),
        kind: 'core',
      })
    }
  }

  return calls
}

export function buildToolSummary(trace: AelinToolStep[] | undefined): {
  tools: ToolCallMeta[]
  plane?: PlaneTaskMeta | null
} {
  const plane = extractPlaneTaskMeta(trace)
  const tools = extractToolCalls(trace)
  return { tools, plane }
}
