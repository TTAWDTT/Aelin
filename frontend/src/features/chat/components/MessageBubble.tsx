import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'
import { sourceIcon, relativeTime } from '@/shared/utils/format'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { AgentTracePanel } from './AgentTracePanel'

const EXPRESSION_LABELS: Record<string, string> = {
  'exp-02': '热情出击', 'exp-03': '温柔赞同', 'exp-04': '托腮思考',
  'exp-05': '轻声提醒', 'exp-06': '偷看观察', 'exp-07': '低落求助', 'exp-08': '不满委屈',
  'exp-09': '指着大笑', 'exp-10': '发财得意', 'exp-11': '趴桌躺平',
}

function resolveExpressionSticker(expression?: string) {
  const exp = String(expression || '').trim().toLowerCase()
  if (/^exp-(0[2-9]|1[0-1])$/.test(exp)) return `/expressions/${exp}.png`
  return ''
}

interface MessageBubbleProps {
  message: ChatMessage
  isThinking?: boolean
  thinkingText?: string
  compact?: boolean
  viewportWidth: number
}

function calculateCompactMaxWidth(viewportWidth: number) {
  const width = Number.isFinite(viewportWidth) ? viewportWidth : 960
  const ratio = 0.72
  const minWidth = 220
  return Math.max(minWidth, Math.floor(width * ratio))
}

export function MessageBubble({ message, isThinking = false, thinkingText, compact = false, viewportWidth }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const compactMaxWidth = calculateCompactMaxWidth(viewportWidth)
  const stickerSrc = !isUser ? resolveExpressionSticker(message.expression) : ''
  const stickerLabel = message.expression ? (EXPRESSION_LABELS[message.expression] ?? 'Aelin 表情') : 'Aelin 表情'

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
        <div
          className={cn(
            'prose prose-sm max-w-none break-words prose-neutral [overflow-wrap:anywhere] [&_a]:break-all [&_blockquote]:my-2 [&_code]:break-all [&_li]:my-0.5 [&_ol]:my-1.5 [&_p]:my-1.5 [&_pre]:my-2 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_ul]:my-1.5'
          )}
          style={{ fontFamily: 'var(--font-body)', lineHeight: compact ? 1.58 : 1.64, fontSize: compact ? '0.88rem' : '0.94rem' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (isUser ? '' : (isThinking ? '' : '…'))}</ReactMarkdown>
        </div>

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
        {message.citations && message.citations.length > 0 && (
          <details className="group mt-3.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-2">
            <summary className="cursor-pointer text-[11px] text-[var(--color-text-muted)] font-semibold uppercase tracking-wide">
              引用来源 ({message.citations.length})
            </summary>
            <div className="grid grid-rows-[0fr] transition-[grid-template-rows] duration-300 ease-out group-open:grid-rows-[1fr]">
              <div className="overflow-hidden">
                <div className="mt-2 space-y-1.5 opacity-0 translate-y-1 transition-all duration-300 ease-out group-open:translate-y-0 group-open:opacity-100">
                  {message.citations.map((c, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1.5 text-[11px] sm:flex-nowrap sm:gap-2 sm:px-2.5 sm:text-xs">
                      <span>{sourceIcon(c.source)}</span>
                      <span className="font-medium min-w-0 flex-1 break-all sm:truncate">[{i + 1}] {c.title}</span>
                      <span className="text-[var(--color-text-muted)]">{c.source_label}</span>
                      <span className="text-[var(--color-text-muted)] sm:inline">{relativeTime(c.received_at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </details>
        )}
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

function formatMessageTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
