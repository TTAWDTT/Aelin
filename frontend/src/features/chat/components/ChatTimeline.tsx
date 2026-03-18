import type { RefObject } from 'react'
import type { ChatMessage } from '../stores/chatStore'
import { MessageBubble } from './MessageBubble'
import { EmptyChatState } from './EmptyChatState'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import { extractPlaneTaskMeta } from '../traceUtils'
import { useChatI18n } from '../chatI18n'

interface ChatTimelineProps {
  scrollRef: RefObject<HTMLDivElement | null>
  messages: ChatMessage[]
  isStreaming: boolean
  statusText?: string
  compact?: boolean
  viewportWidth: number
  onQuickPrompt: (text: string) => void
  onOpenExecutionForMessage?: (messageId: string | null) => void
}

export function ChatTimeline({
  scrollRef,
  messages,
  isStreaming,
  statusText,
  compact = false,
  viewportWidth,
  onQuickPrompt,
  onOpenExecutionForMessage,
}: ChatTimelineProps) {
  const isEmpty = messages.length === 0
  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id
  const { focusedMessageId } = useExecutionPaneStore()
  const { t } = useChatI18n()

  const planeChipsByMessageId: Record<
    string,
    { label: string; targetAssistantId: string | null }
  > = {}

  for (let i = 0; i < messages.length; i += 1) {
    const msg = messages[i]
    if (msg.role !== 'user') continue
    const assistant = messages.slice(i + 1).find(
      (m) => m.role === 'assistant' && m.toolTrace && m.toolTrace.length
    )
    if (!assistant || !assistant.toolTrace || assistant.toolTrace.length === 0) continue
    const planeMeta = extractPlaneTaskMeta(assistant.toolTrace)
    if (!planeMeta) continue

    const statusKey =
      planeMeta.state === 'waiting_user'
        ? 'plane.chip.status.waiting'
        : planeMeta.state === 'running'
          ? 'plane.chip.status.running'
          : planeMeta.state === 'completed'
            ? 'plane.chip.status.completed'
            : planeMeta.state === 'failed'
              ? 'plane.chip.status.failed'
              : 'plane.chip.status.unknown'

    const label = t('plane.chip.label', {
      plane: planeMeta.plane,
      status: t(statusKey),
    })

    planeChipsByMessageId[msg.id] = {
      label,
      targetAssistantId: assistant.id,
    }
  }

  return (
    <div
      ref={scrollRef}
      className={`min-w-0 flex-1 overflow-y-auto ${
        compact ? 'px-2 py-2.5 max-[500px]:px-1 max-[500px]:py-2' : 'px-2.5 py-3 sm:px-5 sm:py-4'
      }`}
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
            const chip = planeChipsByMessageId[message.id]
            const isHighlighted = message.id === focusedMessageId

            return (
              <div key={message.id} className="flex flex-col gap-1.5">
                <MessageBubble
                  message={message}
                  isThinking={isStreaming && message.id === lastAssistantId}
                  thinkingText={statusText}
                  compact={compact}
                  viewportWidth={viewportWidth}
                  onQuickPrompt={onQuickPrompt}
                  highlighted={isHighlighted}
                />
                {chip && (
                  <div className="pl-7 text-[10px] text-[var(--color-text-muted)] max-[500px]:pl-5">
                    <button
                      type="button"
                      onClick={() => {
                        if (onOpenExecutionForMessage) {
                          onOpenExecutionForMessage(chip.targetAssistantId)
                        }
                      }}
                      className="inline-flex max-w-full items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)] hover:bg-[var(--color-panel-alt)] hover:text-[var(--color-text)]"
                    >
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
                      <span className="truncate">{chip.label}</span>
                    </button>
                  </div>
                )}
              </div>
            )
          })}
          {isStreaming && <div className="h-2" />}
        </div>
      )}
    </div>
  )
}
