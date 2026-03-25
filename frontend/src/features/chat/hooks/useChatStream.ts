import { useCallback, useEffect, useMemo } from 'react'
import { useStream } from '@langchain/react'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinAttachmentUploadResponse } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import { useChatI18n } from '../chatI18n'
import type { ChatRuntimeStream, ChatStreamState } from '../executionStreamUtils'
import { useChatStore } from '../stores/chatStore'
import {
  buildAssistantMessage,
  buildHumanStreamMessage,
  buildSessionHistoryMessages,
  buildUserMessage,
  formatBytes,
  streamMessagesToChatMessages,
  trimQueryForApi,
  type PendingImage,
} from './chatStreamHelpers'
import { AelinUseStreamTransport } from './aelinUseStreamTransport'

export type { ChatRuntimeStream, ChatStreamState }

export function useChatStream() {
  const store = useChatStore()
  const { t } = useChatI18n()
  const session = store.sessions.find((item) => item.id === store.activeSessionId)

  const transport = useMemo(() => new AelinUseStreamTransport({
    apiUrl: `${import.meta.env.VITE_API_BASE || ''}/api/v1/deepagents/chat/stream`,
    getToken: () => localStorage.getItem('token'),
    getHistoryMessages: (threadId) => {
      const state = useChatStore.getState()
      const target = state.sessions.find((item) => item.id === threadId)
      return buildSessionHistoryMessages(target)
    },
    getWorkspace: (threadId) => {
      const state = useChatStore.getState()
      const target = state.sessions.find((item) => item.id === threadId)
      return target?.workspace || 'default'
    },
    getSource: () => 'chat_ui',
  }), [])

  const stream = useStream<ChatStreamState>({
    transport,
    threadId: store.activeSessionId,
    messagesKey: 'messages',
    initialValues: {
      messages: buildSessionHistoryMessages(session) as Array<Record<string, unknown>>,
    },
    onCustomEvent: (event, { mutate }) => {
      const record = event && typeof event === 'object' && !Array.isArray(event)
        ? event as Record<string, unknown>
        : {}
      const kind = String(record.kind || '')
      if (kind === 'topology') {
        mutate((prev) => ({
          ...prev,
          topology: (record.topology as Record<string, unknown> | undefined),
        }))
      }
    },
    onError: (error) => {
      store.setStatusText(String((error as Error)?.message || 'Stream error'))
    },
  })

  useEffect(() => {
    store.setStreaming(stream.isLoading)
    if (!stream.isLoading && store.statusText === t('status.thinking')) {
      store.setStatusText('')
    }
  }, [store, stream.isLoading, t])

  useEffect(() => {
    if (!store.activeSessionId) return
    if (stream.messages.length === 0) return

    const state = useChatStore.getState()
    const currentSession = state.sessions.find((item) => item.id === store.activeSessionId)
    if (!currentSession) return

    const nextMessages = streamMessagesToChatMessages(
      stream.messages as any,
      currentSession.messages,
      stream.isLoading,
    )
    if (nextMessages.length === 0) return
    state.setSessionMessages(currentSession.id, nextMessages)
  }, [store.activeSessionId, stream.isLoading, stream.messages])

  const send = useCallback(
    async (text: string, images?: PendingImage[], attachmentIds?: number[]) => {
      let sessionId = store.activeSessionId
      if (!sessionId) {
        sessionId = store.createSession()
      }
      const currentState = useChatStore.getState()
      const currentSession = currentState.sessions.find((item) => item.id === sessionId)
      const normalizedAttachmentIds = Array.from(new Set((attachmentIds || []).filter((id) => Number.isFinite(id) && id > 0))).slice(0, 20)
      const prompt = trimQueryForApi(String(text || '').trim())
      const visibleText =
        prompt
        || (images?.length
          ? '请结合这些图片帮我分析。'
          : normalizedAttachmentIds.length
            ? '请先分析我上传的附件。'
            : '')
      if (!visibleText && !images?.length && normalizedAttachmentIds.length === 0) return

      if ((currentSession?.messages.length ?? 0) === 0) {
        const seed = visibleText || '新对话'
        currentState.renameSession(sessionId, seed.length > 20 ? `${seed.slice(0, 20)}…` : seed)
      }

      currentState.addMessage(sessionId, buildUserMessage(visibleText, images))
      currentState.addMessage(sessionId, buildAssistantMessage())
      currentState.setStreaming(true)
      currentState.setStatusText(t('status.thinking'))
      currentState.setLastErrorCode(null)

      const humanMessage = buildHumanStreamMessage(prompt, images)

      try {
        await stream.submit(
          { messages: [humanMessage] as any },
          {
            context: {
              workspace: currentSession?.workspace || 'default',
              source: 'chat_ui',
              attachment_ids: normalizedAttachmentIds,
            } as any,
            optimisticValues: (prev) => ({
              ...(prev || {}),
              messages: [
                ...(((prev?.messages as Array<Record<string, unknown>> | undefined) ?? buildSessionHistoryMessages(currentSession)) as Array<Record<string, unknown>>),
                humanMessage as any,
              ],
            }),
          },
        )
      } catch (error) {
        currentState.setStreaming(false)
        currentState.setStatusText(String((error as Error)?.message || 'Stream error'))
      }
    },
    [store, stream, t],
  )

  const stop = useCallback(() => {
    void stream.stop()
    store.setStreaming(false)
    store.setStatusText(t('status.cancelled'))
    store.setLastErrorCode(null)
  }, [store, stream, t])

  const captureAndSend = useCallback(
    async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
      if (store.isStreaming) return
      store.setStatusText(
        mode === 'region' ? t('status.capture.region') : t('status.capture.fullscreen'),
      )
      try {
        const capture = await aelinApi.deviceScreenCapture({ mode })
        const prompt = String(textHint || '').trim()
        await send(prompt, [{ dataUrl: capture.data_url, name: capture.name || `screen-${Date.now()}.jpg` }])
      } catch (error) {
        store.setStatusText('')
        throw error
      }
    },
    [send, store, t],
  )

  const uploadAttachments = useCallback(
    async (files: File[]): Promise<AelinAttachmentUploadResponse[]> => {
      if (store.isStreaming) return []
      const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
      if (picked.length === 0) return []

      let sessionId = store.activeSessionId
      if (!sessionId) sessionId = store.createSession() || store.activeSessionId
      const resolvedSessionId = String(sessionId || '')
      const currentSession = useChatStore.getState().sessions.find((item) => item.id === sessionId)
      const workspace = currentSession?.workspace || 'default'

      store.setStatusText(t('status.attach.processing'))
      try {
        const settled = await Promise.allSettled(
          picked.map((file) => aelinApi.uploadAttachment(file, { workspace, session_id: resolvedSessionId })),
        )
        const uploaded: AelinAttachmentUploadResponse[] = []
        const failedNames: string[] = []
        settled.forEach((result, index) => {
          if (result.status === 'fulfilled') {
            uploaded.push(result.value)
            return
          }
          failedNames.push(picked[index]?.name || `attachment-${index + 1}`)
        })
        store.setStatusText('')
        if (uploaded.length === 0 && failedNames.length > 0) {
          throw new Error(t('composer.attach.partialFail', { names: failedNames.join(', ') }))
        }
        return uploaded
      } catch (error) {
        store.setStatusText('')
        throw error
      }
    },
    [store, t],
  )

  const sendWithAttachments = useCallback(
    async (attachments: AelinAttachmentUploadResponse[], textHint = '') => {
      if (store.isStreaming) return
      const rows = Array.from(attachments || []).slice(0, MAX_PENDING_ATTACHMENTS)
      if (rows.length === 0) return
      const attachmentIds = rows
        .map((item) => Number(item.attachment_id))
        .filter((id) => Number.isFinite(id) && id > 0)
      if (attachmentIds.length === 0) return
      const attachmentBlock = `附件清单:\n${rows.map((item) => {
        const parsed = Number(item.chunk_count || 0)
        const parsedNote = parsed > 0 ? `已解析 ${parsed} chunks` : '已接入'
        return `- ${item.file_name || 'attachment'} (${formatBytes(Number(item.size_bytes || 0))}) [${parsedNote}]`
      }).join('\n')}`
      const finalPrompt = trimQueryForApi(
        [String(textHint || '').trim(), attachmentBlock].filter(Boolean).join('\n\n').trim(),
      )
      await send(finalPrompt || '我上传了附件，请先基于附件内容回答。', undefined, attachmentIds)
    },
    [send, store],
  )

  return {
    send,
    captureAndSend,
    uploadAttachments,
    sendWithAttachments,
    stop,
    stream,
  }
}
