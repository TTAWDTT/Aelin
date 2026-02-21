import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'
import { sourceIcon, relativeTime } from '@/shared/utils/format'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { useState } from 'react'
import { AelinAvatar } from '@/shared/components/AelinAvatar'

const EXPRESSION_LABELS: Record<string, string> = {
  'exp-01': '捂嘴惊喜', 'exp-02': '热情出击', 'exp-03': '温柔赞同', 'exp-04': '托腮思考',
  'exp-05': '轻声提醒', 'exp-06': '偷看观察', 'exp-07': '低落求助', 'exp-08': '不满委屈',
  'exp-09': '指着大笑', 'exp-10': '发财得意', 'exp-11': '趴桌躺平',
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const [traceOpen, setTraceOpen] = useState(false)

  return (
    <article className={cn('aelin-fade-up flex max-w-[82%] items-end gap-2.5', isUser ? 'ml-auto flex-row-reverse' : '')}>
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
        'chat-elevate max-w-full rounded-[14px] px-4 py-3',
        isUser
          ? 'rounded-tr-[4px] border border-[var(--color-border)] bg-[var(--color-panel-alt)]'
          : 'rounded-tl-[4px] border border-[var(--color-border)] bg-[var(--color-panel)]'
      )}>
        {/* Images */}
        {message.images && message.images.length > 0 && (
          <div className="mb-2.5 flex gap-2">
            {message.images.map((img, i) => (
              <img key={i} src={img.dataUrl} alt={img.name} className="h-20 w-20 rounded-xl object-cover" />
            ))}
          </div>
        )}

        {/* Content */}
        <div className={cn('prose prose-sm max-w-none prose-neutral')}
          style={{ fontFamily: 'var(--font-body)', lineHeight: 1.64, fontSize: '0.94rem' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || (isUser ? '' : '…')}</ReactMarkdown>
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
          <div className="mt-2.5">
            <button onClick={() => setTraceOpen(!traceOpen)}
              className="flex items-center gap-1 rounded-full px-1 text-[11px] text-[var(--color-text-muted)] hover:text-[var(--color-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-strong)]">
              {traceOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              工具调用 ({message.toolTrace.length})
            </button>
            {traceOpen && (
              <div className="mt-1 space-y-0.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)] p-2 text-[11px] text-[var(--color-text-muted)]">
                {message.toolTrace.map((t, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <span className={t.status === 'completed' ? 'text-[var(--color-green)]' : 'text-[var(--color-warning)]'}>
                      {t.status === 'completed' ? '✓' : '⏳'}
                    </span>
                    <span>{t.stage}</span>
                    {t.detail && <span className="opacity-60">— {t.detail}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
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
