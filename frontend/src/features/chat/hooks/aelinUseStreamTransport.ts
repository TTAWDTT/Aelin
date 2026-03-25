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

type RawAelinPayload = {
  type?: string
  run_id?: string
  seq?: number
  ns?: string[]
  data?: Record<string, unknown>
}

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
  onAelinEvent?: (event: string, payload: RawAelinPayload) => void
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
      type: 'error',
      data: { message: text },
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

function nsEventName(base: string, ns: string[] | undefined): string {
  return ns && ns.length ? `${base}|${ns.join('|')}` : base
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
      let metadataEmitted = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value, { stream: true })
        const parsed = parseSseChunks(text, buffer)
        buffer = parsed.rest

        for (const item of parsed.events) {
          const parsedPayload = toPayload(item.data)
          if (!parsedPayload) continue
          self.options.onAelinEvent?.(item.event, parsedPayload)

          if (!metadataEmitted && parsedPayload.run_id) {
            metadataEmitted = true
            yield {
              event: 'metadata',
              data: {
                run_id: parsedPayload.run_id,
                thread_id: threadId,
              },
            }
          }

          const ns = Array.isArray(parsedPayload.ns) ? parsedPayload.ns.map((part) => String(part)) : undefined
          const data = parsedPayload.data ?? {}

          if (item.event === 'topology') {
            yield {
              event: 'custom',
              data: {
                kind: 'topology',
                topology: data,
              },
            }
            continue
          }

          if (item.event === 'values') {
            yield {
              event: 'custom',
              data: {
                kind: 'values',
                values: data,
              },
            }
            continue
          }

          if (item.event === 'final') {
            yield {
              event: 'custom',
              data: {
                kind: 'final',
                final: data,
              },
            }
            continue
          }

          if (item.event === 'updates') {
            yield {
              event: nsEventName('updates', ns),
              data,
            }
            continue
          }

          if (item.event === 'tasks') {
            yield {
              event: nsEventName('tasks', ns),
              data,
            }
            continue
          }

          if (item.event === 'messages') {
            const record = data as Record<string, unknown>
            const metadata =
              record.metadata && typeof record.metadata === 'object' && !Array.isArray(record.metadata)
                ? { ...(record.metadata as Record<string, unknown>) }
                : {}
            if (ns?.length) {
              const checkpointNs = ns.join('|')
              metadata.langgraph_checkpoint_ns ??= checkpointNs
              metadata.checkpoint_ns ??= checkpointNs
            }

            const message = normalizeStreamMessage(record.message, `${parsedPayload.run_id || threadId}:${parsedPayload.seq || Date.now()}`)
            if (!message) continue

            yield {
              event: nsEventName('messages', ns),
              data: [message, metadata],
            }
            continue
          }

          if (item.event === 'error') {
            const message = String((data as Record<string, unknown>).message || 'stream error')
            yield {
              event: 'error',
              data: {
                error: message,
                message,
              },
            }
            continue
          }

          if (item.event === 'done' || item.event === 'ping' || item.event === 'start') {
            continue
          }
        }
      }
    })()
  }
}
