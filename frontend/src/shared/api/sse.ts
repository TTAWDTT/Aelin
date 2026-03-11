import type { AelinChatRequest, AelinCitation, AelinAction, AelinToolStep } from './types'

interface StreamCallbacks {
  onIntent?: (data: { intent_type: string; time_sensitivity?: string }) => void
  onPlan?: (data: { steps: string[] }) => void
  onToolStep?: (step: AelinToolStep) => void
  onToolEvent?: (event: Record<string, unknown>) => void
  onCitations?: (citations: AelinCitation[]) => void
  onActions?: (actions: AelinAction[]) => void
  onReplyChunk?: (text: string) => void
  onDone?: (data: { answer?: string; expression?: string; memory_summary?: string }) => void
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
  if (!text) return null
  if (text === '[DONE]') return { __streamDone: true }
  try {
    return JSON.parse(text)
  } catch {
    return { message: text }
  }
}

function nextAnimationFrame(): Promise<void> {
  return new Promise((resolve) => {
    const raf =
      typeof globalThis !== 'undefined' &&
      typeof (globalThis as { requestAnimationFrame?: (callback: FrameRequestCallback) => number }).requestAnimationFrame === 'function'
        ? (globalThis as { requestAnimationFrame: (callback: FrameRequestCallback) => number }).requestAnimationFrame.bind(globalThis)
        : (callback: () => void) => setTimeout(callback, 0)
    raf(() => resolve())
  })
}

async function emitReplyChunked(text: string, onReplyChunk?: (text: string) => void): Promise<boolean> {
  const raw = String(text || '')
  if (!raw || !onReplyChunk) return false
  const chunkSize = 28
  const maxAnimatedChars = chunkSize * 10
  const glyphs = Array.from(raw)
  const animateByFrame = glyphs.length <= maxAnimatedChars
  for (let idx = 0; idx < glyphs.length; idx += chunkSize) {
    onReplyChunk(glyphs.slice(idx, idx + chunkSize).join(''))
    if (animateByFrame && idx + chunkSize < glyphs.length) {
      await nextAnimationFrame()
    }
  }
  return true
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
    url: `${BASE}/api/v1/aelin/chat/stream`,
    source: body?.source || 'chat_ui',
    historyCount: Array.isArray(body?.history) ? body.history.length : 0,
    imageCount: Array.isArray(body?.images) ? body.images.length : 0,
  })
  fetch(`${BASE}/api/v1/aelin/chat/stream`, {
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
    let hasStreamedReply = false
    let hasStreamedTrace = false

    const emitDone = (payload?: any) => {
      if (finalized) return
      finalized = true
      callbacks.onDone?.({
        answer: typeof payload?.answer === 'string' ? payload.answer : '',
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

    const dispatch = async (sseEvent: string, payload: any): Promise<string> => {
      if (payload?.__streamDone) {
        emitDone({})
        return 'done'
      }
      const envelopeType = String(payload?.type || payload?.event || '').trim()
      const eventType = (envelopeType || sseEvent || 'message').toLowerCase()
      debugLog('event', { sseEvent, eventType })

      if (!payload) {
        if (eventType === 'done' || eventType === 'final') {
          emitDone({})
          return eventType
        }
        return eventType
      }

      switch (eventType) {
        case 'intent':
          callbacks.onIntent?.(payload.data ?? payload)
          return eventType
        case 'plan':
          callbacks.onPlan?.(payload.data ?? payload)
          return eventType
        case 'trace':
        case 'tool_step':
          hasStreamedTrace = true
          callbacks.onToolStep?.((payload.data?.step ?? payload.step ?? payload.data ?? payload) as AelinToolStep)
          return eventType
        case 'tool_event':
          hasStreamedTrace = true
          callbacks.onToolEvent?.((payload.data ?? payload) as Record<string, unknown>)
          return eventType
        case 'citations':
          callbacks.onCitations?.((payload.data ?? payload) as AelinCitation[])
          return eventType
        case 'actions':
          callbacks.onActions?.((payload.data ?? payload) as AelinAction[])
          return eventType
        case 'reply': {
          const chunk = payload.data?.chunk ?? payload.chunk ?? payload.data ?? ''
          if (String(chunk).length > 0) hasStreamedReply = true
          callbacks.onReplyChunk?.(String(chunk))
          return eventType
        }
        case 'ping':
          // Keepalive heartbeat from backend; no UI mutation needed.
          return eventType
        case 'final': {
          const result = payload.result ?? payload.data?.result ?? payload.data ?? {}
          if (!hasStreamedTrace && Array.isArray(result.tool_trace)) {
            for (const step of result.tool_trace) {
              callbacks.onToolStep?.(step as AelinToolStep)
              await nextAnimationFrame()
            }
          }
          if (Array.isArray(result.citations)) callbacks.onCitations?.(result.citations as AelinCitation[])
          if (Array.isArray(result.actions)) callbacks.onActions?.(result.actions as AelinAction[])
          if (!hasStreamedReply && typeof result.answer === 'string' && result.answer) {
            const streamed = await emitReplyChunked(String(result.answer), callbacks.onReplyChunk)
            if (streamed) hasStreamedReply = true
          }
          emitDone(result)
          return eventType
        }
        case 'error':
          emitError(payload.data ?? payload)
          return eventType
        case 'done':
          emitDone(payload.data ?? payload)
          return eventType
        default:
          return eventType
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
          await dispatch(evt.event, payload)
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
