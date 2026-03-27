import { useCallback, useEffect, useMemo } from 'react'
import type { AnyStreamCustomOptions } from '@langchain/langgraph-sdk/ui'
import { useStream } from '@langchain/react'
import { aelinApi } from '@/shared/api/aelin'
import type { AttachmentUploadResponse } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import { useChatI18n } from '../chatI18n'
import { getSessionMessages, setSessionMessages } from '../chatHistoryStorage'
import type { ChatRuntimeStream, ChatStreamState } from '../executionStreamUtils'
import { useChatStore } from '../stores/chatStore'
import {
  buildHumanStreamMessage,
  buildSessionHistoryMessages,
  formatBytes,
  streamMessagesToChatMessages,
  trimQueryForApi,
  type PendingImage,
} from './chatStreamHelpers'
import { DeepAgentsUseStreamTransport } from './deepagentsUseStreamTransport'

export type { ChatRuntimeStream, ChatStreamState }

function sameImages(
  left?: Array<{ dataUrl: string; name: string }>,
  right?: Array<{ dataUrl: string; name: string }>,
): boolean {
  const a = left ?? []
  const b = right ?? []
  if (a.length !== b.length) return false
  for (let index = 0; index < a.length; index += 1) {
    if (a[index]?.dataUrl !== b[index]?.dataUrl) return false
    if ((a[index]?.name || '') !== (b[index]?.name || '')) return false
  }
  return true
}

function sameChatMessages(
  left: Array<{
    id: string
    role: 'user' | 'assistant'
    content: string
    expression?: string
    citations?: unknown[]
    actions?: unknown[]
    images?: Array<{ dataUrl: string; name: string }>
  }>,
  right: Array<{
    id: string
    role: 'user' | 'assistant'
    content: string
    expression?: string
    citations?: unknown[]
    actions?: unknown[]
    images?: Array<{ dataUrl: string; name: string }>
  }>,
): boolean {
  if (left.length !== right.length) return false
  for (let index = 0; index < left.length; index += 1) {
    const a = left[index]
    const b = right[index]
    if (!a || !b) return false
    if (a.id !== b.id) return false
    if (a.role !== b.role) return false
    if (a.content !== b.content) return false
    if ((a.expression || '') !== (b.expression || '')) return false
    if (!sameImages(a.images, b.images)) return false
    if ((a.citations?.length || 0) !== (b.citations?.length || 0)) return false
    if ((a.actions?.length || 0) !== (b.actions?.length || 0)) return false
  }
  return true
}

export function useChatStream() {
  const sessions = useChatStore((state) => state.sessions)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const isStreaming = useChatStore((state) => state.isStreaming)
  const statusText = useChatStore((state) => state.statusText)
  const createSession = useChatStore((state) => state.createSession)
  const setStreaming = useChatStore((state) => state.setStreaming)
  const setStatusText = useChatStore((state) => state.setStatusText)
  const setLastErrorCode = useChatStore((state) => state.setLastErrorCode)
  const { t } = useChatI18n()
  const session = sessions.find((item) => item.id === activeSessionId)
  const sessionMessages = useMemo(
    () => getSessionMessages(activeSessionId),
    [activeSessionId, sessions],
  )
  const thinkingLabel = t('status.thinking')

  const transport = useMemo(() => new DeepAgentsUseStreamTransport({
    apiUrl: `${import.meta.env.VITE_API_BASE || ''}/api/v1/deepagents/chat/stream`,
    getToken: () => localStorage.getItem('token'),
    getWorkspace: (threadId) => {
      const state = useChatStore.getState()
      const target = state.sessions.find((item) => item.id === threadId)
      return target?.workspace || 'default'
    },
    getSource: () => 'chat_ui',
  }), [])

  const streamOptions: AnyStreamCustomOptions<ChatStreamState> = {
    transport,
    threadId: activeSessionId,
    filterSubagentMessages: true,
    messagesKey: 'messages',
    initialValues: {
      messages: buildSessionHistoryMessages(sessionMessages) as Array<Record<string, unknown>>,
    },
    onError: (error) => {
      setStatusText(String((error as Error)?.message || 'Stream error'))
    },
  }

  const stream = useStream<ChatStreamState>(streamOptions)

  const displayMessages = useMemo(() => {
    if (!session) return []
    if (stream.messages.length === 0) return sessionMessages
    const nextMessages = streamMessagesToChatMessages(stream.messages as any, sessionMessages)
    return nextMessages.length > 0 ? nextMessages : sessionMessages
  }, [session, sessionMessages, stream.messages])

  useEffect(() => {
    if (isStreaming !== stream.isLoading) {
      setStreaming(stream.isLoading)
    }
    if (!stream.isLoading && statusText === thinkingLabel) {
      setStatusText('')
    }
  }, [isStreaming, setStreaming, setStatusText, statusText, stream.isLoading, thinkingLabel])

  useEffect(() => {
    if (!activeSessionId) return
    if (stream.isLoading) return
    if (stream.messages.length === 0) return

    if (displayMessages.length === 0) return
    if (sameChatMessages(displayMessages, sessionMessages)) return
    setSessionMessages(activeSessionId, displayMessages)
  }, [activeSessionId, displayMessages, sessionMessages, stream.isLoading, stream.messages.length])

  const send = useCallback(
    async (text: string, images?: PendingImage[], attachmentIds?: number[]) => {
      let sessionId = activeSessionId
      if (!sessionId) {
        sessionId = createSession()
      }
      const currentState = useChatStore.getState()
      const currentSession = currentState.sessions.find((item) => item.id === sessionId)
      const currentSessionMessages = getSessionMessages(sessionId)
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

      if (currentSessionMessages.length === 0) {
        const seed = visibleText || '新对话'
        currentState.renameSession(sessionId, seed.length > 20 ? `${seed.slice(0, 20)}…` : seed)
      }

      const humanMessage = buildHumanStreamMessage(prompt, images)
      currentState.setStreaming(true)
      currentState.setStatusText(t('status.thinking'))
      currentState.setLastErrorCode(null)

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
                ...(((prev?.messages as Array<Record<string, unknown>> | undefined) ?? buildSessionHistoryMessages(currentSessionMessages)) as Array<Record<string, unknown>>),
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
    [activeSessionId, createSession, stream, t],
  )

  const stop = useCallback(() => {
    void stream.stop()
    setStreaming(false)
    setStatusText(t('status.cancelled'))
    setLastErrorCode(null)
  }, [setLastErrorCode, setStatusText, setStreaming, stream, t])

  const captureAndSend = useCallback(
    async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
      if (isStreaming) return
      setStatusText(
        mode === 'region' ? t('status.capture.region') : t('status.capture.fullscreen'),
      )
      try {
        const capture = await aelinApi.deviceScreenCapture({ mode })
        const prompt = String(textHint || '').trim()
        await send(prompt, [{ dataUrl: capture.data_url, name: capture.name || `screen-${Date.now()}.jpg` }])
      } catch (error) {
        setStatusText('')
        throw error
      }
    },
    [isStreaming, send, setStatusText, t],
  )

  const uploadAttachments = useCallback(
    async (files: File[]): Promise<AttachmentUploadResponse[]> => {
      if (isStreaming) return []
      const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
      if (picked.length === 0) return []

      let sessionId = activeSessionId
      if (!sessionId) sessionId = createSession() || useChatStore.getState().activeSessionId
      const resolvedSessionId = String(sessionId || '')
      const workspace = useChatStore.getState().sessions.find((item) => item.id === sessionId)?.workspace || 'default'

      setStatusText(t('status.attach.processing'))
      try {
        const settled = await Promise.allSettled(
          picked.map((file) => aelinApi.uploadAttachment(file, { workspace, session_id: resolvedSessionId })),
        )
        const uploaded: AttachmentUploadResponse[] = []
        const failedNames: string[] = []
        settled.forEach((result, index) => {
          if (result.status === 'fulfilled') {
            uploaded.push(result.value)
            return
          }
          failedNames.push(picked[index]?.name || `attachment-${index + 1}`)
        })
        setStatusText('')
        if (uploaded.length === 0 && failedNames.length > 0) {
          throw new Error(t('composer.attach.partialFail', { names: failedNames.join(', ') }))
        }
        return uploaded
      } catch (error) {
        setStatusText('')
        throw error
      }
    },
    [activeSessionId, createSession, isStreaming, setStatusText, t],
  )

  const sendWithAttachments = useCallback(
    async (attachments: AttachmentUploadResponse[], textHint = '') => {
      if (isStreaming) return
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
    [isStreaming, send],
  )

  return {
    send,
    messages: displayMessages,
    captureAndSend,
    uploadAttachments,
    sendWithAttachments,
    stop,
    stream,
  }
}
