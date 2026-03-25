import { useCallback, useRef } from 'react'
import { streamChat } from '@/shared/api/sse'
import { useChatStore } from '../stores/chatStore'
import { useChatI18n } from '../chatI18n'
import {
  buildAssistantMessage,
  buildChatRequest,
  buildHistory,
  buildStreamCallbacks,
  buildUserMessage,
  maybeRenameFreshSession,
  normalizeAttachmentIds,
  resolveSessionForSend,
  type PendingImage,
} from './chatStreamHelpers'

export function useDeepAgentsStream() {
  const store = useChatStore()
  const abortRef = useRef<(() => void) | null>(null)
  const { t } = useChatI18n()

  const send = useCallback(
    (text: string, images?: PendingImage[], attachmentIds?: number[]) => {
      abortRef.current?.()
      abortRef.current = null

      const { sessionId, session } = resolveSessionForSend(store)
      const normalizedAttachmentIds = normalizeAttachmentIds(attachmentIds)
      const history = buildHistory(session)

      store.addMessage(sessionId, buildUserMessage(text, images))
      store.addMessage(sessionId, buildAssistantMessage())
      store.setStreaming(true)
      store.setStatusText(t('status.thinking'))

      maybeRenameFreshSession(store, sessionId, session, text, images, normalizedAttachmentIds)

      const body = buildChatRequest({
        text,
        session,
        history,
        images,
        attachmentIds: normalizedAttachmentIds,
      })

      let cancel = () => {}
      cancel = streamChat(
        body,
        buildStreamCallbacks({
          store,
          sessionId,
          abortRef,
          getCancel: () => cancel,
        }),
      )

      abortRef.current = cancel
    },
    [store, t],
  )

  const stop = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    store.setStreaming(false)
    store.setStatusText(t('status.cancelled'))
    store.setLastErrorCode(null)
  }, [store, t])

  return {
    send,
    stop,
    isStreaming: store.isStreaming,
  }
}
