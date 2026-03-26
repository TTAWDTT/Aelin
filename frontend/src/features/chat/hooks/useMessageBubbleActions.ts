import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { aelinApi } from '@/shared/api/aelin'
import type { ChatAction, AelinBrowserConfirmResponse } from '@/shared/api/types'
import { useChatStore, type ChatMessage } from '../stores/chatStore'
import {
  buildBrowserConfirmBody,
  formatBrowserConfirmFeedback,
} from '../components/messageBubbleUtils'

interface UseMessageBubbleActionsOptions {
  message: ChatMessage
  onQuickPrompt?: (text: string) => void
}

function appendFollowupMessage(response: AelinBrowserConfirmResponse, sessionId: string | null) {
  const followup = (response.followup_result || {}) as Record<string, unknown>
  const followupAnswer = String(followup.answer || '').trim()
  if (!response.continued || !followupAnswer) return

  if (!sessionId) return
  const store = useChatStore.getState()
  const session = store.sessions.find((item) => item.id === sessionId)
  if (!session) return

  const nextMessage: ChatMessage = {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: followupAnswer,
    expression: String(followup.expression || '').trim() || undefined,
    citations: Array.isArray(followup.citations) ? followup.citations as ChatMessage['citations'] : undefined,
    actions: Array.isArray(followup.actions) ? followup.actions as ChatMessage['actions'] : undefined,
    timestamp: Date.now(),
  }

  store.setSessionMessages(sessionId, [...session.messages, nextMessage])
}

export function useMessageBubbleActions({ message: _message, onQuickPrompt }: UseMessageBubbleActionsOptions) {
  const confirmBrowser = useMutation({
    mutationFn: async (action: ChatAction) => {
      const originSessionId = useChatStore.getState().activeSessionId
      const response = await aelinApi.confirmBrowserAction(buildBrowserConfirmBody(action))
      return { response, originSessionId }
    },
    onSuccess: ({ response, originSessionId }) => {
      if (response.ok) {
        toast.success(String(response.message || '已确认并继续执行'))
        appendFollowupMessage(response, originSessionId)
        if (!response.continued && onQuickPrompt) {
          onQuickPrompt('我已确认，请继续完成刚才的浏览器任务并直接给我结果。')
        }
        return
      }
      toast.error(formatBrowserConfirmFeedback(response))
    },
    onError: (error: Error) => {
      toast.error(String(error?.message || '确认后执行失败'))
    },
  })

  return {
    confirmBrowser,
  }
}
