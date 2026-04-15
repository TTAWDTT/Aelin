import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { type BaseMessage } from '@langchain/core/messages'
import { Client, type AssistantGraph } from '@langchain/langgraph-sdk'
import { useStream } from '@langchain/react'
import { aelinApi } from '@/shared/api/aelin'
import type { AttachmentUploadResponse, ChatAction, ChatCitation } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import { useChatI18n } from '../chatI18n'
import { getSessionMessages, setSessionMessages } from '../chatHistoryStorage'
import type { ChatMessage } from '../chatTypes'
import type { ChatRuntimeStream, ChatStreamState } from '../executionStreamUtils'
import { selectSessionRuntime, useChatStore } from '../stores/chatStore'
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

function getRuntimeMessageId(
  message: BaseMessage,
  fallback: string,
  getMessagesMetadata?: (
    message: BaseMessage,
    index?: number,
  ) => {
    messageId?: string
    branch?: string
    streamMetadata?: Record<string, unknown>
  } | undefined,
  index?: number,
): string {
  const direct = getMessageId(message, '')
  if (direct) return direct
  if (typeof getMessagesMetadata === 'function') {
    try {
      const metadata = getMessagesMetadata(message, index)
      const metadataId = String(metadata?.messageId || '').trim()
      if (metadataId) return metadataId
    } catch {
      // Ignore metadata read errors and fall back to a synthetic id.
    }
  }
  return fallback
}

function getRuntimeToolCalls(
  message: BaseMessage,
  getToolCalls?: ((message: BaseMessage) => unknown[]) | undefined,
): unknown[] {
  if (typeof getToolCalls !== 'function') return []
  try {
    const toolCalls = getToolCalls(message)
    return Array.isArray(toolCalls) ? toolCalls : []
  } catch {
    return []
  }
}

function projectRuntimeMessages(
  runtimeMessages: BaseMessage[],
  previousMessages: ChatMessage[],
  getToolCalls?: ((message: BaseMessage) => unknown[]) | undefined,
  getMessagesMetadata?: (
    message: BaseMessage,
    index?: number,
  ) => {
    messageId?: string
    branch?: string
    streamMetadata?: Record<string, unknown>
  } | undefined,
): ChatMessage[] {
  const previousById = new Map(previousMessages.map((message) => [message.id, message]))
  const projected: ChatMessage[] = []
  const seen = new Set<string>()

  runtimeMessages.forEach((message, index) => {
    const role = normalizeMessageRole(message)
    if (role !== 'user' && role !== 'assistant') return

    const id = getRuntimeMessageId(
      message,
      `message:${index}`,
      getMessagesMetadata,
      index,
    )
    const previous = previousById.get(id)
    const content = extractMessageText((message as any)?.content)
    const rawToolCalls = Array.isArray((message as any)?.tool_calls) ? (message as any).tool_calls : []
    const toolCalls = rawToolCalls.length > 0 ? rawToolCalls : getRuntimeToolCalls(message, getToolCalls)
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

function stableSerialize(value: unknown): string {
  if (value == null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return `[${value.map((item) => stableSerialize(item)).join(',')}]`
  const record = asRecord(value)
  const keys = Object.keys(record).sort()
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableSerialize(record[key])}`).join(',')}}`
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

function buildCitationRevision(citation: ChatCitation): string {
  return [
    String(citation.message_id ?? ''),
    String(citation.source ?? ''),
    String(citation.source_label ?? ''),
    String(citation.sender ?? ''),
    String(citation.sender_avatar_url ?? ''),
    String(citation.title ?? ''),
    String(citation.received_at ?? ''),
    String(citation.score ?? ''),
  ].join('|')
}

function buildActionRevision(action: ChatAction): string {
  return [
    String(action.kind ?? ''),
    String(action.title ?? ''),
    String(action.detail ?? ''),
    stableSerialize(action.payload ?? {}),
  ].join('|')
}

function buildMessagePersistenceRevision(message: ChatMessage): string {
  const citationsHash = hashStringList(
    Array.from(message.citations || []).map((item) => buildCitationRevision(item)),
  )
  const actionsHash = hashStringList(
    Array.from(message.actions || []).map((item) => buildActionRevision(item)),
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

function resolveErrorCode(error: unknown): string | null {
  const code = String((error as any)?.code || (error as any)?.status || '').trim()
  return code || null
}

export function useChatStream() {
  const sessions = useChatStore((state) => state.sessions)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const activeSessionRuntime = useChatStore((state) => selectSessionRuntime(state, state.activeSessionId))
  const createSession = useChatStore((state) => state.createSession)
  const statusText = activeSessionRuntime.statusText
  const { t } = useChatI18n()
  const session = sessions.find((item) => item.id === activeSessionId)
  const sessionMessages = useMemo(() => getSessionMessages(activeSessionId), [activeSessionId])
  const thinkingLabel = t('status.thinking')
  const [assistantId, setAssistantId] = useState<string>('')
  const [assistantGraph, setAssistantGraph] = useState<AssistantGraph | null>(null)
  const [streamThreadId, setStreamThreadId] = useState<string | null>(null)
  const activeSessionIdRef = useRef(activeSessionId)
  const assistantIdRef = useRef(assistantId)
  const assistantReadyWaitersRef = useRef<Array<{ id: string; resolve: () => void }>>([])
  const persistedRevisionsRef = useRef<string[]>([])
  const streamThreadIdRef = useRef<string | null>(null)

  const setSessionStatusText = useCallback((sessionId: string | null | undefined, value: string) => {
    const id = String(sessionId || '').trim()
    if (!id) return
    useChatStore.getState().setSessionStatusText(id, value)
  }, [])

  const setSessionLastErrorCode = useCallback((sessionId: string | null | undefined, code: string | null) => {
    const id = String(sessionId || '').trim()
    if (!id) return
    useChatStore.getState().setSessionLastErrorCode(id, code)
  }, [])

  const setSessionPhase = useCallback((sessionId: string | null | undefined, phase: 'idle' | 'streaming' | 'background') => {
    const id = String(sessionId || '').trim()
    if (!id) return
    useChatStore.getState().setSessionPhase(id, phase)
  }, [])

  const setCurrentStreamStatusText = useCallback((value: string) => {
    const sessionId = streamThreadIdRef.current || activeSessionIdRef.current
    if (!sessionId) return
    setSessionStatusText(sessionId, value)
  }, [setSessionStatusText])

  const setCurrentStreamPhase = useCallback((phase: 'idle' | 'streaming' | 'background') => {
    const sessionId = streamThreadIdRef.current || activeSessionIdRef.current
    if (!sessionId) return
    setSessionPhase(sessionId, phase)
  }, [setSessionPhase])

  const setCurrentStreamLastErrorCode = useCallback((code: string | null) => {
    const sessionId = streamThreadIdRef.current || activeSessionIdRef.current
    if (!sessionId) return
    setSessionLastErrorCode(sessionId, code)
  }, [setSessionLastErrorCode])

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
    reconnectOnMount: true,
    filterSubagentMessages: true,
    messagesKey: 'messages',
    initialValues: {
      messages: buildSessionHistoryMessages(sessionMessages) as Array<Record<string, unknown>>,
    },
    onError: (error: unknown) => {
      setCurrentStreamStatusText(String((error as Error)?.message || 'Stream error'))
      setCurrentStreamLastErrorCode(resolveErrorCode(error))
      setCurrentStreamPhase('idle')
    },
    onFinish: () => {
      const sessionId = streamThreadIdRef.current || activeSessionIdRef.current
      if (!sessionId) return
      const currentRuntime = selectSessionRuntime(useChatStore.getState(), sessionId)
      if (currentRuntime.statusText === thinkingLabel) {
        setSessionStatusText(sessionId, '')
      }
      setSessionLastErrorCode(sessionId, null)
      setSessionPhase(sessionId, 'idle')
    },
    onStop: () => {
      const sessionId = streamThreadIdRef.current || activeSessionIdRef.current
      if (!sessionId) return
      setSessionStatusText(sessionId, t('status.cancelled'))
      setSessionLastErrorCode(sessionId, null)
      setSessionPhase(sessionId, 'idle')
    },
  } as any)
  const streamRef = useRef(stream)

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId
  }, [activeSessionId])

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
    void findAssistantId(client)
      .then((resolved) => {
        if (!cancelled) setAssistantId(resolved)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setCurrentStreamStatusText(String((error as Error)?.message || 'Assistant lookup failed'))
          setCurrentStreamLastErrorCode(resolveErrorCode(error))
        }
      })
    return () => {
      cancelled = true
    }
  }, [assistantId, client, setCurrentStreamLastErrorCode, setCurrentStreamStatusText])

  useEffect(() => {
    if (!assistantId) {
      setAssistantGraph(null)
      return
    }
    let cancelled = false
    void fetchAssistantGraph(client, assistantId)
      .then((graph) => {
        if (!cancelled) setAssistantGraph(graph)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setAssistantGraph(null)
          setCurrentStreamStatusText(String((error as Error)?.message || 'Assistant graph lookup failed'))
          setCurrentStreamLastErrorCode(resolveErrorCode(error))
        }
      })
    return () => {
      cancelled = true
    }
  }, [assistantId, client, setCurrentStreamLastErrorCode, setCurrentStreamStatusText])

  const waitForAssistantId = useCallback((expectedId: string) => {
    if (assistantIdRef.current === expectedId) return Promise.resolve()
    return new Promise<void>((resolve) => {
      assistantReadyWaitersRef.current.push({ id: expectedId, resolve })
    })
  }, [])

  const ensureThreadReady = useCallback(async (threadId: string) => {
    const nextId = String(threadId || '').trim()
    if (!nextId) return
    await ensureThreadExists(client, nextId)
    if (streamThreadIdRef.current !== nextId) {
      const previousId = streamThreadIdRef.current
      if (previousId && previousId !== nextId) {
        const storeState = useChatStore.getState()
        const previousSessionStillExists = storeState.sessions.some((item) => item.id === previousId)
        if (previousSessionStillExists) {
          const previousRuntime = selectSessionRuntime(storeState, previousId)
          if (previousRuntime.phase === 'streaming') {
            storeState.setSessionPhase(previousId, 'background')
          }
        }
      }
      streamThreadIdRef.current = nextId
      setStreamThreadId(nextId)
      streamRef.current.switchThread(nextId)
      const reconnectableStream = streamRef.current as ChatRuntimeStream & { tryReconnect?: () => boolean }
      const didReconnect = typeof reconnectableStream.tryReconnect === 'function'
        ? Boolean(reconnectableStream.tryReconnect())
        : false
      const storeState = useChatStore.getState()
      const nextRuntime = selectSessionRuntime(storeState, nextId)
      if (didReconnect) {
        storeState.setSessionPhase(nextId, 'streaming')
        if (!nextRuntime.statusText.trim()) {
          storeState.setSessionStatusText(nextId, thinkingLabel)
        }
      } else if (nextRuntime.phase === 'background') {
        storeState.setSessionPhase(nextId, 'idle')
        if (nextRuntime.statusText === thinkingLabel) {
          storeState.setSessionStatusText(nextId, '')
        }
      }
    }
  }, [client, thinkingLabel])

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
    void ensureThreadExists(client, nextId)
      .then(() => {
        if (cancelled) return
        void ensureThreadReady(nextId)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setCurrentStreamStatusText(String((error as Error)?.message || 'Thread bootstrap failed'))
          setCurrentStreamLastErrorCode(resolveErrorCode(error))
        }
      })
    return () => {
      cancelled = true
    }
  }, [activeSessionId, client, ensureThreadReady, setCurrentStreamLastErrorCode, setCurrentStreamStatusText])

  const messages = useMemo(() => {
    const runtimeMessages = Array.isArray(stream.messages) ? stream.messages : []
    const runtimeToolCallsReader = (stream as ChatRuntimeStream).getToolCalls
    const runtimeMetadataReader = (stream as ChatRuntimeStream).getMessagesMetadata
    const projected = projectRuntimeMessages(
      runtimeMessages as BaseMessage[],
      sessionMessages,
      runtimeToolCallsReader,
      runtimeMetadataReader,
    )
    return projected.length > 0 ? projected : sessionMessages
  }, [sessionMessages, stream.messages, stream])

  useEffect(() => {
    if (!activeSessionId || stream.isLoading || messages.length === 0) return
    const revisions = messages.map((message) => buildMessagePersistenceRevision(message))
    if (revisionsMatch(persistedRevisionsRef.current, revisions)) return
    setSessionMessages(activeSessionId, messages)
    persistedRevisionsRef.current = revisions
  }, [activeSessionId, messages, stream.isLoading])

  useEffect(() => {
    if (stream.isLoading) {
      if (activeSessionId) {
        setSessionPhase(activeSessionId, 'streaming')
      }
      return
    }
    if (!activeSessionId) return
    const currentRuntime = selectSessionRuntime(useChatStore.getState(), activeSessionId)
    if (currentRuntime.phase === 'streaming') {
      setSessionPhase(activeSessionId, 'idle')
    }
    if (currentRuntime.statusText === thinkingLabel) {
      setSessionStatusText(activeSessionId, '')
    }
  }, [activeSessionId, setSessionPhase, setSessionStatusText, stream.isLoading, thinkingLabel])

  const send = useCallback(
    async (text: string, images?: PendingImage[], attachmentIds?: number[]) => {
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

      await ensureThreadReady(sessionId)

      const resolvedAssistantId = assistantIdRef.current || await findAssistantId(client)
      if (assistantIdRef.current !== resolvedAssistantId) {
        setAssistantId(resolvedAssistantId)
        await waitForAssistantId(resolvedAssistantId)
      }

      const humanMessage = buildHumanStreamMessage(prompt, images)
      const inputMessages = [humanMessage] as Array<Record<string, unknown>>
      currentState.setSessionStatusText(sessionId, t('status.thinking'))
      currentState.setSessionLastErrorCode(sessionId, null)
      currentState.setSessionPhase(sessionId, 'streaming')

      try {
        await streamRef.current.submit(
          { messages: inputMessages as any },
          {
            context: {
              workspace: currentSession?.workspace || 'default',
              source: 'chat_ui',
              attachment_ids: normalizedAttachmentIds,
            } as any,
            streamSubgraphs: true,
            onDisconnect: 'continue',
            streamResumable: true,
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
      } catch (error) {
        currentState.setSessionStatusText(sessionId, String((error as Error)?.message || 'Stream error'))
        currentState.setSessionLastErrorCode(sessionId, resolveErrorCode(error))
        currentState.setSessionPhase(sessionId, 'idle')
      }
    },
    [activeSessionId, client, createSession, ensureThreadReady, t, waitForAssistantId],
  )

  const stop = useCallback(() => {
    void stream.stop()
    const sessionId = activeSessionIdRef.current
    if (sessionId) {
      setSessionStatusText(sessionId, t('status.cancelled'))
      setSessionLastErrorCode(sessionId, null)
      setSessionPhase(sessionId, 'idle')
    }
  }, [setSessionLastErrorCode, setSessionPhase, setSessionStatusText, stream, t])

  const captureAndSend = useCallback(
    async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
      if (stream.isLoading) return
      const sessionId = activeSessionIdRef.current
      if (sessionId) {
        setSessionStatusText(
          sessionId,
          mode === 'region' ? t('status.capture.region') : t('status.capture.fullscreen'),
        )
      }
      try {
        const capture = await aelinApi.deviceScreenCapture({ mode })
        const prompt = String(textHint || '').trim()
        await send(prompt, [{ dataUrl: capture.data_url, name: capture.name || `screen-${Date.now()}.jpg` }])
      } catch (error) {
        if (sessionId) setSessionStatusText(sessionId, '')
        throw error
      }
    },
    [send, setSessionStatusText, stream.isLoading, t],
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

      if (resolvedSessionId) {
        setSessionStatusText(resolvedSessionId, t('status.attach.processing'))
      }
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
        if (resolvedSessionId) setSessionStatusText(resolvedSessionId, '')
        if (uploaded.length === 0 && failedNames.length > 0) {
          throw new Error(t('composer.attach.partialFail', { names: failedNames.join(', ') }))
        }
        return uploaded
      } catch (error) {
        if (resolvedSessionId) setSessionStatusText(resolvedSessionId, '')
        throw error
      }
    },
    [activeSessionId, createSession, setSessionStatusText, stream.isLoading, t],
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
