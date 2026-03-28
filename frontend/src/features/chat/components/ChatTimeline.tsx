import type { RefObject } from 'react'
import type { ChatMessage } from '../chatTypes'
import type { ExecutionToolCall } from '../executionStreamUtils'
import { MessageBubble } from './MessageBubble'
import { EmptyChatState } from './EmptyChatState'
import { useChatI18n } from '../chatI18n'

interface ChatTimelineProps {
  scrollRef: RefObject<HTMLDivElement | null>
  messages: ChatMessage[]
  isStreaming: boolean
  statusText?: string
  compact?: boolean
  viewportWidth: number
  toolCallsByMessage?: Map<string, ExecutionToolCall[]>
  onQuickPrompt: (text: string) => void
}

export function ChatTimeline({
  scrollRef,
  messages,
  isStreaming,
  statusText,
  compact = false,
  viewportWidth,
  toolCallsByMessage,
  onQuickPrompt,
}: ChatTimelineProps) {
  const isEmpty = messages.length === 0
  const lastMessage = messages.at(-1)
  const activeAssistantId =
    isStreaming && lastMessage?.role === 'assistant'
      ? lastMessage.id
      : ''
  const showPendingAssistant = isStreaming && lastMessage?.role !== 'assistant'
  const { t } = useChatI18n()

  return (
    <div
      ref={scrollRef}
      className={`min-w-0 flex-1 overflow-y-auto ${
        compact ? 'px-2 py-2.5 max-[500px]:px-1 max-[500px]:py-2' : 'px-2.5 py-3 sm:px-5 sm:py-4'
      } [overflow-anchor:none]`}
    >
      {isEmpty ? (
        <EmptyChatState onQuickPrompt={onQuickPrompt} />
      ) : (
        <div
          className={`mx-auto flex min-w-0 w-full max-w-[880px] flex-col ${
            compact ? 'gap-2.5 pb-1.5 max-[500px]:gap-2' : 'gap-3.5 pb-2'
          }`}
        >
          {messages.map((message) => {
            return (
              <div key={message.id} className="flex flex-col gap-1.5">
                <MessageBubble
                  message={message}
                  toolCalls={toolCallsByMessage?.get(message.id) ?? []}
                  isThinking={Boolean(activeAssistantId) && message.id === activeAssistantId}
                  thinkingText={statusText}
                  compact={compact}
                  viewportWidth={viewportWidth}
                  onQuickPrompt={onQuickPrompt}
                />
              </div>
            )
          })}
          {showPendingAssistant && (
            <div className="flex flex-col gap-1.5">
              <MessageBubble
                message={{
                  id: 'pending-assistant',
                  role: 'assistant',
                  content: '',
                  timestamp: Date.now(),
                }}
                toolCalls={[]}
                isThinking
                thinkingText={statusText}
                compact={compact}
                viewportWidth={viewportWidth}
                onQuickPrompt={onQuickPrompt}
              />
            </div>
          )}
          {isStreaming && <div className="h-2" />}
          <div className="h-px [overflow-anchor:auto]" />
        </div>
      )}
    </div>
  )
}
