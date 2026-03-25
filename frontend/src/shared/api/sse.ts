import type {
  AelinChatRequest,
  AelinCitation,
  AelinAction,
  DeepAgentsExecutionEvent,
  DeepAgentsToolRun,
} from './types'
import { createExecutionEvent } from '@/features/chat/executionEventUtils'

interface StreamCallbacks {
  onExecutionEvent?: (event: DeepAgentsExecutionEvent) => void
  onCitations?: (citations: AelinCitation[]) => void
  onActions?: (actions: AelinAction[]) => void
  onReplyChunk?: (text: string) => void
  onToolRuns?: (runs: DeepAgentsToolRun[]) => void
  onDone?: (data: { expression: string; memory_summary: string; answer?: string }) => void
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
    let hasReplyText = false

    const emitDone = (payload?: any) => {
      if (finalized) return
      finalized = true
      callbacks.onDone?.({
        expression: String(payload?.expression || 'exp-04'),
        memory_summary: String(payload?.memory_summary || ''),
        answer: typeof payload?.answer === 'string' ? payload.answer : '',
      })
    }

    const emitError = (payload: any) => {
      const message =
        typeof payload?.message === 'string'
          ? payload.message
          : typeof payload === 'string'
            ? payload
            : 'stream error'
      const code =
        typeof payload?.code === 'string'
          ? payload.code
          : typeof payload?.error === 'string'
            ? payload.error
            : undefined
      callbacks.onError?.({ message, code })
    }

    const dispatch = (sseEvent: string, payload: any) => {
      if (!payload) return
      const envelopeType = String(payload?.type || payload?.event || '').trim()
      const eventType = (envelopeType || sseEvent || 'message').toLowerCase()
      debugLog('event', { sseEvent, eventType })

      if (!['reply', 'ping', 'done'].includes(eventType)) {
        const executionEvent = createExecutionEvent(
          eventType,
          payload?.data != null && ['messages', 'updates', 'tasks', 'values'].includes(eventType)
            ? { ...(payload.data || {}), ns: payload?.ns ?? [] }
            : payload,
        )
        if (executionEvent) {
          callbacks.onExecutionEvent?.(executionEvent)
        }
      }

      switch (eventType) {
        case 'citations':
          callbacks.onCitations?.((payload.data ?? payload) as AelinCitation[])
          return
        case 'actions':
          callbacks.onActions?.((payload.data ?? payload) as AelinAction[])
          return
        case 'reply': {
          // Legacy compatibility event. The native DeepAgents/LangGraph
          // streaming path now uses `messages` as the primary text source,
          // so we intentionally avoid double-appending here.
          return
        }
        case 'ping':
          // Keepalive heartbeat from backend; no UI mutation needed.
          return
        case 'messages': {
          const metadata = payload?.data?.metadata ?? {}
          const nodeName = String(metadata?.langgraph_node ?? '').trim().toLowerCase()
          const text =
            typeof payload?.data?.content === 'string'
              ? payload.data.content
              : typeof payload?.content === 'string'
                ? payload.content
                : ''
          if (text && nodeName === 'model') {
            callbacks.onReplyChunk?.(text)
            hasReplyText = true
          }
          return
        }
        case 'final': {
          const result = payload.result ?? payload.data?.result ?? payload.data ?? {}
          const rawToolRuns = payload.tool_runs ?? payload.data?.tool_runs
          if (Array.isArray(rawToolRuns) && rawToolRuns.length > 0) {
            callbacks.onToolRuns?.(rawToolRuns as DeepAgentsToolRun[])
          }

          if (Array.isArray(result.citations)) callbacks.onCitations?.(result.citations as AelinCitation[])
          if (Array.isArray(result.actions)) callbacks.onActions?.(result.actions as AelinAction[])
          const answer =
            typeof result.answer === 'string' && result.answer
              ? result.answer
              : typeof payload.answer === 'string' && payload.answer
                ? payload.answer
                : typeof payload.data?.answer === 'string' && payload.data.answer
                  ? payload.data.answer
                  : ''
          if (answer && !hasReplyText) {
            callbacks.onReplyChunk?.(answer)
            hasReplyText = true
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
