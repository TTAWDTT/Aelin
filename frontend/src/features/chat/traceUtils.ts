import type { DeepAgentsToolRun } from '@/shared/api/types'

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
  | 'tool'
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
  raw: DeepAgentsToolRun
}

function normalizeStatus(status: string | undefined): string {
  return String(status || '').trim().toLowerCase() || 'unknown'
}

export function formatStageLabel(label: string | undefined): string {
  const s = String(label || '').trim()
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

export function buildRunNodesFromToolRuns(toolRuns: DeepAgentsToolRun[] | undefined): RunNode[] {
  if (!toolRuns || toolRuns.length === 0) return []

  return toolRuns.map((run, index) => {
    const name = String(run.name || 'tool').trim() || 'tool'
    const status = normalizeStatus(run.status)
    const provider = inferProviderFromToolName(name)
    const kind = inferKindFromToolName(name)
    const isWrite = typeof run.is_write === 'boolean' ? !!run.is_write : false
    const latencyMs = typeof run.latency_ms === 'number' && run.latency_ms > 0 ? run.latency_ms : 0
    const summary = String(run.summary || run.error || '').trim()

    const meta: Record<string, unknown> = {
      kind,
      isWrite,
      latencyMs,
    }
    if (summary) meta.summary = summary

    return {
      id: `tool-${index}-${name}`,
      index,
      type: 'tool',
      label: name,
      status,
      provider,
      meta,
      raw: run,
    }
  })
}

export function extractToolCallsFromToolRuns(toolRuns: DeepAgentsToolRun[] | undefined): ToolCallMeta[] {
  if (!toolRuns || toolRuns.length === 0) return []

  return toolRuns.map((run, index) => {
    const name = String(run.name || 'tool').trim() || 'tool'
    const provider = inferProviderFromToolName(name)
    const kind = inferKindFromToolName(name)
    const isWrite = typeof run.is_write === 'boolean' ? !!run.is_write : false
    const latencyMs = typeof run.latency_ms === 'number' && run.latency_ms > 0 ? run.latency_ms : 0
    const detail = String(run.summary || run.error || '').trim()

    return {
      index,
      name,
      provider,
      status: normalizeStatus(run.status),
      detail,
      isWrite,
      latencyMs,
      kind,
    }
  })
}
