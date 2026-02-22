import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'
import { sourceIcon, relativeTime } from '@/shared/utils/format'
import { ExternalLink } from 'lucide-react'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { AgentTracePanel } from './AgentTracePanel'

const EXPRESSION_LABELS: Record<string, string> = {
  'exp-01': '捂嘴惊喜', 'exp-02': '热情出击', 'exp-03': '温柔赞同', 'exp-04': '托腮思考',
  'exp-05': '轻声提醒', 'exp-06': '偷看观察', 'exp-07': '低落求助', 'exp-08': '不满委屈',
  'exp-09': '指着大笑', 'exp-10': '发财得意', 'exp-11': '趴桌躺平',
}

interface MessageBubbleProps {
  message: ChatMessage
  isThinking?: boolean
  thinkingText?: string
}

export function MessageBubble({ message, isThinking = false, thinkingText }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <article className={cn('aelin-fade-up flex max-w-[86%] items-end gap-2.5 md:max-w-[80%]', isUser ? 'ml-auto flex-row-reverse' : '')}>
      {/* Avatar */}
      {!isUser && (
        <div className="shrink-0">
          <AelinAvatar
            size="sm"
            expression={message.expression}
            title={message.expression ? EXPRESSION_LABELS[message.expression] : 'Aelin'}
            className="!rounded-[10px]"
          />
        </div>
      )}
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] text-[11px] font-semibold text-[var(--color-text-muted)]">
          你
        </div>
      )}

      <div className={cn(
        'chat-elevate max-w-full rounded-[16px] px-4 py-3.5',
        isThinking && !isUser && 'chat-thinking-bubble',
        isUser
          ? 'rounded-tr-[6px] border border-[var(--color-border)] bg-[var(--color-panel-alt)]'
          : 'rounded-tl-[6px] border border-[var(--color-border)] bg-[var(--color-panel)]'
      )}>
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
            'prose prose-sm max-w-none prose-neutral',
            '[&_p]:my-1.5 [&_ul]:my-1.5 [&_ol]:my-1.5 [&_li]:my-0.5 [&_pre]:my-2 [&_blockquote]:my-2'
          )}
          style={{ fontFamily: 'var(--font-body)', lineHeight: 1.64, fontSize: '0.94rem' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (isUser ? '' : (isThinking ? '' : '…'))}</ReactMarkdown>
        </div>

        {/* Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-3.5 space-y-1.5">
            <div className="text-[11px] text-[var(--color-text-muted)] font-semibold uppercase tracking-wide">引用来源</div>
            {message.citations.map((c, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-1.5 text-xs">
                <span>{sourceIcon(c.source)}</span>
                <span className="font-medium truncate flex-1">[{i + 1}] {c.title}</span>
                <span className="text-[var(--color-text-muted)]">{c.source_label}</span>
                <span className="text-[var(--color-text-muted)]">{relativeTime(c.received_at)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Tool trace */}
        {message.toolTrace && message.toolTrace.length > 0 && (
          <AgentTracePanel trace={message.toolTrace} live={isThinking} />
        )}

        {/* Actions */}
        {message.actions && message.actions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.actions.map((a, i) => (
              <ActionChip key={i} action={a} />
            ))}
          </div>
        )}

        <div className="mt-2 text-[10px] tracking-wide text-[var(--color-text-muted)]">
          {formatMessageTime(message.timestamp)}
        </div>
      </div>
    </article>
  )
}

function ActionChip({ action }: { action: { kind: string; title: string; detail?: string; payload?: Record<string, string> } }) {
  const handleClick = () => {
    if (action.kind === 'open_url' && action.payload?.url) {
      window.open(action.payload.url, '_blank')
    }
    // track_confirm and other actions will be handled by parent
  }

  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--color-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-strong)]"
      title={action.detail}
    >
      {action.kind === 'open_url' && <ExternalLink size={12} />}
      {action.kind === 'track_confirm' && <span>🔔</span>}
      {action.title}
    </button>
  )
}

function formatMessageTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
