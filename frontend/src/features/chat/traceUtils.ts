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

function normalizeStage(stage: string | undefined): string {
  return String(stage || '').trim()
}

function normalizeStatus(status: string | undefined): string {
  return String(status || '').trim().toLowerCase() || 'unknown'
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

export function extractPlaneTaskMeta(trace: AelinToolStep[] | undefined): PlaneTaskMeta | null {
  if (!trace || trace.length === 0) return null

  const planeSteps = trace.filter((step) => normalizeStage(step.stage) === 'agent_loop_plane')
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
