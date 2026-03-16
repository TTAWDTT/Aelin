import { useRef, useEffect } from 'react'
import toast from 'react-hot-toast'
import { useChatStore } from './stores/chatStore'
import { useChatStream } from './hooks/useChatStream'
import { ComposerBar } from './components/ComposerBar'
import { SessionTabs } from './components/SessionTabs'
import { ChatStatusBar } from './components/ChatStatusBar'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { ChatTimeline } from './components/ChatTimeline'
import { useAutoScrollToBottom } from './hooks/useAutoScrollToBottom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { useViewportWidth } from '@/shared/hooks/useViewportWidth'
import type { AelinAttachmentUploadResponse } from '@/shared/api/types'
import { useChatI18n } from './chatI18n'

export function ChatView() {
  const { sessions, activeSessionId, isStreaming, statusText, createSession } = useChatStore()
  const session = sessions.find((s) => s.id === activeSessionId)
  const messages = session?.messages ?? []
  const { send, captureAndSend, uploadAttachments, sendWithAttachments, stop } = useChatStream()
  const scrollRef = useRef<HTMLDivElement>(null)
  const compact = useMediaQuery('(max-width: 960px)')
  const viewportWidth = useViewportWidth()
  const { t } = useChatI18n()

  useAutoScrollToBottom(scrollRef, [
    messages.length,
    messages.at(-1)?.content,
    isStreaming,
  ])

  const handleSend = (text: string) => {
    if (!text.trim()) return
    send(text)
  }

  const handleCaptureAndSend = async (mode: 'fullscreen' | 'region', textHint: string) => {
    try {
      await captureAndSend(mode, textHint)
    } catch (error: any) {
      const message = String(error?.message || t('error.screenshot'))
      toast.error(message)
      throw error
    }
  }

  const handleUploadAttachments = async (files: File[]) => {
    try {
      return await uploadAttachments(files)
    } catch (error: any) {
      const message = String(error?.message || t('error.attach.process'))
      toast.error(message)
      throw error
    }
  }

  const handleSendWithAttachments = async (attachments: AelinAttachmentUploadResponse[], textHint: string) => {
    try {
      await sendWithAttachments(attachments, textHint)
    } catch (error: any) {
      const message = String(error?.message || t('error.attach.send'))
      toast.error(message)
      throw error
    }
  }

  useEffect(() => {
    if (sessions.length === 0) createSession()
  }, [sessions.length, createSession])

  return (
    <PageScaffold
      title={t('nav.title')}
      subtitle={t('nav.subtitle')}
      contentClassName="flex flex-1 min-h-0 flex-col p-0"
      headerActionsFullWidth
      headerActions={<SessionTabs wrap={compact} className="w-full min-w-0 max-w-full" />}
    >
      <ChatStatusBar isStreaming={isStreaming} statusText={statusText} compact={compact} />
      <ChatTimeline
        scrollRef={scrollRef}
        messages={messages}
        isStreaming={isStreaming}
        statusText={statusText}
        compact={compact}
        viewportWidth={viewportWidth}
        onQuickPrompt={handleSend}
      />
      <ComposerBar
        onSend={handleSend}
        onCaptureAndSend={handleCaptureAndSend}
        onUploadAttachments={handleUploadAttachments}
        onSendWithAttachments={handleSendWithAttachments}
        onStop={stop}
        isStreaming={isStreaming}
        compact={compact}
        placeholder={t('composer.placeholder')}
      />
    </PageScaffold>
  )
}
