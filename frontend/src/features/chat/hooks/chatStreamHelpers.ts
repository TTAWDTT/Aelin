import type { MutableRefObject } from 'react'
import { useChatStore, type ChatMessage, type ChatSession } from '../stores/chatStore'
import type { AelinChatRequest, AelinToolStep } from '@/shared/api/types'

const MAX_QUERY_CHARS = 1200
const STREAM_FLUSH_DELAY_MS = 32

export type PendingImage = { dataUrl: string; name: string }
export type ChatStoreState = ReturnType<typeof useChatStore.getState>

function mergeToolTrace(prev: AelinToolStep[] | undefined, step: AelinToolStep): AelinToolStep[] {
  const existing = [...(prev ?? [])]
  const stage = String(step.stage || '').trim()
  if (!stage) return existing

  const index = existing.findIndex((item) => String(item.stage || '').trim() === stage)
  if (index === -1) return [...existing, step]

  existing[index] = {
    ...existing[index],
    ...step,
    stage,
  }
  return existing
}

export function formatBytes(size: number): string {
  const bytes = Number.isFinite(size) ? Math.max(0, size) : 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
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

export function buildStreamCallbacks(params: {
  store: ChatStoreState
  sessionId: string
  abortRef: MutableRefObject<(() => void) | null>
  getCancel: () => () => void
}) {
  let pendingReplyChunk = ''
  let flushTimer: ReturnType<typeof setTimeout> | null = null
  let active = true

  const flushReplyChunk = () => {
    if (!active) return
    if (flushTimer) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
    if (!pendingReplyChunk) return
    params.store.appendContent(params.sessionId, pendingReplyChunk)
    pendingReplyChunk = ''
  }

  const queueReplyChunk = (chunk: string) => {
    if (!active) return
    pendingReplyChunk += chunk
    if (flushTimer) return
    flushTimer = setTimeout(flushReplyChunk, STREAM_FLUSH_DELAY_MS)
  }

  const dispose = () => {
    active = false
    pendingReplyChunk = ''
    if (flushTimer) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
  }

  const finalize = () => {
    if (!active) return
    flushReplyChunk()
    if (params.abortRef.current === params.getCancel()) {
      params.abortRef.current = null
    }
    params.store.setStreaming(false)
    params.store.setStatusText('')
    active = false
  }

  return {
    dispose,
    onIntent: (data: { intent_type?: string }) => {
      if (!active) return
      params.store.setStatusText(`意图: ${data.intent_type}`)
    },
    onPlan: (data: { steps?: unknown[] }) => {
      if (!active) return
      params.store.setStatusText(`计划: ${data.steps?.length || 0} 步`)
    },
    onToolStep: (step: AelinToolStep) => {
      if (!active) return
      params.store.setStatusText(`${step.stage}…`)
      updateLatestAssistantToolTrace(params.sessionId, step)
    },
    onCitations: (citations: NonNullable<ChatMessage['citations']>) =>
      active ? params.store.updateLastAssistant(params.sessionId, { citations }) : undefined,
    onActions: (actions: NonNullable<ChatMessage['actions']>) =>
      active ? params.store.updateLastAssistant(params.sessionId, { actions }) : undefined,
    onReplyChunk: (chunk: string) => queueReplyChunk(chunk),
    onDone: (data: { expression?: string; memory_summary?: string }) => {
      if (!active) return
      params.store.updateLastAssistant(params.sessionId, {
        expression: data.expression,
        memorySummary: data.memory_summary,
      })
      finalize()
    },
    onError: (error: { message: string }) => {
      if (!active) return
      queueReplyChunk(`\n\n> ⚠️ 错误: ${error.message}`)
      finalize()
    },
  }
}
