import type { MutableRefObject } from 'react'
import { useChatStore, type ChatMessage, type ChatSession } from '../stores/chatStore'
import type { AelinChatRequest, AelinToolStep } from '@/shared/api/types'

const MAX_QUERY_CHARS = 1200
const VISIBLE_TRACE_STAGES = new Set([
  'attachment_prefetch',
  'local_search',
  'file_memory_search',
  'web_search',
  'code_write',
  'forced_tool',
  'model_decision',
  'intent_router',
  'model_plan',
  'generation',
  'final_answer',
])
const TERMINAL_TRACE_STATUSES = new Set(['completed', 'failed', 'skipped'])
const RUNNING_TRACE_STATUSES = new Set(['running', 'in_progress'])

export type PendingImage = { dataUrl: string; name: string }
export type ChatStoreState = ReturnType<typeof useChatStore.getState>
type ToolEventPayload = Record<string, unknown>

function mergeToolTrace(prev: AelinToolStep[] | undefined, step: AelinToolStep): AelinToolStep[] {
  const existing = [...(prev ?? [])]
  const stage = String(step.stage || '').trim()
  if (!stage) return existing
  const status = String(step.status || '').trim().toLowerCase()
  const normalizedStep: AelinToolStep = {
    ...step,
    stage,
    status,
    detail: typeof step.detail === 'string' ? step.detail : step.detail == null ? undefined : String(step.detail),
    ts: Number.isFinite(Number(step.ts)) ? Number(step.ts) : Date.now(),
  }
  if (!existing.length) return [normalizedStep]

  let matchIndex = -1
  for (let idx = existing.length - 1; idx >= 0; idx -= 1) {
    if (String(existing[idx]?.stage || '').trim() === stage) {
      matchIndex = idx
      break
    }
  }
  if (matchIndex < 0) return [...existing, normalizedStep].slice(-160)

  const target = existing[matchIndex]
  const targetStatus = String(target?.status || '').trim().toLowerCase()
  const sameSnapshot =
    targetStatus === status &&
    String(target?.detail || '') === String(normalizedStep.detail || '') &&
    Number(target?.count || 0) === Number(normalizedStep.count || 0)
  if (sameSnapshot) return existing

  if (RUNNING_TRACE_STATUSES.has(status)) {
    if (RUNNING_TRACE_STATUSES.has(targetStatus)) {
      existing[matchIndex] = {
        ...target,
        ...normalizedStep,
        ts: Number.isFinite(Number(target?.ts)) ? Number(target.ts) : normalizedStep.ts,
      }
      return existing.slice(-160)
    }
    return [...existing, normalizedStep].slice(-160)
  }

  if (TERMINAL_TRACE_STATUSES.has(status) && RUNNING_TRACE_STATUSES.has(targetStatus)) {
    return [...existing, normalizedStep].slice(-160)
  }

  return [...existing, normalizedStep].slice(-160)
}

function shouldDisplayTraceStep(step: AelinToolStep): boolean {
  const stage = String(step.stage || '').trim().toLowerCase()
  if (!stage) return false
  if (stage.startsWith('tool_call:')) return true
  return VISIBLE_TRACE_STAGES.has(stage)
}

function compactJson(value: unknown, limit = 180): string {
  try {
    const text = JSON.stringify(value)
    if (!text) return ''
    return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}…` : text
  } catch {
    const text = String(value || '')
    return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}…` : text
  }
}

function buildSafeParamDetailParts(args: Record<string, unknown>): string[] {
  const parts: string[] = []
  const queryRaw = String(args.query || '').replace(/;/g, '，').trim()
  const query = queryRaw.length > 120 ? `${queryRaw.slice(0, 119)}…` : queryRaw
  if (query) parts.push(`query=${query}`)
  const topKRaw = Number(args.top_k ?? args.k ?? args.limit)
  const topK = Number.isFinite(topKRaw) && topKRaw > 0 ? Math.round(topKRaw) : 0
  if (topK > 0) parts.push(`top_k=${topK}`)
  const ids = Array.isArray(args.attachment_ids) ? args.attachment_ids : []
  if (ids.length > 0) parts.push(`attachment_ids=${ids.slice(0, 8).join(',')}${ids.length > 8 ? ',…' : ''}`)
  return parts
}

function stageStatusText(stageRaw: string): string {
  const stage = String(stageRaw || '').trim().toLowerCase()
  if (stage.startsWith('tool_call:')) {
    const tool = String(stage.split(':')[1] || 'tool').trim()
    return `调用 ${tool}…`
  }
  if (stage === 'attachment_prefetch') return '预处理附件…'
  if (stage === 'web_search') return '网页检索…'
  if (stage === 'local_search') return '本地检索…'
  if (stage === 'file_memory_search') return '文件检索…'
  if (stage === 'code_write') return '执行代码子任务…'
  if (stage === 'model_plan') return '生成执行计划…'
  if (stage === 'generation') return '汇总中间结果…'
  if (stage === 'final_answer') return '生成最终回答…'
  return '执行中…'
}

function buildToolEventTraceStep(event: ToolEventPayload): AelinToolStep | null {
  const phase = String(event.phase || '').trim().toLowerCase()
  if (!phase) return null
  const toolName = String(event.tool_name || event.tool || '').trim().toLowerCase()
  if (!toolName) return null
  const tcId = String(event.tc_id || '').trim()
  const roundIndex = Number(event.round_index || 0)
  const stage = String(event.stage || '').trim() || `tool_call:${toolName}:${tcId || 'evt'}`
  const ts = Date.now()

  if (phase === 'start') {
    const args =
      typeof event.args === 'object' && event.args !== null ? (event.args as Record<string, unknown>) : {}
    const detailParts = [
      `round=${Number.isFinite(roundIndex) && roundIndex > 0 ? roundIndex : 1}`,
      `tool=${toolName}`,
      ...buildSafeParamDetailParts(args),
    ]
    return {
      stage,
      status: 'running',
      detail: detailParts.join('; '),
      count: 0,
      ts,
    }
  }

  if (phase === 'partial') {
    const message = String(event.message || event.summary || '').trim()
    const args =
      typeof event.args === 'object' && event.args !== null ? (event.args as Record<string, unknown>) : {}
    const currentAction = String(event.current_action || '').trim()
    const progressLabel = String(event.progress_label || '').trim()
    const tick = Math.max(0, Number(event.tick || 0))
    const elapsedMs = Math.max(0, Number(event.elapsed_ms || 0))
    const foundCount = Math.max(0, Number(event.found_count || 0))
    const processed = Math.max(0, Number(event.processed || 0))
    const matched = Math.max(0, Number(event.matched || 0))
    const total = Math.max(0, Number(event.total || 0))
    if (!message && !currentAction && !progressLabel) return null
    const detailParts = [
      `round=${Number.isFinite(roundIndex) && roundIndex > 0 ? roundIndex : 1}`,
      `tool=${toolName}`,
      ...buildSafeParamDetailParts(args),
    ]
    if (currentAction) detailParts.push(`current_action=${compactJson(currentAction, 180)}`)
    if (progressLabel) detailParts.push(`progress_label=${progressLabel}`)
    if (tick > 0) detailParts.push(`tick=${Math.round(tick)}`)
    if (elapsedMs > 0) detailParts.push(`elapsed_ms=${Math.round(elapsedMs)}`)
    if (foundCount > 0) detailParts.push(`found_count=${Math.round(foundCount)}`)
    if (processed > 0) detailParts.push(`processed=${Math.round(processed)}`)
    if (matched > 0) detailParts.push(`matched=${Math.round(matched)}`)
    if (total > 0) detailParts.push(`total=${Math.round(total)}`)
    if (message) detailParts.push(`partial=${compactJson(message, 180)}`)
    return {
      stage,
      status: 'running',
      detail: detailParts.join('; '),
      count: 0,
      ts,
    }
  }

  if (phase === 'end') {
    const statusRaw = String(event.status || '').trim().toLowerCase()
    const status = statusRaw === 'completed' ? 'completed' : 'failed'
    const latencyMs = Math.max(0, Number(event.latency_ms || 0))
    const result = typeof event.result === 'object' && event.result !== null ? event.result : {}
    const summary = compactJson(result, 180)
    return {
      stage,
      status,
      detail: `round=${Number.isFinite(roundIndex) && roundIndex > 0 ? roundIndex : 1}; tool=${toolName}; latency_ms=${Math.round(latencyMs)}; summary=${summary}`,
      count: status === 'completed' ? 1 : 0,
      ts,
    }
  }

  if (phase === 'blocked') {
    const reason = String(event.reason || event.error || 'policy_denied').trim()
    return {
      stage,
      status: 'failed',
      detail: `round=${Number.isFinite(roundIndex) && roundIndex > 0 ? roundIndex : 1}; tool=${toolName}; blocked=${reason}`,
      count: 0,
      ts,
    }
  }

  return null
}

export function trimQueryForApi(text: string): string {
  const normalized = String(text || '').trim()
  if (normalized.length <= MAX_QUERY_CHARS) return normalized
  return `${normalized.slice(0, MAX_QUERY_CHARS - 1)}…`
}

export function normalizeAttachmentIds(attachmentIds?: number[]): number[] {
  return Array.from(new Set((attachmentIds || []).filter((id) => Number.isFinite(id) && id > 0))).slice(0, 20)
}

export function buildHistory(session?: ChatSession): Array<{ role: ChatMessage['role']; content: string }> {
  return (session?.messages ?? [])
    .slice(-20)
    .filter((message) => {
      const role = String(message.role || '').trim()
      const content = String(message.content || '').trim()
      return (role === 'user' || role === 'assistant') && content.length > 0
    })
    .map((message) => ({ role: message.role, content: String(message.content || '').trim() }))
}

export function buildUserMessage(text: string, images?: PendingImage[]): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content: text,
    images,
    timestamp: Date.now(),
  }
}

export function buildAssistantMessage(): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
  }
}

export function resolveSessionForSend(store: ChatStoreState): { sessionId: string; session?: ChatSession } {
  let sessionId = store.activeSessionId
  if (!sessionId) {
    sessionId = store.createSession()
  }
  return {
    sessionId,
    session: store.sessions.find((item) => item.id === sessionId),
  }
}

export function maybeRenameFreshSession(
  store: ChatStoreState,
  sessionId: string,
  session: ChatSession | undefined,
  text: string,
  images: PendingImage[] | undefined,
  attachmentIds: number[],
): void {
  if ((session?.messages.length ?? 0) !== 0) return

  const seed =
    String(text || '').trim() || (images?.length || attachmentIds.length ? '附件分析' : '新对话')
  const title = seed.length > 20 ? `${seed.slice(0, 20)}…` : seed
  store.renameSession(sessionId, title)
}

export function buildChatRequest(params: {
  text: string
  session: ChatSession | undefined
  history: Array<{ role: ChatMessage['role']; content: string }>
  images?: PendingImage[]
  attachmentIds: number[]
}): AelinChatRequest {
  const normalizedQuery = trimQueryForApi(String(params.text || '').trim())
  return {
    query:
      normalizedQuery ||
      (params.images?.length || params.attachmentIds.length
        ? '请先分析我上传的附件，然后给我结论和建议。'
        : ''),
    workspace: params.session?.workspace || 'default',
    history: params.history,
    images: params.images?.map((image) => ({ data_url: image.dataUrl, name: image.name })),
    attachment_ids: params.attachmentIds,
  }
}

function updateLatestAssistantToolTrace(sessionId: string, step: AelinToolStep): void {
  const state = useChatStore.getState()
  const targetSession = state.sessions.find((session) => session.id === sessionId)
  const currentTrace = targetSession?.messages.findLast((message: ChatMessage) => message.role === 'assistant')?.toolTrace
  state.updateLastAssistant(sessionId, {
    toolTrace: mergeToolTrace(currentTrace, step),
  })
}

function latestAssistantTraceForSession(store: ChatStoreState, sessionId: string): AelinToolStep[] {
  const targetSession = store.sessions.find((session) => session.id === sessionId)
  return targetSession?.messages.findLast((message: ChatMessage) => message.role === 'assistant')?.toolTrace || []
}

function latestAssistantContentForSession(store: ChatStoreState, sessionId: string): string {
  const targetSession = store.sessions.find((session) => session.id === sessionId)
  return String(targetSession?.messages.findLast((message: ChatMessage) => message.role === 'assistant')?.content || '')
}

function hasRecentEquivalentStep(trace: AelinToolStep[], step: AelinToolStep): boolean {
  const targetStage = String(step.stage || '').trim()
  const targetStatus = String(step.status || '').trim().toLowerCase()
  const targetDetail = String(step.detail || '').trim()
  if (!targetStage) return true
  const recent = trace.slice(-12)
  return recent.some((item) => {
    const stage = String(item.stage || '').trim()
    const status = String(item.status || '').trim().toLowerCase()
    const detail = String(item.detail || '').trim()
    if (stage !== targetStage || status !== targetStatus) return false
    if (!targetDetail) return true
    if (!detail) return false
    if (detail === targetDetail) return true
    return detail.includes(targetDetail) || targetDetail.includes(detail)
  })
}

function hasRunningStepForStage(trace: AelinToolStep[], stageRaw: string): boolean {
  const stage = String(stageRaw || '').trim()
  if (!stage) return false
  return trace.some((item) => {
    if (String(item.stage || '').trim() !== stage) return false
    const status = String(item.status || '').trim().toLowerCase()
    return RUNNING_TRACE_STATUSES.has(status)
  })
}

function appendOnlyDeltaContent(current: string, target: string): string {
  const currentText = String(current || '')
  const targetText = String(target || '')
  if (!targetText) return ''
  if (!currentText) return targetText
  if (targetText === currentText) return ''
  if (targetText.startsWith(currentText)) return targetText.slice(currentText.length)
  if (currentText.startsWith(targetText)) return ''

  const maxOverlap = Math.min(currentText.length, targetText.length)
  let overlap = 0
  for (let length = maxOverlap; length > 0; length -= 1) {
    if (currentText.slice(-length) === targetText.slice(0, length)) {
      overlap = length
      break
    }
  }
  if (overlap >= targetText.length) return ''
  return targetText.slice(overlap)
}

export function buildStreamCallbacks(params: {
  store: ChatStoreState
  sessionId: string
  abortRef: MutableRefObject<(() => void) | null>
  getCancel: () => () => void
}) {
  let finalAnswerStarted = false
  let resultOrganized = false

  const finalize = () => {
    if (params.abortRef.current === params.getCancel()) {
      params.abortRef.current = null
    }
    params.store.setStreaming(false)
    params.store.setStatusText('')
  }

  return {
    onIntent: (data: { intent_type?: string; time_sensitivity?: string }) => {
      params.store.setStatusText(`意图: ${data.intent_type}`)
      updateLatestAssistantToolTrace(params.sessionId, {
        stage: 'model_decision',
        status: 'completed',
        detail: `intent=${String(data.intent_type || 'unknown')}${data.time_sensitivity ? ` · time=${String(data.time_sensitivity)}` : ''}`,
        ts: Date.now(),
      })
    },
    onPlan: (data: { steps?: unknown[] }) => {
      const planSteps = Array.isArray(data.steps) ? data.steps.map((item) => String(item || '').trim()).filter(Boolean) : []
      params.store.setStatusText(`计划: ${planSteps.length || 0} 步`)
      updateLatestAssistantToolTrace(params.sessionId, {
        stage: 'model_plan',
        status: 'completed',
        detail: planSteps.length ? planSteps.map((step, idx) => `${idx + 1}. ${step}`).join('\n') : '未返回显式计划',
        ts: Date.now(),
      })
    },
    onToolStep: (step: AelinToolStep) => {
      if (!shouldDisplayTraceStep(step)) return
      const rawStatus = String(step.status || '').trim().toLowerCase()
      if (rawStatus === 'completed' || rawStatus === 'failed') {
        const existingTrace = latestAssistantTraceForSession(params.store, params.sessionId)
        if (!hasRunningStepForStage(existingTrace, step.stage)) {
          updateLatestAssistantToolTrace(params.sessionId, {
            stage: String(step.stage || ''),
            status: 'running',
            detail: stageStatusText(step.stage),
            count: 0,
            ts: Math.max(0, Number(step.ts || Date.now()) - 1),
          })
        }
      }
      params.store.setStatusText(stageStatusText(step.stage))
      updateLatestAssistantToolTrace(params.sessionId, step)
    },
    onToolEvent: (event: ToolEventPayload) => {
      const traceStep = buildToolEventTraceStep(event)
      if (!traceStep || !shouldDisplayTraceStep(traceStep)) return
      const existingTrace = latestAssistantTraceForSession(params.store, params.sessionId)
      if (hasRecentEquivalentStep(existingTrace, traceStep)) return
      params.store.setStatusText(stageStatusText(traceStep.stage))
      updateLatestAssistantToolTrace(params.sessionId, traceStep)
    },
    onCitations: (citations: NonNullable<ChatMessage['citations']>) =>
      params.store.updateLastAssistant(params.sessionId, { citations }),
    onActions: (actions: NonNullable<ChatMessage['actions']>) =>
      params.store.updateLastAssistant(params.sessionId, { actions }),
    onReplyChunk: (chunk: string) => {
      const text = String(chunk || '')
      if (text && !resultOrganized) {
        updateLatestAssistantToolTrace(params.sessionId, {
          stage: 'generation',
          status: 'running',
          detail: '正在整理检索结果…',
          ts: Date.now(),
        })
        resultOrganized = true
      }
      if (text && !finalAnswerStarted) {
        params.store.setStatusText('生成回答…')
        updateLatestAssistantToolTrace(params.sessionId, {
          stage: 'final_answer',
          status: 'running',
          detail: '开始生成回答',
          ts: Date.now(),
        })
        finalAnswerStarted = true
      }
      params.store.appendContent(params.sessionId, text)
    },
    onDone: (data: { expression?: string; memory_summary?: string; answer?: string }) => {
      if (resultOrganized) {
        updateLatestAssistantToolTrace(params.sessionId, {
          stage: 'generation',
          status: 'completed',
          detail: '已完成检索结果整理',
          ts: Date.now(),
        })
      }
      const finalAnswer = String(data.answer || '')
      const currentContent = latestAssistantContentForSession(params.store, params.sessionId)
      const delta = appendOnlyDeltaContent(currentContent, finalAnswer)
      if (delta) {
        params.store.appendContent(params.sessionId, delta)
      }
      params.store.updateLastAssistant(params.sessionId, {
        expression: data.expression,
        memorySummary: data.memory_summary,
      })
      updateLatestAssistantToolTrace(params.sessionId, {
        stage: 'final_answer',
        status: 'completed',
        detail: '已完成链路汇总并生成最终回答',
        ts: Date.now(),
      })
      finalize()
    },
    onError: (error: { message: string }) => {
      params.store.appendContent(params.sessionId, `\n\n> ⚠️ 错误: ${error.message}`)
      updateLatestAssistantToolTrace(params.sessionId, {
        stage: 'final_answer',
        status: 'failed',
        detail: String(error.message || 'stream error'),
        ts: Date.now(),
      })
      finalize()
    },
  }
}
