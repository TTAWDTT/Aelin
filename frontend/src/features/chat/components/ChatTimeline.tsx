import type { RefObject } from 'react'
import type { ChatMessage } from '../stores/chatStore'
import { MessageBubble } from './MessageBubble'
import { EmptyChatState } from './EmptyChatState'

interface ChatTimelineProps {
  scrollRef: RefObject<HTMLDivElement | null>
  messages: ChatMessage[]
  isStreaming: boolean
  statusText?: string
  compact?: boolean
  onQuickPrompt: (text: string) => void
}

export function ChatTimeline({ scrollRef, messages, isStreaming, statusText, compact = false, onQuickPrompt }: ChatTimelineProps) {
  const isEmpty = messages.length === 0
  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id

  return (
    <div ref={scrollRef} className={`flex-1 overflow-y-auto ${compact ? 'px-2 py-2.5' : 'px-2.5 py-3 sm:px-5 sm:py-4'}`}>
      {isEmpty ? (
        <EmptyChatState onQuickPrompt={onQuickPrompt} />
      ) : (
        <div className={`mx-auto flex w-full max-w-[880px] flex-col ${compact ? 'gap-2.5 pb-1.5' : 'gap-3.5 pb-2'}`}>
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              isThinking={isStreaming && message.id === lastAssistantId}
              thinkingText={statusText}
              compact={compact}
            />
          ))}
          {isStreaming && <div className="h-2" />}
        </div>
      )}
    </div>
  )
}
