import { useRef, useEffect } from 'react'
import { useChatStore } from './stores/chatStore'
import { useChatStream } from './hooks/useChatStream'
import { MessageBubble } from './components/MessageBubble'
import { ComposerBar } from './components/ComposerBar'
import { SessionTabs } from './components/SessionTabs'
import { EmptyChatState } from './components/EmptyChatState'
import { ChatStatusBar } from './components/ChatStatusBar'
import { cn } from '@/shared/utils/cn'

export function ChatView() {
  const { sessions, activeSessionId, isStreaming, statusText, searchMode, setSearchMode, createSession } = useChatStore()
  const session = sessions.find(s => s.id === activeSessionId)
  const { send, stop } = useChatStream()
  const scrollRef = useRef<HTMLDivElement>(null)
  const isEmpty = !session || session.messages.length === 0

  // Auto scroll on new messages
  useEffect(() => {
    const el = scrollRef.current
    if (!isEmpty && el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [isEmpty, session?.messages.length, session?.messages.at(-1)?.content])

  const handleSend = (text: string, images?: { dataUrl: string; name: string }[]) => {
    if (!text.trim() && !images?.length) return
    send(text, images)
  }

  // Ensure there's at least one session
  useEffect(() => {
    if (sessions.length === 0) createSession()
  }, [sessions.length, createSession])

  return (
    <div className={cn('flex h-full min-h-0 flex-col', isEmpty && 'bg-[var(--color-bg)]')}>
      {(!isEmpty || sessions.length > 1) && <SessionTabs />}

      <ChatStatusBar isStreaming={isStreaming} statusText={statusText} />

      {isEmpty ? (
        <EmptyChatState
          onSend={handleSend}
          onStop={stop}
          isStreaming={isStreaming}
          searchMode={searchMode}
          onSearchModeChange={setSearchMode}
        />
      ) : (
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-5 sm:px-5">
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 pb-2">
            {session?.messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isStreaming && <div className="h-2" />}
          </div>
        </div>
      )}

      {!isEmpty && (
        <ComposerBar
          onSend={handleSend}
          onStop={stop}
          isStreaming={isStreaming}
          searchMode={searchMode}
          onSearchModeChange={setSearchMode}
        />
      )}
    </div>
  )
}
