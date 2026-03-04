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

export function ChatView() {
  const { sessions, activeSessionId, isStreaming, statusText, createSession } = useChatStore()
  const session = sessions.find((s) => s.id === activeSessionId)
  const messages = session?.messages ?? []
  const { send, captureAndSend, attachAndSend, stop } = useChatStream()
  const scrollRef = useRef<HTMLDivElement>(null)
  const compact = useMediaQuery('(max-width: 960px)')
  const viewportWidth = useViewportWidth()

  useAutoScrollToBottom(scrollRef, [
    messages.length,
    messages.at(-1)?.content,
    isStreaming,
  ])

  const handleSend = (text: string) => {
    if (!text.trim()) return
    send(text)
  }

  const handleCaptureAndSend = async (textHint: string) => {
    try {
      await captureAndSend(textHint)
    } catch (error: any) {
      const message = String(error?.message || '截图失败，请稍后重试')
      toast.error(message)
    }
  }

  const handleAttachAndSend = async (files: File[], textHint: string) => {
    try {
      await attachAndSend(files, textHint)
    } catch (error: any) {
      const message = String(error?.message || '附件处理失败，请稍后重试')
      toast.error(message)
      throw error
    }
  }

  useEffect(() => {
    if (sessions.length === 0) createSession()
  }, [sessions.length, createSession])

  return (
    <PageScaffold
      title="Chat"
      subtitle="Aelin 在线中"
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
        onAttachAndSend={handleAttachAndSend}
        onStop={stop}
        isStreaming={isStreaming}
        compact={compact}
      />
    </PageScaffold>
  )
}
