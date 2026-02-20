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

export function streamChat(body: AelinChatRequest, callbacks: StreamCallbacks, signal?: AbortSignal): () => void {
  const controller = new AbortController()
  const combined = signal ? AbortSignal.any([signal, controller.signal]) : controller.signal
  const token = localStorage.getItem('token')
  const BASE = import.meta.env.VITE_API_BASE || ''

  fetch(`${BASE}/api/v1/aelin/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
    signal: combined,
  }).then(async (res) => {
    if (!res.ok) { callbacks.onError?.({ message: `HTTP ${res.status}` }); return }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw || raw === '[DONE]') continue
        try {
          const evt = JSON.parse(raw)
          const type = evt.type || evt.event
          switch (type) {
            case 'intent': callbacks.onIntent?.(evt.data ?? evt); break
            case 'plan': callbacks.onPlan?.(evt.data ?? evt); break
            case 'tool_step': callbacks.onToolStep?.(evt.data ?? evt); break
            case 'citations': callbacks.onCitations?.(evt.data ?? evt); break
            case 'actions': callbacks.onActions?.(evt.data ?? evt); break
            case 'reply': callbacks.onReplyChunk?.(evt.data?.chunk ?? evt.chunk ?? ''); break
            case 'done': callbacks.onDone?.(evt.data ?? evt); break
            case 'error': callbacks.onError?.(evt.data ?? evt); break
          }
        } catch { /* skip malformed */ }
      }
    }
  }).catch((err) => {
    if (!combined.aborted) callbacks.onError?.({ message: err.message })
  })

  return () => controller.abort()
}
