import { useRef, useEffect } from 'react'
import { useChatStore } from './stores/chatStore'
import { useChatStream } from './hooks/useChatStream'
import { ComposerBar } from './components/ComposerBar'
import { SessionTabs } from './components/SessionTabs'
import { ChatStatusBar } from './components/ChatStatusBar'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { ChatTimeline } from './components/ChatTimeline'
import { useAutoScrollToBottom } from './hooks/useAutoScrollToBottom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'

export function ChatView() {
  const { sessions, activeSessionId, isStreaming, statusText, createSession } = useChatStore()
  const session = sessions.find((s) => s.id === activeSessionId)
  const messages = session?.messages ?? []
  const { send, stop } = useChatStream()
  const scrollRef = useRef<HTMLDivElement>(null)
  const compact = useMediaQuery('(max-width: 960px)')

  useAutoScrollToBottom(scrollRef, [
    messages.length,
    messages.at(-1)?.content,
    isStreaming,
  ])

  const handleSend = (text: string, images?: { dataUrl: string; name: string }[]) => {
    if (!text.trim() && !images?.length) return
    send(text, images)
  }

  useEffect(() => {
    if (sessions.length === 0) createSession()
  }, [sessions.length, createSession])

  return (
    <PageScaffold
      title="Chat"
      subtitle="Aelin 在线中"
      contentClassName="flex flex-1 min-h-0 flex-col p-0"
      headerActions={<SessionTabs className="max-w-full sm:max-w-[420px]" />}
    >
      <ChatStatusBar isStreaming={isStreaming} statusText={statusText} compact={compact} />
      <ChatTimeline
        scrollRef={scrollRef}
        messages={messages}
        isStreaming={isStreaming}
        statusText={statusText}
        compact={compact}
        onQuickPrompt={handleSend}
      />
      <ComposerBar
        onSend={handleSend}
        onStop={stop}
        isStreaming={isStreaming}
        compact={compact}
      />
    </PageScaffold>
  )
}
