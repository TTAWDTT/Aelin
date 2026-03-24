import type { AelinChatRequest, AelinCitation, AelinAction, AelinToolStep } from './types'

interface StreamCallbacks {
  onIntent?: (data: { intent_type: string; time_sensitivity?: string }) => void
  onPlan?: (data: { steps: string[] }) => void
  onToolStep?: (step: AelinToolStep) => void
  onCitations?: (citations: AelinCitation[]) => void
  onActions?: (actions: AelinAction[]) => void
  onReplyChunk?: (text: string) => void
  onDone?: (data: { expression: string; memory_summary: string }) => void
  onError?: (error: { message: string; code?: string }) => void
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

export function streamChat(body: AelinChatRequest, callbacks: StreamCallbacks, signal?: AbortSignal): () => void {
  const controller = new AbortController()
  const combined = signal ? AbortSignal.any([signal, controller.signal]) : controller.signal
  const token = localStorage.getItem('token')
  const BASE = import.meta.env.VITE_API_BASE || ''
  const debugEnabled = import.meta.env.DEV || import.meta.env.VITE_DEBUG_STREAM === 'true'
  const debugLog = (...args: unknown[]) => {
    if (!debugEnabled) return
    // eslint-disable-next-line no-console
    console.info('[aelin-stream]', ...args)
  }

  debugLog('request_start', {
    url: `${BASE}/api/v1/deepagents/chat/stream`,
    source: body?.source || 'chat_ui',
    historyCount: Array.isArray(body?.history) ? body.history.length : 0,
    imageCount: Array.isArray(body?.images) ? body.images.length : 0,
  })
  let hasTraceSteps = false

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
      callbacks.onError?.({ message: `HTTP ${res.status}${suffix}` })
      return
    }
    if (!res.body) {
      callbacks.onError?.({ message: 'stream body unavailable' })
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalized = false

    const emitDone = (payload?: any) => {
      if (finalized) return
      finalized = true
      callbacks.onDone?.({
        expression: String(payload?.expression || 'exp-04'),
        memory_summary: String(payload?.memory_summary || ''),
      })
    }

    const emitError = (payload: any) => {
      const message =
        typeof payload?.message === 'string'
          ? payload.message
          : typeof payload === 'string'
            ? payload
            : 'stream error'
      callbacks.onError?.({ message })
    }

    const dispatch = (sseEvent: string, payload: any) => {
      if (!payload) return
      const envelopeType = String(payload?.type || payload?.event || '').trim()
      const eventType = (envelopeType || sseEvent || 'message').toLowerCase()
      debugLog('event', { sseEvent, eventType })

      switch (eventType) {
        case 'intent':
          callbacks.onIntent?.(payload.data ?? payload)
          return
        case 'plan':
          callbacks.onPlan?.(payload.data ?? payload)
          return
        case 'trace':
        case 'tool_step':
          callbacks.onToolStep?.((payload.data?.step ?? payload.step ?? payload.data ?? payload) as AelinToolStep)
          hasTraceSteps = true
          return
        case 'citations':
          callbacks.onCitations?.((payload.data ?? payload) as AelinCitation[])
          return
        case 'actions':
          callbacks.onActions?.((payload.data ?? payload) as AelinAction[])
          return
        case 'reply': {
          const chunk = payload.data?.chunk ?? payload.chunk ?? payload.data ?? ''
          callbacks.onReplyChunk?.(String(chunk))
          return
        }
        case 'ping':
          // Keepalive heartbeat from backend; no UI mutation needed.
          return
        case 'messages': {
          // DeepAgents v2 streaming chunks where type === "messages". We only
          // rely on the textual delta here so that the UI can stream the
          // answer; richer run-graph rendering will be handled by a separate
          // layer built on top of the raw chunk stream.
          const text =
            typeof payload?.data?.content === 'string'
              ? payload.data.content
              : typeof payload?.content === 'string'
                ? payload.content
                : ''
          if (text) {
            callbacks.onReplyChunk?.(text)
          }
          return
        }
        case 'final': {
          const result = payload.result ?? payload.data?.result ?? payload.data ?? {}
          if (Array.isArray(result.tool_trace) && !hasTraceSteps) {
            for (const step of result.tool_trace) {
              callbacks.onToolStep?.(step as AelinToolStep)
            }
          }
          if (Array.isArray(result.citations)) callbacks.onCitations?.(result.citations as AelinCitation[])
          if (Array.isArray(result.actions)) callbacks.onActions?.(result.actions as AelinAction[])
          if (typeof result.answer === 'string' && result.answer) {
            callbacks.onReplyChunk?.(result.answer)
          }
          emitDone(result)
          return
        }
        case 'error':
          emitError(payload.data ?? payload)
          return
        case 'done':
          emitDone(payload.data ?? payload)
          return
        default:
          return
      }
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
          console.error('[aelin-stream] callback_error', {
            message: String(callbackError?.message || ''),
            event: evt.event,
          })
        }
      }
    }
    debugLog('stream_done')
    emitDone()
  }).catch((err) => {
    const aborted = combined.aborted || String(err?.name || '') === 'AbortError'
    if (!aborted) {
      // eslint-disable-next-line no-console
      console.error('[aelin-stream] network_error', { message: String(err?.message || ''), stack: String(err?.stack || '') })
      callbacks.onError?.({ message: err.message })
    }
  })

  return () => controller.abort()
}
