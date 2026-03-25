import type {
  ChatRequest,
  ChatCitation,
  ChatAction,
  DeepAgentsStreamEnvelope,
  DeepAgentsStreamUpdate,
} from './types'
import { createStreamPart } from '@/features/chat/executionEventUtils'

interface StreamCallbacks {
  onUpdate?: (update: DeepAgentsStreamUpdate) => void
}

type ParsedSseEvent = {
  event: string
  data: string
}

function parseSseChunks(chunkText: string, pending = ''): { events: ParsedSseEvent[]; rest: string } {
  const input = `${pending}${chunkText}`
  const lines = input.split(/\r?\n/)
  const events: ParsedSseEvent[] = []
  let eventName = 'message'
  let dataLines: string[] = []

  const flush = () => {
    if (!dataLines.length) return
    events.push({
      event: eventName || 'message',
      data: dataLines.join('\n'),
    })
    eventName = 'message'
    dataLines = []
  }

  // If the stream chunk does not end with newline, keep the trailing partial line.
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

function toEventPayload(raw: string): any {
  const text = String(raw || '').trim()
  if (!text || text === '[DONE]') return null
  try {
    return JSON.parse(text)
  } catch {
    return { message: text }
  }
}

function toEnvelopePayload(payload: any, fallbackType: string): DeepAgentsStreamEnvelope {
  const base =
    payload && typeof payload === 'object' && !Array.isArray(payload)
      ? payload as Record<string, unknown>
      : {}
  return {
    type: String(base.type || base.event || fallbackType || 'message').trim().toLowerCase(),
    run_id: typeof base.run_id === 'string' ? base.run_id : undefined,
    seq: typeof base.seq === 'number' ? base.seq : undefined,
    ts: typeof base.ts === 'number' ? base.ts : undefined,
    ns: Array.isArray(base.ns) ? base.ns.map((item) => String(item)) : undefined,
    data: base.data,
  }
}

function buildStreamUpdate(sseEvent: string, payload: any): DeepAgentsStreamUpdate | null {
  if (!payload) return null
  const envelope = toEnvelopePayload(payload, sseEvent)
  const type = envelope.type
  const part = createStreamPart(type, payload)
  const update: DeepAgentsStreamUpdate = {
    type,
    envelope,
    part: part && type !== 'ping' ? part : undefined,
  }

  if (type === 'messages') {
    const metadata = (payload?.data?.metadata ?? {}) as Record<string, unknown>
    const nodeName = String(metadata?.langgraph_node ?? '').trim().toLowerCase()
    const text =
      typeof payload?.data?.content === 'string'
        ? payload.data.content
        : typeof payload?.content === 'string'
          ? payload.content
          : ''
    if (text && nodeName === 'model') {
      update.textDelta = text
    }
    return update
  }

  if (type === 'final') {
    const result = payload?.data?.result ?? payload?.result ?? payload?.data ?? {}
    if (Array.isArray(result.citations)) update.citations = result.citations as ChatCitation[]
    if (Array.isArray(result.actions)) update.actions = result.actions as ChatAction[]
    const answer =
      typeof result.answer === 'string' && result.answer
        ? result.answer
        : typeof payload?.data?.answer === 'string' && payload.data.answer
          ? payload.data.answer
          : ''
    if (answer) update.finalAnswer = answer
    return update
  }

  if (type === 'error') {
    const raw = payload?.data ?? payload
    update.error = {
      message:
        typeof raw?.message === 'string'
          ? raw.message
          : typeof raw === 'string'
            ? raw
            : 'stream error',
      code:
        typeof raw?.code === 'string'
          ? raw.code
          : typeof raw?.error === 'string'
            ? raw.error
            : undefined,
    }
    return update
  }

  if (type === 'done') {
    update.done = true
    return update
  }

  if (type === 'citations') {
    const citations = (payload.data ?? payload) as ChatCitation[]
    if (Array.isArray(citations)) update.citations = citations
    return update
  }

  if (type === 'actions') {
    const actions = (payload.data ?? payload) as ChatAction[]
    if (Array.isArray(actions)) update.actions = actions
    return update
  }

  return update
}

export function streamChat(body: ChatRequest, callbacks: StreamCallbacks, signal?: AbortSignal): () => void {
  const controller = new AbortController()
  const combined = signal ? AbortSignal.any([signal, controller.signal]) : controller.signal
  const token = localStorage.getItem('token')
  const BASE = import.meta.env.VITE_API_BASE || ''
  const debugEnabled = import.meta.env.DEV || import.meta.env.VITE_DEBUG_STREAM === 'true'
  const debugLog = (...args: unknown[]) => {
    if (!debugEnabled) return
    // eslint-disable-next-line no-console
    console.info('[deepagents-stream]', ...args)
  }

  debugLog('request_start', {
    url: `${BASE}/api/v1/deepagents/chat/stream`,
    source: body?.source || 'chat_ui',
    historyCount: Array.isArray(body?.history) ? body.history.length : 0,
    imageCount: Array.isArray(body?.images) ? body.images.length : 0,
  })

  fetch(`${BASE}/api/v1/deepagents/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
    signal: combined,
  }).then(async (res) => {
    debugLog('response_open', { ok: res.ok, status: res.status })
    if (!res.ok) {
      let detail = ''
      try {
        detail = await res.text()
      } catch {
        detail = ''
      }
      const trimmed = String(detail || '').trim()
      const suffix = trimmed ? `: ${trimmed.slice(0, 240)}` : ''
      debugLog('response_error', { status: res.status, detail: trimmed.slice(0, 240) })
      callbacks.onUpdate?.({
        type: 'error',
        envelope: { type: 'error' },
        error: { message: `HTTP ${res.status}${suffix}` },
      })
      return
    }
    if (!res.body) {
      callbacks.onUpdate?.({
        type: 'error',
        envelope: { type: 'error' },
        error: { message: 'stream body unavailable' },
      })
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    const dispatch = (sseEvent: string, payload: any) => {
      const update = buildStreamUpdate(sseEvent, payload)
      if (!update) return
      debugLog('event', { sseEvent, eventType: update.type })
      callbacks.onUpdate?.(update)
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value, { stream: true })
      const parsed = parseSseChunks(text, buffer)
      buffer = parsed.rest
      for (const evt of parsed.events) {
        const payload = toEventPayload(evt.data)
        try {
          dispatch(evt.event, payload)
        } catch (callbackError: any) {
          // Callback exceptions should not be misreported as transport failures.
          // eslint-disable-next-line no-console
          console.error('[deepagents-stream] callback_error', {
            message: String(callbackError?.message || ''),
            event: evt.event,
          })
        }
      }
    }
    debugLog('stream_done')
  }).catch((err) => {
    const aborted = combined.aborted || String(err?.name || '') === 'AbortError'
    if (!aborted) {
      // eslint-disable-next-line no-console
      console.error('[deepagents-stream] network_error', { message: String(err?.message || ''), stack: String(err?.stack || '') })
      callbacks.onUpdate?.({
        type: 'error',
        envelope: { type: 'error' },
        error: { message: err.message },
      })
    }
  })

  return () => controller.abort()
}
