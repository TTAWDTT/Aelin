import type { RefObject } from 'react'
import type { ChatMessage } from '../stores/chatStore'
import { MessageBubble } from './MessageBubble'
import { EmptyChatState } from './EmptyChatState'

interface ChatTimelineProps {
  scrollRef: RefObject<HTMLDivElement | null>
  messages: ChatMessage[]
  isStreaming: boolean
  onQuickPrompt: (text: string) => void
}

export function ChatTimeline({ scrollRef, messages, isStreaming, onQuickPrompt }: ChatTimelineProps) {
  const isEmpty = messages.length === 0

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 sm:px-5">
      {isEmpty ? (
        <EmptyChatState onQuickPrompt={onQuickPrompt} />
      ) : (
        <div className="mx-auto flex w-full max-w-[1040px] flex-col gap-3 pb-2">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isStreaming && <div className="h-2" />}
        </div>
      )}
    </div>
  )
}

