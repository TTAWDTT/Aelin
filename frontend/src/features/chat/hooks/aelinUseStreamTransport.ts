import type { ChatRequest } from '@/shared/api/types'
import {
  buildChatRequestFromStream,
  type PendingImage,
} from './chatStreamHelpers'

type StreamMessageLike = {
  id?: string
  type?: string
  content?: unknown
  tool_calls?: unknown[]
  tool_call_id?: string
}

type RawSseEvent = {
  event: string
  data: string
}

type RawAelinPayload = unknown

type TransportStreamEvent = {
  id?: string
  event: string
  data: unknown
}

interface AelinUseStreamTransportOptions {
  apiUrl: string
  getToken: () => string | null
  getHistoryMessages: (threadId: string) => StreamMessageLike[]
  getWorkspace: (threadId: string) => string
  getSource?: () => string
}

function parseSseChunks(chunkText: string, pending = ''): { events: RawSseEvent[]; rest: string } {
  const input = `${pending}${chunkText}`
  const lines = input.split(/\r?\n/)
  const events: RawSseEvent[] = []
  let eventName = 'message'
  let dataLines: string[] = []

  const flush = () => {
    if (!dataLines.length) return
    events.push({ event: eventName || 'message', data: dataLines.join('\n') })
    eventName = 'message'
    dataLines = []
  }

  let rest = ''
  if (!input.endsWith('\n') && !input.endsWith('\r')) {
    rest = lines.pop() ?? ''
  }

  for (const line of lines) {
    if (!line) {
      flush()
      continue
    }
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  return { events, rest }
}

function toPayload(raw: string): RawAelinPayload | null {
  const text = String(raw || '').trim()
  if (!text || text === '[DONE]') return null
  try {
    return JSON.parse(text) as RawAelinPayload
  } catch {
    return {
      message: text,
    }
  }
}

function normalizeMessageType(value: unknown): string {
  const type = String(value || '').trim().toLowerCase()
  if (type === 'assistant') return 'ai'
  if (type === 'user') return 'human'
  return type
}

function normalizeStreamMessage(message: unknown, fallbackId: string): StreamMessageLike | null {
  const record =
    message && typeof message === 'object' && !Array.isArray(message)
      ? message as Record<string, unknown>
      : {}
  const type = normalizeMessageType(record.type)
  const content = record.content
  if (!type) return null

  return {
    ...record,
    id: typeof record.id === 'string' && record.id.trim() ? record.id.trim() : fallbackId,
    type,
    content,
  }
}

export class AelinUseStreamTransport {
  private readonly options: AelinUseStreamTransportOptions

  constructor(options: AelinUseStreamTransportOptions) {
    this.options = options
  }

  async stream(payload: {
    input: Record<string, unknown> | null | undefined
    context?: Record<string, unknown>
    signal: AbortSignal
    config?: Record<string, unknown>
  }): Promise<AsyncGenerator<TransportStreamEvent>> {
    const token = this.options.getToken()
    const threadId = String(
      (payload.config as Record<string, any> | undefined)?.configurable?.thread_id
      || crypto.randomUUID(),
    )
    const inputRecord = (payload.input ?? {}) as Record<string, unknown>
    const inputMessages = Array.isArray(inputRecord.messages)
      ? inputRecord.messages as StreamMessageLike[]
      : []

    const contextRecord =
      payload.context && typeof payload.context === 'object' && !Array.isArray(payload.context)
        ? payload.context as Record<string, unknown>
        : {}

    const attachmentIds = Array.isArray(contextRecord.attachment_ids)
      ? contextRecord.attachment_ids.filter((id): id is number => Number.isFinite(Number(id))).map(Number)
      : []

    const body: ChatRequest = buildChatRequestFromStream({
      historyMessages: this.options.getHistoryMessages(threadId),
      inputMessages,
      workspace: String(contextRecord.workspace || this.options.getWorkspace(threadId) || 'default'),
      attachmentIds,
      source: String(contextRecord.source || this.options.getSource?.() || 'chat_ui'),
    })

    const response = await fetch(this.options.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal: payload.signal,
    })
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new Error(detail || `Failed to stream: HTTP ${response.status}`)
    }
    if (!response.body) {
      throw new Error('Expected response body from stream endpoint')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    const self = this

    return (async function* () {
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value, { stream: true })
        const parsed = parseSseChunks(text, buffer)
        buffer = parsed.rest

        for (const item of parsed.events) {
          const parsedPayload = toPayload(item.data)
          if (!parsedPayload) continue

          if (item.event === 'metadata') {
            const record =
              parsedPayload && typeof parsedPayload === 'object' && !Array.isArray(parsedPayload)
                ? parsedPayload as Record<string, unknown>
                : {}
            yield {
              event: 'metadata',
              data: {
                ...record,
                thread_id: threadId,
              },
            }
            continue
          }

          if (item.event === 'custom') {
            yield {
              event: 'custom',
              data: parsedPayload,
            }
            continue
          }

          if (item.event === 'done' || item.event === 'ping') {
            continue
          }

          if (item.event === 'error') {
            const message = String((parsedPayload as Record<string, unknown>).message || 'stream error')
            yield {
              event: 'error',
              data: { error: message, message },
            }
            continue
          }

          if (item.event === 'messages' || item.event.startsWith('messages|')) {
            const tuple = Array.isArray(parsedPayload) ? parsedPayload : []
            const rawMessage = tuple[0]
            const metadata =
              tuple[1] && typeof tuple[1] === 'object' && !Array.isArray(tuple[1])
                ? { ...(tuple[1] as Record<string, unknown>) }
                : {}
            const message = normalizeStreamMessage(rawMessage, `${threadId}:${Date.now()}`)
            if (!message) continue
            yield {
              event: item.event,
              data: [message, metadata],
            }
            continue
          }

          if (
            item.event === 'updates' || item.event.startsWith('updates|')
            || item.event === 'tasks' || item.event.startsWith('tasks|')
            || item.event === 'values' || item.event.startsWith('values|')
          ) {
            yield {
              event: item.event,
              data: parsedPayload,
            }
          }
        }
      }
    })()
  }
}
