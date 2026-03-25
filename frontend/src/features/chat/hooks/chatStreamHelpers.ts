import type { MutableRefObject } from 'react'
import { useChatStore, type ChatMessage, type ChatSession } from '../stores/chatStore'
import type { ChatRequest, DeepAgentsStreamPart, DeepAgentsStreamUpdate } from '@/shared/api/types'
import { appendRunStatePart, summarizeStreamPartStatus } from '../executionEventUtils'

const MAX_QUERY_CHARS = 1200

export type PendingImage = { dataUrl: string; name: string }
export type ChatStoreState = ReturnType<typeof useChatStore.getState>

function normalizeAssistantMarkdown(text: string): string {
  const normalized = String(text || '').replace(/\r\n/g, '\n')
  return normalized.replace(/^(#{1,6})(\S)/gm, '$1 $2')
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
}): ChatRequest {
  const normalizedQuery = trimQueryForApi(String(params.text || '').trim())
  return {
    query:
      normalizedQuery ||
      (params.images?.length || params.attachmentIds.length
        ? '请先分析我上传的附件，然后给我结论和建议。'
        : ''),
    source: 'chat_ui',
    workspace: params.session?.workspace || 'default',
    history: params.history,
    images: params.images?.map((image) => ({ data_url: image.dataUrl, name: image.name })),
    attachment_ids: params.attachmentIds,
  }
}

function appendRunState(sessionId: string, part: DeepAgentsStreamPart): void {
  const state = useChatStore.getState()
  const targetSession = state.sessions.find((session) => session.id === sessionId)
  if (!targetSession) return
  let currentRunState: ChatMessage['runState']
  for (let i = targetSession.messages.length - 1; i >= 0; i -= 1) {
    const msg = targetSession.messages[i]
    if (msg.role === 'assistant') {
      currentRunState = msg.runState
      break
    }
  }
  state.updateLastAssistant(sessionId, {
    runState: appendRunStatePart(currentRunState, part),
  })
}

export function buildStreamCallbacks(params: {
  store: ChatStoreState
  sessionId: string
  abortRef: MutableRefObject<(() => void) | null>
  getCancel: () => () => void
}) {
  let lastFinalAnswer = ''

  const finalize = () => {
    if (params.abortRef.current === params.getCancel()) {
      params.abortRef.current = null
    }
    params.store.setStreaming(false)
    params.store.setStatusText('')
    params.store.setLastErrorCode(null)
  }

  return {
    onUpdate: (update: DeepAgentsStreamUpdate) => {
      const part: DeepAgentsStreamPart | undefined = update.part
      if (part) {
        const partStatus = summarizeStreamPartStatus(part)
        if (partStatus) {
          params.store.setStatusText(partStatus)
        }
        appendRunState(params.sessionId, part)
      }

      if (Array.isArray(update.citations)) {
        params.store.updateLastAssistant(params.sessionId, { citations: update.citations })
      }

      if (Array.isArray(update.actions)) {
        params.store.updateLastAssistant(params.sessionId, { actions: update.actions })
      }

      if (typeof update.textDelta === 'string' && update.textDelta) {
        params.store.appendContent(params.sessionId, update.textDelta)
      }

      if (typeof update.finalAnswer === 'string' && update.finalAnswer.trim()) {
        lastFinalAnswer = normalizeAssistantMarkdown(update.finalAnswer)
        params.store.updateLastAssistant(params.sessionId, { content: lastFinalAnswer })
      }

      if (update.error) {
        const error = update.error
        // 仅在当前助手消息尚无任何内容时，才在对话中插入可见错误提示。
        // 若已经有部分或完整回答（例如 agent_loop partial_result），
        // 则将网络/传输异常视为非致命，不再打断用户视线。
        const state = useChatStore.getState()
        const session = state.sessions.find((s) => s.id === params.sessionId)
        const lastAssistant =
          session?.messages
            .slice()
            .reverse()
            .find((m) => m.role === 'assistant') ?? null
        const hasAnswer =
          !!lastAssistant && String(lastAssistant.content || '').trim().length > 0

        if (!hasAnswer) {
          params.store.appendContent(params.sessionId, `\n\n> ⚠️ 错误: ${error.message}`)
        }
        if (error.code) {
          params.store.setLastErrorCode(String(error.code))
        }
        finalize()
        return
      }

      if (update.done) {
        if (lastFinalAnswer) {
          params.store.updateLastAssistant(params.sessionId, { content: lastFinalAnswer })
        }
        finalize()
      }
    },
  }
}
