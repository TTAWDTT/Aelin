import type { AelinToolStep } from '@/shared/api/types'

export type ToolCallKind =
  | 'core'
  | 'llm_tool'
  | 'gws'
  | 'device'
  | 'web'

export interface ToolCallMeta {
  index: number
  name: string
  provider: string
  status: string
  detail: string
  isWrite: boolean
  latencyMs: number
  kind: ToolCallKind
}

export type RunNodeType =
  | 'preflight'
  | 'agent'
  | 'plan'
  | 'tool'
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
    .replace(/[_\.]/g, ' ')
    .replace(/\b\w/g, (m) => m.toUpperCase())
}

function inferProviderFromToolName(name: string): string {
  const n = String(name || '').toLowerCase()
  if (!n) return 'aelin-core'
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
  return false
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
    let groupId: string | undefined

    if (stage.startsWith('preflight')) {
      type = 'preflight'
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
      if (toolName.startsWith('memory') || toolName.includes('memory')) {
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
      groupId,
      provider,
      meta: Object.keys(meta).length ? meta : undefined,
      raw: step,
    }

    nodes.push(node)
  })

  return nodes
}

export function extractToolCalls(trace: AelinToolStep[] | undefined): ToolCallMeta[] {
  if (!trace || trace.length === 0) return []

  const calls: ToolCallMeta[] = []
  for (const [index, step] of trace.entries()) {
    const stage = normalizeStage(step.stage)
    const status = normalizeStatus(step.status)
    const detail = String(step.detail || '')

    if (stage === 'agent_loop_tool') {
      const head = detail.split(':', 1)[0]?.trim() || ''
      const name = head || 'tool'
      calls.push({
        index,
        name,
        provider: inferProviderFromToolName(name),
        status,
        detail,
        isWrite: looksLikeWriteCall(name, detail),
        latencyMs: extractLatencyFromDetail(detail),
        kind: inferKindFromToolName(name),
      })
      continue
    }

    if (stage === 'agent_loop_read_batch') {
      calls.push({
        index,
        name: 'read_batch',
        provider: 'aelin-core',
        status,
        detail,
        isWrite: false,
        latencyMs: extractLatencyFromDetail(detail),
        kind: 'core',
      })
      continue
    }

    if (stage === 'attachment_prefetch') {
      calls.push({
        index,
        name: 'attachment_search',
        provider: 'aelin-core',
        status,
        detail,
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
} {
  const tools = extractToolCalls(trace)
  return { tools }
}
