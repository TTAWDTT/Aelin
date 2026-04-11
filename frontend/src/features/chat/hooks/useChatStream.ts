import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { type BaseMessage } from '@langchain/core/messages'
import { Client, type AssistantGraph } from '@langchain/langgraph-sdk'
import { useStream } from '@langchain/react'
import { aelinApi } from '@/shared/api/aelin'
import type { AttachmentUploadResponse } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import { useChatI18n } from '../chatI18n'
import { getSessionMessages, setSessionMessages } from '../chatHistoryStorage'
import type { ChatMessage } from '../chatTypes'
import type { ChatRuntimeStream, ChatStreamState } from '../executionStreamUtils'
import { useChatStore } from '../stores/chatStore'
import {
  buildHumanStreamMessage,
  buildSessionHistoryMessages,
  formatBytes,
  trimQueryForApi,
  type PendingImage,
} from './chatStreamHelpers'
import {
  ensureThreadExists,
  fetchAssistantGraph,
  findAssistantId,
} from './chatStreamRuntime'

export type { ChatRuntimeStream, ChatStreamState }

const DEFAULT_AGENT_SERVER_URL = 'http://127.0.0.1:8000'

function resolveAgentServerUrl(): string {
  const fromEnv = String(import.meta.env.VITE_API_BASE || '').trim()
  if (fromEnv) return fromEnv.replace(/\/$/, '')
  if (typeof window !== 'undefined' && /^https?:$/.test(window.location.protocol)) {
    const protocol = window.location.protocol
    const hostname = window.location.hostname || '127.0.0.1'
    const currentPort = String(window.location.port || '')
    if (currentPort === '8000' || currentPort === '18080') {
      return `${protocol}//${window.location.host}`.replace(/\/$/, '')
    }
    const inferredPort = currentPort === '1420' ? '18080' : '8000'
    return `${protocol}//${hostname}:${inferredPort}`
  }
  return DEFAULT_AGENT_SERVER_URL
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function normalizeMessageRole(message: BaseMessage): 'user' | 'assistant' | '' {
  const rawType = typeof (message as any)?.getType === 'function'
    ? (message as any).getType()
    : (message as any)?.type
  const type = String(rawType || '').trim().toLowerCase()
  if (type === 'human' || type === 'user') return 'user'
  if (type === 'ai' || type === 'assistant') return 'assistant'
  return ''
}

function extractMessageText(content: unknown): string {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''

  return content
    .map((item) => {
      const record = asRecord(item)
      return record.type === 'text' ? String(record.text || '') : ''
    })
    .filter(Boolean)
    .join('\n')
    .trim()
}

function extractMessageImages(content: unknown): Array<{ dataUrl: string; name: string }> {
  if (!Array.isArray(content)) return []

  return content
    .map((item) => {
      const record = asRecord(item)
      if (record.type !== 'image_url') return null
      const imageUrl = record.image_url
      if (typeof imageUrl === 'string' && imageUrl.startsWith('data:image/')) {
        return { dataUrl: imageUrl, name: '' }
      }
      const imageRecord = asRecord(imageUrl)
      const url = String(imageRecord.url || '').trim()
      if (!url.startsWith('data:image/')) return null
      return {
        dataUrl: url,
        name: String(imageRecord.name || ''),
      }
    })
    .filter((item): item is { dataUrl: string; name: string } => item != null)
}

function getMessageId(message: BaseMessage, fallback: string): string {
  const direct = String((message as any)?.id || '').trim()
  return direct || fallback
}

function nowMs(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

function reportChatTiming(stage: string, startedAt: number, detail?: Record<string, unknown>) {
  const durationMs = Math.max(0, Math.round(nowMs() - startedAt))
  if (typeof window !== 'undefined') {
    try {
      window.dispatchEvent(
        new CustomEvent('aelin:chat-perf', {
          detail: {
            stage,
            duration_ms: durationMs,
            ...(detail || {}),
          },
        }),
      )
    } catch {
      // Ignore runtime environments without CustomEvent.
    }
  }
  if (import.meta.env.DEV && typeof console !== 'undefined' && typeof console.debug === 'function') {
    console.debug('[aelin-chat-perf]', stage, {
      duration_ms: durationMs,
      ...(detail || {}),
    })
  }
}

function projectRuntimeMessages(
  runtimeMessages: BaseMessage[],
  previousMessages: ChatMessage[],
): ChatMessage[] {
  const previousById = new Map(previousMessages.map((message) => [message.id, message]))
  const projected: ChatMessage[] = []
  const seen = new Set<string>()

  runtimeMessages.forEach((message, index) => {
    const role = normalizeMessageRole(message)
    if (role !== 'user' && role !== 'assistant') return

    const id = getMessageId(message, `message:${index}`)
    const previous = previousById.get(id)
    const content = extractMessageText((message as any)?.content)
    const toolCalls = Array.isArray((message as any)?.tool_calls) ? (message as any).tool_calls : []
    if (role === 'assistant' && !content.trim() && toolCalls.length === 0) return

    const images = role === 'user'
      ? extractMessageImages((message as any)?.content)
      : (previous?.images ?? [])

    const nextMessage: ChatMessage = {
      id,
      role,
      content,
      images: images.length > 0 ? images : previous?.images,
      timestamp: previous?.timestamp ?? Date.now(),
      expression: previous?.expression,
      citations: previous?.citations,
      actions: previous?.actions,
    }

    if (seen.has(id)) {
      const existingIndex = projected.findIndex((item) => item.id === id)
      if (existingIndex >= 0) projected[existingIndex] = nextMessage
      return
    }

    seen.add(id)
    projected.push(nextMessage)
  })

  return projected
}

function hashString(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function hashStringList(values: string[]): number {
  let hash = 2166136261
  values.forEach((value) => {
    hash ^= hashString(value)
    hash = Math.imul(hash, 16777619)
  })
  return hash >>> 0
}

function buildMessagePersistenceRevision(message: ChatMessage): string {
  const citationsHash = hashStringList(
    Array.from(message.citations || []).map((item) => [
      String((item as any)?.id || ''),
      String((item as any)?.title || ''),
      String((item as any)?.url || ''),
    ].join('|')),
  )
  const actionsHash = hashStringList(
    Array.from(message.actions || []).map((item) => [
      String((item as any)?.type || ''),
      String((item as any)?.label || ''),
      String((item as any)?.payload || ''),
    ].join('|')),
  )
  const imagesHash = hashStringList(
    Array.from(message.images || []).map((item) => `${item.name || ''}|${item.dataUrl || ''}`),
  )
  return [
    message.id,
    message.role,
    String(hashString(String(message.content || ''))),
    String(hashString(String(message.expression || ''))),
    String(citationsHash),
    String(actionsHash),
    String(imagesHash),
  ].join(':')
}

function revisionsMatch(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return false
  }
  return true
}

export function useChatStream() {
  const sessions = useChatStore((state) => state.sessions)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const statusText = useChatStore((state) => state.statusText)
  const createSession = useChatStore((state) => state.createSession)
  const setStatusText = useChatStore((state) => state.setStatusText)
  const setLastErrorCode = useChatStore((state) => state.setLastErrorCode)
  const { t } = useChatI18n()
  const session = sessions.find((item) => item.id === activeSessionId)
  const sessionMessages = useMemo(() => getSessionMessages(activeSessionId), [activeSessionId])
  const thinkingLabel = t('status.thinking')
  const [assistantId, setAssistantId] = useState<string>('')
  const [assistantGraph, setAssistantGraph] = useState<AssistantGraph | null>(null)
  const [streamThreadId, setStreamThreadId] = useState<string | null>(null)
  const assistantIdRef = useRef(assistantId)
  const assistantReadyWaitersRef = useRef<Array<{ id: string; resolve: () => void }>>([])
  const persistedRevisionsRef = useRef<string[]>([])
  const streamThreadIdRef = useRef<string | null>(null)

  const client = useMemo(() => new Client({
    apiUrl: resolveAgentServerUrl(),
    apiKey: null,
    onRequest: async (_url, init) => {
      const headers = new Headers(init.headers ?? {})
      const token = localStorage.getItem('token')
      if (token) headers.set('Authorization', `Bearer ${token}`)
      return {
        ...init,
        headers,
      }
    },
  }), [])

  const stream = useStream<ChatStreamState>({
    assistantId: assistantId || '__aelin_agent_pending__',
    client,
    threadId: streamThreadId,
    filterSubagentMessages: true,
    messagesKey: 'messages',
    initialValues: {
      messages: buildSessionHistoryMessages(sessionMessages) as Array<Record<string, unknown>>,
    },
    onError: (error: unknown) => {
      setStatusText(String((error as Error)?.message || 'Stream error'))
    },
    onFinish: () => {
      if (useChatStore.getState().statusText === thinkingLabel) {
        setStatusText('')
      }
    },
    onStop: () => {
      setStatusText(t('status.cancelled'))
    },
  } as any)
  const streamRef = useRef(stream)

  useEffect(() => {
    streamRef.current = stream
  }, [stream])

  useEffect(() => {
    streamThreadIdRef.current = streamThreadId
  }, [streamThreadId])

  useEffect(() => {
    assistantIdRef.current = assistantId
    if (!assistantId) return
    const pending = assistantReadyWaitersRef.current
    assistantReadyWaitersRef.current = []
    pending.forEach((waiter) => {
      if (waiter.id === assistantId) waiter.resolve()
      else assistantReadyWaitersRef.current.push(waiter)
    })
  }, [assistantId])

  useEffect(() => {
    if (assistantId) return
    let cancelled = false
    const startedAt = nowMs()
    void findAssistantId(client)
      .then((resolved) => {
        if (!cancelled) {
          setAssistantId(resolved)
          reportChatTiming('assistant_lookup', startedAt, { assistant_id: resolved || '' })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          reportChatTiming('assistant_lookup_failed', startedAt)
          setStatusText(String((error as Error)?.message || 'Assistant lookup failed'))
        }
      })
    return () => {
      cancelled = true
    }
  }, [assistantId, client, setStatusText])

  useEffect(() => {
    if (!assistantId) {
      setAssistantGraph(null)
      return
    }
    let cancelled = false
    const startedAt = nowMs()
    void fetchAssistantGraph(client, assistantId)
      .then((graph) => {
        if (!cancelled) {
          setAssistantGraph(graph)
          reportChatTiming('assistant_graph_lookup', startedAt, { assistant_id: assistantId })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          reportChatTiming('assistant_graph_lookup_failed', startedAt, { assistant_id: assistantId })
          setAssistantGraph(null)
          setStatusText(String((error as Error)?.message || 'Assistant graph lookup failed'))
        }
      })
    return () => {
      cancelled = true
    }
  }, [assistantId, client, setStatusText])

  const waitForAssistantId = useCallback((expectedId: string) => {
    if (assistantIdRef.current === expectedId) return Promise.resolve()
    return new Promise<void>((resolve) => {
      assistantReadyWaitersRef.current.push({ id: expectedId, resolve })
    })
  }, [])

  const ensureThreadReady = useCallback(async (threadId: string) => {
    const nextId = String(threadId || '').trim()
    if (!nextId) return
    const startedAt = nowMs()
    await ensureThreadExists(client, nextId)
    if (streamThreadIdRef.current !== nextId) {
      streamThreadIdRef.current = nextId
      setStreamThreadId(nextId)
      streamRef.current.switchThread(nextId)
    }
    reportChatTiming('thread_ready', startedAt, { thread_id: nextId })
  }, [client])

  useEffect(() => {
    persistedRevisionsRef.current = []
    const nextId = String(activeSessionId || '').trim()
    if (!nextId) {
      if (streamThreadIdRef.current == null) return
      streamThreadIdRef.current = null
      setStreamThreadId(null)
      streamRef.current.switchThread(null)
      return
    }

    let cancelled = false
    const startedAt = nowMs()
    void ensureThreadExists(client, nextId)
      .then(() => {
        if (cancelled) return
        if (streamThreadIdRef.current === nextId) return
        streamThreadIdRef.current = nextId
        setStreamThreadId(nextId)
        streamRef.current.switchThread(nextId)
        reportChatTiming('thread_bootstrap', startedAt, { thread_id: nextId })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          reportChatTiming('thread_bootstrap_failed', startedAt, { thread_id: nextId })
          setStatusText(String((error as Error)?.message || 'Thread bootstrap failed'))
        }
      })
    return () => {
      cancelled = true
    }
  }, [activeSessionId, client, setStatusText])

  const messages = useMemo(() => {
    const runtimeMessages = Array.isArray(stream.messages) ? stream.messages : []
    const projected = projectRuntimeMessages(runtimeMessages as BaseMessage[], sessionMessages)
    return projected.length > 0 ? projected : sessionMessages
  }, [sessionMessages, stream.messages])

  useEffect(() => {
    if (!activeSessionId || stream.isLoading || messages.length === 0) return
    const revisions = messages.map((message) => buildMessagePersistenceRevision(message))
    if (revisionsMatch(persistedRevisionsRef.current, revisions)) return
    setSessionMessages(activeSessionId, messages)
    persistedRevisionsRef.current = revisions
  }, [activeSessionId, messages, stream.isLoading])

  useEffect(() => {
    if (stream.isLoading) return
    if (statusText === thinkingLabel) {
      setStatusText('')
    }
  }, [setStatusText, statusText, stream.isLoading, thinkingLabel])

  const send = useCallback(
    async (text: string, images?: PendingImage[], attachmentIds?: number[]) => {
      const sendStartedAt = nowMs()
      let sessionId = activeSessionId
      if (!sessionId) {
        sessionId = createSession()
      }
      const currentState = useChatStore.getState()
      const currentSession = currentState.sessions.find((item) => item.id === sessionId)
      const currentSessionMessages = getSessionMessages(sessionId)
      const normalizedAttachmentIds = Array.from(
        new Set((attachmentIds || []).filter((id) => Number.isFinite(id) && id > 0)),
      ).slice(0, 20)
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

      const threadReadyStartedAt = nowMs()
      await ensureThreadReady(sessionId)
      reportChatTiming('send_thread_prepare', threadReadyStartedAt, { thread_id: sessionId })

      const assistantReadyStartedAt = nowMs()
      const resolvedAssistantId = assistantIdRef.current || await findAssistantId(client)
      if (assistantIdRef.current !== resolvedAssistantId) {
        setAssistantId(resolvedAssistantId)
        await waitForAssistantId(resolvedAssistantId)
      }
      reportChatTiming('send_assistant_prepare', assistantReadyStartedAt, { assistant_id: resolvedAssistantId || '' })

      const humanMessage = buildHumanStreamMessage(prompt, images)
      const inputMessages = [humanMessage] as Array<Record<string, unknown>>
      currentState.setStatusText(t('status.thinking'))
      currentState.setLastErrorCode(null)

      try {
        const submitStartedAt = nowMs()
        await streamRef.current.submit(
          { messages: inputMessages as any },
          {
            context: {
              workspace: currentSession?.workspace || 'default',
              source: 'chat_ui',
              attachment_ids: normalizedAttachmentIds,
            } as any,
            streamSubgraphs: true,
            onDisconnect: 'cancel',
            optimisticValues: (prev) => ({
              ...(prev || {}),
              messages: [
                ...((((prev?.messages as Array<Record<string, unknown>> | undefined)
                  ?? buildSessionHistoryMessages(currentSessionMessages)) as Array<Record<string, unknown>>)),
                humanMessage as Record<string, unknown>,
              ],
            }),
          },
        )
        reportChatTiming('send_submit', submitStartedAt, {
          attachment_count: normalizedAttachmentIds.length,
          image_count: images?.length || 0,
          thread_id: sessionId,
        })
        reportChatTiming('send_total_prepare', sendStartedAt, {
          attachment_count: normalizedAttachmentIds.length,
          image_count: images?.length || 0,
          thread_id: sessionId,
        })
      } catch (error) {
        reportChatTiming('send_submit_failed', sendStartedAt, { thread_id: sessionId })
        currentState.setStatusText(String((error as Error)?.message || 'Stream error'))
      }
    },
    [activeSessionId, client, createSession, ensureThreadReady, t, waitForAssistantId],
  )

  const stop = useCallback(() => {
    void stream.stop()
    setStatusText(t('status.cancelled'))
    setLastErrorCode(null)
  }, [setLastErrorCode, setStatusText, stream, t])

  const captureAndSend = useCallback(
    async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
      if (stream.isLoading) return
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
    [send, setStatusText, stream.isLoading, t],
  )

  const uploadAttachments = useCallback(
    async (files: File[]): Promise<AttachmentUploadResponse[]> => {
      if (stream.isLoading) return []
      const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
      if (picked.length === 0) return []

      let sessionId = activeSessionId
      if (!sessionId) sessionId = createSession() || useChatStore.getState().activeSessionId
      const resolvedSessionId = String(sessionId || '')
      const workspace =
        useChatStore.getState().sessions.find((item) => item.id === sessionId)?.workspace || 'default'

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
    [activeSessionId, createSession, setStatusText, stream.isLoading, t],
  )

  const sendWithAttachments = useCallback(
    async (attachments: AttachmentUploadResponse[], textHint = '') => {
      if (stream.isLoading) return
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
    [send, stream.isLoading],
  )

  return {
    send,
    messages,
    captureAndSend,
    uploadAttachments,
    sendWithAttachments,
    stop,
    assistantGraph,
    stream,
  }
}
