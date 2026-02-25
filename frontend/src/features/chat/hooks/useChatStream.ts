import { useRef, useCallback } from 'react'
import { useChatStore, type ChatMessage } from '../stores/chatStore'
import { streamChat } from '@/shared/api/sse'
import type { AelinChatRequest, AelinToolStep } from '@/shared/api/types'

function mergeToolTrace(prev: AelinToolStep[] | undefined, step: AelinToolStep): AelinToolStep[] {
  const existing = [...(prev ?? [])]
  const stage = String(step.stage || '').trim()
  if (!stage) return existing

  const index = existing.findIndex((item) => String(item.stage || '').trim() === stage)
  if (index === -1) return [...existing, step]

  existing[index] = {
    ...existing[index],
    ...step,
    stage,
  }
  return existing
}

export function useChatStream() {
  const store = useChatStore()
  const abortRef = useRef<(() => void) | null>(null)

  const send = useCallback((text: string, images?: { dataUrl: string; name: string }[]) => {
    let sessionId = store.activeSessionId
    if (!sessionId) sessionId = store.createSession()

    const session = store.sessions.find(s => s.id === sessionId)
    const history = (session?.messages ?? []).slice(-10).map(m => ({ role: m.role, content: m.content }))

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(), role: 'user', content: text,
      images, timestamp: Date.now(),
    }
    store.addMessage(sessionId!, userMsg)

    // Add empty assistant message
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(), role: 'assistant', content: '',
      timestamp: Date.now(),
    }
    store.addMessage(sessionId!, assistantMsg)
    store.setStreaming(true)
    store.setStatusText('正在思考…')

    // Auto-title from first message
    if ((session?.messages.length ?? 0) === 0) {
      const title = text.length > 20 ? text.slice(0, 20) + '…' : text
      store.renameSession(sessionId!, title)
    }

    const body: AelinChatRequest = {
      query: text,
      workspace: session?.workspace || 'default',
      history,
      images: images?.map(i => ({ data_url: i.dataUrl, name: i.name })),
    }

    const cancel = streamChat(body, {
      onIntent: (d) => store.setStatusText(`意图: ${d.intent_type}`),
      onPlan: (d) => store.setStatusText(`计划: ${d.steps?.length || 0} 步`),
      onToolStep: (step) => {
        store.setStatusText(`${step.stage}…`)
        const currentTrace = store.getActiveSession()?.messages.findLast((m: ChatMessage) => m.role === 'assistant')?.toolTrace
        store.updateLastAssistant(sessionId!, {
          toolTrace: mergeToolTrace(currentTrace, step),
        })
      },
      onCitations: (citations) => store.updateLastAssistant(sessionId!, { citations }),
      onActions: (actions) => store.updateLastAssistant(sessionId!, { actions }),
      onReplyChunk: (chunk) => store.appendContent(sessionId!, chunk),
      onDone: (d) => {
        store.updateLastAssistant(sessionId!, { expression: d.expression, memorySummary: d.memory_summary })
        store.setStreaming(false)
        store.setStatusText('')
      },
      onError: (err) => {
        store.appendContent(sessionId!, `\n\n> ⚠️ 错误: ${err.message}`)
        store.setStreaming(false)
        store.setStatusText('')
      },
    })

    abortRef.current = cancel
  }, [store])

  const stop = useCallback(() => {
    abortRef.current?.()
    store.setStreaming(false)
    store.setStatusText('')
  }, [store])

  return { send, stop }
}
