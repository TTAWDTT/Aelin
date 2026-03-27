import type { ChatMessage } from '../chatTypes'
import type { ExecutionToolCall } from '../executionStreamUtils'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { MessageActionsPanel } from './MessageActionsPanel'
import { MessageCitationsPanel } from './MessageCitationsPanel'
import { MarkdownMessage } from './MarkdownMessage'
import {
  calculateCompactMaxWidth,
  EXPRESSION_LABELS,
  formatMessageTime,
  resolveExpressionSticker,
} from './messageBubbleUtils'
import { useMessageBubbleActions } from '../hooks/useMessageBubbleActions'
import { useLocaleStore } from '@/shared/stores/localeStore'

interface MessageBubbleProps {
  message: ChatMessage
  toolCalls?: ExecutionToolCall[]
  isThinking?: boolean
  thinkingText?: string
  compact?: boolean
  viewportWidth: number
  onQuickPrompt?: (text: string) => void
}

export function MessageBubble({
  message,
  toolCalls = [],
  isThinking = false,
  thinkingText,
  compact = false,
  viewportWidth,
  onQuickPrompt,
}: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const compactMaxWidth = calculateCompactMaxWidth(viewportWidth)
  const stickerSrc = !isUser ? resolveExpressionSticker(message.expression) : ''
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const stickerLabel = message.expression
    ? EXPRESSION_LABELS[message.expression] ?? (isZh ? 'Aelin 表情' : 'Aelin expression')
    : isZh
      ? 'Aelin 表情'
      : 'Aelin expression'
  const { confirmBrowser } = useMessageBubbleActions({ message, onQuickPrompt })

  return (
    <article className={cn(
      'aelin-fade-up flex min-w-0 w-full',
      compact ? 'max-w-full items-start gap-1.5' : 'max-w-[94%] items-end gap-2 sm:max-w-[86%] sm:gap-2.5 md:max-w-[80%]',
      isUser ? 'ml-auto flex-row-reverse' : ''
    )}>
      {/* Avatar */}
      {!isUser && (
        <div className="shrink-0 max-[500px]:hidden">
          <AelinAvatar
            size="sm"
            title="Aelin"
            className={cn('!rounded-[10px]', compact && '!h-6 !w-6')}
          />
        </div>
      )}

      <div className={cn(
        'chat-elevate min-w-0 rounded-[16px]',
        'max-w-full',
        compact ? 'px-2.5 py-2' : 'px-3 py-2.5 sm:px-4 sm:py-3.5',
        isThinking && !isUser && 'chat-thinking-bubble',
        isUser
          ? 'rounded-tr-[6px] border border-[var(--color-border)] bg-[var(--color-panel-alt)]'
          : 'rounded-tl-[6px] border border-[var(--color-border)] bg-[var(--color-panel)]'
      )} style={compact ? { maxWidth: `${compactMaxWidth}px` } : undefined}>
        {!isUser && isThinking && (
          <div className="mb-2 flex items-center gap-2">
            <img
              src="/gif/action_05.gif"
              alt="Aelin is thinking"
              className="h-7 w-7 rounded-[8px] border border-[var(--color-border)] object-cover"
              draggable={false}
            />
            <div className="flex items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
              <span>{thinkingText || (isZh ? 'Aelin 正在思考' : 'Aelin is thinking')}</span>
              <span className="chat-thinking-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        )}

        {/* Images */}
        {message.images && message.images.length > 0 && (
          <div className="mb-2.5 flex gap-2">
            {message.images.map((img, i) => (
              <img key={i} src={img.dataUrl} alt={img.name} className="h-20 w-20 rounded-xl object-cover" />
            ))}
          </div>
        )}

        {/* Content */}
        <MarkdownMessage content={message.content || ''} compact={compact} />

        {!isUser && toolCalls.length > 0 && (
          <div className="mt-2.5 space-y-1.5 border-t border-[var(--color-border)] pt-2">
            {toolCalls.map((tool) => (
              <div
                key={tool.key}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2.5 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-[var(--color-text)]">
                    {tool.name}
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    {tool.state}
                  </span>
                </div>
                {tool.args && (
                  <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                    args: {tool.args}
                  </div>
                )}
                {tool.result && (
                  <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                    result: {tool.result}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {!isUser && stickerSrc && !isThinking && (
          <div className="mt-2">
            <img
              src={stickerSrc}
              alt={stickerLabel}
              title={stickerLabel}
              className={cn(
                'block rounded-[18px] object-contain',
                compact ? 'h-16 w-16' : 'h-20 w-20'
              )}
              draggable={false}
            />
          </div>
        )}

        {/* Citations (collapsed by default) */}
        <MessageCitationsPanel citations={message.citations || []} />
        <MessageActionsPanel
          actions={message.actions || []}
          isBrowserPending={confirmBrowser.isPending}
          onBrowserConfirm={(action) => confirmBrowser.mutate(action)}
        />

        <div className="mt-2 text-[10px] tracking-wide text-[var(--color-text-muted)]">
          {formatMessageTime(message.timestamp)}
        </div>
      </div>
    </article>
  )
}
