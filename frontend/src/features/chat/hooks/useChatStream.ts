import { useRef, useCallback, type MutableRefObject } from 'react'
import { useChatStore, type ChatMessage, type ChatSession } from '../stores/chatStore'
import { streamChat } from '@/shared/api/sse'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinAttachmentUploadResponse, AelinChatRequest, AelinToolStep } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'

const MAX_QUERY_CHARS = 1200

type PendingImage = { dataUrl: string; name: string }
type ChatStoreState = ReturnType<typeof useChatStore.getState>

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

function formatBytes(size: number): string {
  const bytes = Number.isFinite(size) ? Math.max(0, size) : 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function trimQueryForApi(text: string): string {
  const normalized = String(text || '').trim()
  if (normalized.length <= MAX_QUERY_CHARS) return normalized
  return `${normalized.slice(0, MAX_QUERY_CHARS - 1)}…`
}

function normalizeAttachmentIds(attachmentIds?: number[]): number[] {
  return Array.from(new Set((attachmentIds || []).filter((id) => Number.isFinite(id) && id > 0))).slice(0, 20)
}

function buildHistory(session?: ChatSession): Array<{ role: ChatMessage['role']; content: string }> {
  return (session?.messages ?? [])
    .slice(-20)
    .filter((message) => {
      const role = String(message.role || '').trim()
      const content = String(message.content || '').trim()
      return (role === 'user' || role === 'assistant') && content.length > 0
    })
    .map((message) => ({ role: message.role, content: String(message.content || '').trim() }))
}

function buildUserMessage(text: string, images?: PendingImage[]): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content: text,
    images,
    timestamp: Date.now(),
  }
}

function buildAssistantMessage(): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
  }
}

function resolveSessionForSend(store: ChatStoreState): { sessionId: string; session?: ChatSession } {
  let sessionId = store.activeSessionId
  if (!sessionId) {
    sessionId = store.createSession()
  }
  return {
    sessionId,
    session: store.sessions.find((item) => item.id === sessionId),
  }
}

function maybeRenameFreshSession(
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

function buildChatRequest(params: {
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

function buildStreamCallbacks(params: {
  store: ChatStoreState
  sessionId: string
  abortRef: MutableRefObject<(() => void) | null>
  getCancel: () => () => void
}) {
  const finalize = () => {
    if (params.abortRef.current === params.getCancel()) {
      params.abortRef.current = null
    }
    params.store.setStreaming(false)
    params.store.setStatusText('')
  }

  return {
    onIntent: (data: { intent_type?: string }) => params.store.setStatusText(`意图: ${data.intent_type}`),
    onPlan: (data: { steps?: unknown[] }) => params.store.setStatusText(`计划: ${data.steps?.length || 0} 步`),
    onToolStep: (step: AelinToolStep) => {
      params.store.setStatusText(`${step.stage}…`)
      updateLatestAssistantToolTrace(params.sessionId, step)
    },
    onCitations: (citations: NonNullable<ChatMessage['citations']>) =>
      params.store.updateLastAssistant(params.sessionId, { citations }),
    onActions: (actions: NonNullable<ChatMessage['actions']>) =>
      params.store.updateLastAssistant(params.sessionId, { actions }),
    onReplyChunk: (chunk: string) => params.store.appendContent(params.sessionId, chunk),
    onDone: (data: { expression?: string; memory_summary?: string }) => {
      params.store.updateLastAssistant(params.sessionId, {
        expression: data.expression,
        memorySummary: data.memory_summary,
      })
      finalize()
    },
    onError: (error: { message: string }) => {
      params.store.appendContent(params.sessionId, `\n\n> ⚠️ 错误: ${error.message}`)
      finalize()
    },
  }
}

export function useChatStream() {
  const store = useChatStore()
  const abortRef = useRef<(() => void) | null>(null)

  const send = useCallback(
    (
      text: string,
      images?: PendingImage[],
      attachmentIds?: number[],
    ) => {
      abortRef.current?.()
      abortRef.current = null

      const { sessionId, session } = resolveSessionForSend(store)
      const normalizedAttachmentIds = normalizeAttachmentIds(attachmentIds)
      const history = buildHistory(session)

      store.addMessage(sessionId, buildUserMessage(text, images))
      store.addMessage(sessionId, buildAssistantMessage())
      store.setStreaming(true)
      store.setStatusText('正在思考…')

      maybeRenameFreshSession(store, sessionId, session, text, images, normalizedAttachmentIds)

      const body = buildChatRequest({
        text,
        session,
        history,
        images,
        attachmentIds: normalizedAttachmentIds,
      })

      let cancel = () => {}
      cancel = streamChat(
        body,
        buildStreamCallbacks({
          store,
          sessionId,
          abortRef,
          getCancel: () => cancel,
        }),
      )

      abortRef.current = cancel
    },
    [store]
  )

  const captureAndSend = useCallback(async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
    if (store.isStreaming) return
    store.setStatusText(mode === 'region' ? '等待框选截图…' : '正在全屏截图…')
    try {
      const capture = await aelinApi.deviceScreenCapture({ mode })
      const prompt = String(textHint || '').trim()
      send(prompt, [{ dataUrl: capture.data_url, name: capture.name || `screen-${Date.now()}.jpg` }])
    } catch (error) {
      store.setStatusText('')
      throw error
    }
  }, [send, store])

  const uploadAttachments = useCallback(async (files: File[]): Promise<AelinAttachmentUploadResponse[]> => {
    if (store.isStreaming) return []
    const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
    if (picked.length === 0) return []

    let sessionId = store.activeSessionId
    if (!sessionId) sessionId = store.createSession() || store.activeSessionId
    const resolvedSessionId = String(sessionId || '')
    const session = store.sessions.find(s => s.id === sessionId)
    const workspace = session?.workspace || 'default'

    store.setStatusText('附件处理中…')
    try {
      const settled = await Promise.allSettled(
        picked.map((file) => aelinApi.uploadAttachment(file, { workspace, session_id: resolvedSessionId }))
      )
      const uploaded: AelinAttachmentUploadResponse[] = []
      const failedNames: string[] = []
      settled.forEach((item, index) => {
        if (item.status === 'fulfilled') {
          uploaded.push(item.value)
          return
        }
        failedNames.push(picked[index]?.name || `attachment-${index + 1}`)
      })
      store.setStatusText('')
      if (uploaded.length === 0 && failedNames.length > 0) {
        throw new Error(`附件上传失败：${failedNames.join('、')}`)
      }
      return uploaded
    } catch (error) {
      store.setStatusText('')
      throw error
    }
  }, [store])

  const sendWithAttachments = useCallback(async (attachments: AelinAttachmentUploadResponse[], textHint = '') => {
    if (store.isStreaming) return
    const rows = Array.from(attachments || []).slice(0, MAX_PENDING_ATTACHMENTS)
    if (rows.length === 0) return
    const attachmentIds = rows.map((item) => Number(item.attachment_id)).filter((id) => Number.isFinite(id) && id > 0)
    if (attachmentIds.length === 0) return
    const attachmentBlock = `附件清单:\n${rows.map((item) => {
      const parsed = Number(item.chunk_count || 0)
      const parsedNote = parsed > 0 ? `已解析 ${parsed} chunks` : '已接入'
      return `- ${item.file_name || 'attachment'} (${formatBytes(Number(item.size_bytes || 0))}) [${parsedNote}]`
    }).join('\n')}`
    const finalPrompt = trimQueryForApi([String(textHint || '').trim(), attachmentBlock].filter(Boolean).join('\n\n').trim())
    send(finalPrompt || '我上传了附件，请先基于附件内容回答。', undefined, attachmentIds)
  }, [send, store])

  const stop = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    store.setStreaming(false)
    store.setStatusText('')
  }, [store])

  return { send, captureAndSend, uploadAttachments, sendWithAttachments, stop }
}
