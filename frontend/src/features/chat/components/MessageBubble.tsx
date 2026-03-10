import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { AgentTracePanel } from './AgentTracePanel'
import { MessageActionsPanel } from './MessageActionsPanel'
import { MessageCitationsPanel } from './MessageCitationsPanel'
import {
  calculateCompactMaxWidth,
  EXPRESSION_LABELS,
  formatMessageTime,
  resolveExpressionSticker,
} from './messageBubbleUtils'
import { useMessageBubbleActions } from '../hooks/useMessageBubbleActions'

interface MessageBubbleProps {
  message: ChatMessage
  isThinking?: boolean
  thinkingText?: string
  compact?: boolean
  viewportWidth: number
  onQuickPrompt?: (text: string) => void
}

function MessageBubbleComponent({ message, isThinking = false, thinkingText, compact = false, viewportWidth, onQuickPrompt }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const compactMaxWidth = calculateCompactMaxWidth(viewportWidth)
  const stickerSrc = !isUser ? resolveExpressionSticker(message.expression) : ''
  const stickerLabel = message.expression ? (EXPRESSION_LABELS[message.expression] ?? 'Aelin 表情') : 'Aelin 表情'
  const { confirmTrack, confirmBrowser } = useMessageBubbleActions({ message, onQuickPrompt })

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
              <span>{thinkingText || 'Aelin 正在思考'}</span>
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
        {isThinking && !isUser ? (
          <div
            className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]"
            style={{ fontFamily: 'var(--font-body)', lineHeight: compact ? 1.58 : 1.64, fontSize: compact ? '0.88rem' : '0.94rem' }}
          >
            {message.content || ''}
          </div>
        ) : (
          <div
            className={cn(
              'prose prose-sm max-w-none break-words prose-neutral [overflow-wrap:anywhere] [&_a]:break-all [&_blockquote]:my-2 [&_code]:break-all [&_li]:my-0.5 [&_ol]:my-1.5 [&_p]:my-1.5 [&_pre]:my-2 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_ul]:my-1.5'
            )}
            style={{ fontFamily: 'var(--font-body)', lineHeight: compact ? 1.58 : 1.64, fontSize: compact ? '0.88rem' : '0.94rem' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (isUser ? '' : '…')}</ReactMarkdown>
          </div>
        )}

        {!isUser && stickerSrc && !isThinking && (
          <div className="mt-2">
            <img
              src={stickerSrc}
              alt={stickerLabel}
              title={stickerLabel}
              className={cn('block object-contain', compact ? 'h-16 w-16' : 'h-20 w-20')}
              draggable={false}
            />
          </div>
        )}

        {/* Citations (collapsed by default) */}
        <MessageCitationsPanel citations={message.citations || []} />
        <MessageActionsPanel
          actions={message.actions || []}
          isTrackPending={confirmTrack.isPending}
          isBrowserPending={confirmBrowser.isPending}
          onTrackConfirm={(action) => confirmTrack.mutate(action)}
          onBrowserConfirm={(action) => confirmBrowser.mutate(action)}
        />
        {/* Tool trace */}
        {message.toolTrace && message.toolTrace.length > 0 && (
          <AgentTracePanel trace={message.toolTrace} live={isThinking} />
        )}

        <div className="mt-2 text-[10px] tracking-wide text-[var(--color-text-muted)]">
          {formatMessageTime(message.timestamp)}
        </div>
      </div>
    </article>
  )
}

export const MessageBubble = memo(MessageBubbleComponent, (prev, next) => (
  prev.message === next.message
  && prev.isThinking === next.isThinking
  && prev.thinkingText === next.thinkingText
  && prev.compact === next.compact
  && prev.viewportWidth === next.viewportWidth
  && prev.onQuickPrompt === next.onQuickPrompt
))
