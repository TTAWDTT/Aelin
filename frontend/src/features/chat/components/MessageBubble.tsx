import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore, type ChatMessage } from '../stores/chatStore'
import { cn } from '@/shared/utils/cn'
import { sourceIcon, relativeTime } from '@/shared/utils/format'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { AgentTracePanel } from './AgentTracePanel'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinAction, AelinTrackConfirmRequest } from '@/shared/api/types'

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
  onQuickPrompt?: (text: string) => void
}

function calculateCompactMaxWidth(viewportWidth: number) {
  const width = Number.isFinite(viewportWidth) ? viewportWidth : 960
  const ratio = 0.72
  const minWidth = 220
  return Math.max(minWidth, Math.floor(width * ratio))
}

function resolveActionHref(action: AelinAction): string {
  const kind = String(action.kind || '').trim().toLowerCase()
  const payload = action.payload || {}
  if (kind === 'open_tracking') {
    const targetId = String(payload.target_id || '').trim()
    if (targetId) return `/tracking/${encodeURIComponent(targetId)}`
    return '/tracking'
  }
  if (kind === 'open_desk' || kind === 'open_todos') {
    const path = String(payload.path || '').trim()
    return path || '/tracking?panel=desk'
  }
  if (kind === 'open_settings') {
    const path = String(payload.path || '').trim()
    return path || '/settings'
  }
  if (kind === 'open_message') {
    const messageId = String(payload.message_id || '').trim()
    if (messageId) return `/tracking?panel=desk&message_id=${encodeURIComponent(messageId)}`
    return '/tracking?panel=desk'
  }
  return ''
}

function buildTrackConfirmBody(action: AelinAction, fallbackText: string): AelinTrackConfirmRequest | null {
  const payload = action.payload || {}
  const target = String(payload.target || payload.query || fallbackText || '').trim().slice(0, 240)
  if (!target) return null
  const source = String(payload.source || 'auto').trim().toLowerCase() || 'auto'
  const query = String(payload.query || '').trim().slice(0, 500)
  const workspace = String(payload.workspace || 'default').trim() || 'default'
  return {
    target,
    source,
    query: query || undefined,
    workspace,
  }
}

function formatBrowserConfirmFeedback(res: { message?: string; tool_result?: Record<string, unknown> }) {
  const base = String(res.message || '确认后执行失败').trim()
  const toolResult = (res.tool_result || {}) as Record<string, unknown>
  const restart = (toolResult.restart || {}) as Record<string, unknown>
  const probeReason = String(restart.probe_reason || '').trim()
  const listenerCount = Number(restart.probe_listener_count || 0)
  if (!probeReason) return base
  const suffix = listenerCount > 0 ? `，probe=${probeReason}，listeners=${listenerCount}` : `，probe=${probeReason}`
  return `${base}${suffix}`
}

export function MessageBubble({ message, isThinking = false, thinkingText, compact = false, viewportWidth, onQuickPrompt }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const compactMaxWidth = calculateCompactMaxWidth(viewportWidth)
  const stickerSrc = !isUser ? resolveExpressionSticker(message.expression) : ''
  const stickerLabel = message.expression ? (EXPRESSION_LABELS[message.expression] ?? 'Aelin 表情') : 'Aelin 表情'
  const qc = useQueryClient()
  const confirmTrack = useMutation({
    mutationFn: async (action: AelinAction) => {
      const body = buildTrackConfirmBody(action, message.content)
      if (!body) {
        throw new Error('缺少可追踪目标')
      }
      return aelinApi.trackConfirm(body)
    },
    onSuccess: (res) => {
      toast.success(String(res.message || '已创建追踪'))
      qc.invalidateQueries({ queryKey: ['tracking'] })
      qc.invalidateQueries({ queryKey: ['desk-tracking-list'] })
    },
    onError: (error: any) => {
      toast.error(String(error?.message || '追踪创建失败'))
    },
  })

  const isTrackAction = (action: AelinAction) => {
    const kind = String(action.kind || '').trim().toLowerCase()
    return kind === 'confirm_track' || kind === 'track_topic'
  }
  const isBrowserConfirmAction = (action: AelinAction) => String(action.kind || '').trim().toLowerCase() === 'confirm_browser_action'

  const confirmBrowser = useMutation({
    mutationFn: async (action: AelinAction) => {
      const payload = action.payload || {}
      const rawNextCall = String(payload.next_call || '').trim()
      let nextCall: Record<string, unknown> = {}
      let resumeRequest: Record<string, unknown> = {}
      if (rawNextCall) {
        try {
          const parsed = JSON.parse(rawNextCall)
          if (!parsed || typeof parsed !== 'object') throw new Error('invalid_next_call')
          nextCall = parsed as Record<string, unknown>
        } catch {
          throw new Error('next_call 解析失败')
        }
      }
      const rawResumeRequest = String(payload.resume_request || '').trim()
      if (rawResumeRequest) {
        try {
          const parsedResume = JSON.parse(rawResumeRequest)
          if (parsedResume && typeof parsedResume === 'object') {
            resumeRequest = parsedResume as Record<string, unknown>
          }
        } catch {
          throw new Error('resume_request 解析失败')
        }
      }
      const loginRequestId = String(payload.login_request_id || '').trim()
      if (!rawNextCall && !loginRequestId) {
        throw new Error('缺少 next_call 或 login_request_id 参数')
      }
      const rawContinueAfterConfirm = String(payload.continue_after_confirm || '').trim().toLowerCase()
      const continueAfterConfirm = rawContinueAfterConfirm
        ? rawContinueAfterConfirm !== 'false' && rawContinueAfterConfirm !== '0' && rawContinueAfterConfirm !== 'no'
        : true
      const body = {
        workspace: String(payload.workspace || 'default').trim() || 'default',
        action_kind: String(action.kind || '').trim() || 'confirm_browser_action',
        action: String(payload.action || '').trim(),
        profile_id: String(payload.profile_id || '').trim(),
        login_request_id: loginRequestId,
        resume_request: resumeRequest,
        resume_query: String(payload.resume_query || '').trim(),
        continue_after_confirm: continueAfterConfirm,
        ...(rawNextCall ? { next_call: nextCall } : {}),
      }
      return aelinApi.confirmBrowserAction(body)
    },
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(String(res.message || '已确认并继续执行'))
        const followup = (res.followup_result || {}) as Record<string, unknown>
        const followupAnswer = String(followup.answer || '').trim()
        if (res.continued && followupAnswer) {
          const store = useChatStore.getState()
          const sessionId = store.activeSessionId
          if (sessionId) {
            store.addMessage(sessionId, {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: followupAnswer,
              expression: String(followup.expression || '').trim() || undefined,
              citations: Array.isArray(followup.citations) ? (followup.citations as any[]) : undefined,
              actions: Array.isArray(followup.actions) ? (followup.actions as any[]) : undefined,
              toolTrace: Array.isArray(followup.tool_trace) ? (followup.tool_trace as any[]) : undefined,
              memorySummary: String(followup.memory_summary || '').trim() || undefined,
              timestamp: Date.now(),
            })
          }
        } else if (onQuickPrompt) {
          onQuickPrompt('我已确认，请继续完成刚才的浏览器任务并直接给我结果。')
        }
      } else {
        toast.error(formatBrowserConfirmFeedback(res))
      }
    },
    onError: (error: any) => {
      toast.error(String(error?.message || '确认后执行失败'))
    },
  })

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

        {message.actions && message.actions.length > 0 && (
          <details className="group mt-3.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-2">
            <summary className="cursor-pointer text-[11px] text-[var(--color-text-muted)] font-semibold uppercase tracking-wide">
              建议动作 ({message.actions.length})
            </summary>
            <div className="grid grid-rows-[0fr] transition-[grid-template-rows] duration-300 ease-out group-open:grid-rows-[1fr]">
              <div className="overflow-hidden">
                <div className="mt-2 space-y-1.5 opacity-0 translate-y-1 transition-all duration-300 ease-out group-open:translate-y-0 group-open:opacity-100">
                  {message.actions.map((action, i) => {
                    const href = resolveActionHref(action)
                    const detail = String(action.detail || '').trim()
                    const key = `${String(action.kind || 'action')}-${i}`
                    if (isTrackAction(action)) {
                      return (
                        <div key={key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-2">
                          <div className="text-[11px] font-medium text-[var(--color-text)]">{action.title}</div>
                          {detail ? <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">{detail}</div> : null}
                          <button
                            className="aelin-btn mt-2 h-7 px-2 text-[11px]"
                            onClick={() => confirmTrack.mutate(action)}
                            disabled={confirmTrack.isPending}
                          >
                            {confirmTrack.isPending ? '处理中…' : '执行'}
                          </button>
                        </div>
                      )
                    }
                    if (isBrowserConfirmAction(action)) {
                      return (
                        <div key={key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-2">
                          <div className="text-[11px] font-medium text-[var(--color-text)]">{action.title}</div>
                          {detail ? <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">{detail}</div> : null}
                          <button
                            className="aelin-btn mt-2 h-7 px-2 text-[11px]"
                            onClick={() => confirmBrowser.mutate(action)}
                            disabled={confirmBrowser.isPending}
                          >
                            {confirmBrowser.isPending ? '处理中…' : '确认并继续'}
                          </button>
                        </div>
                      )
                    }
                    return (
                      <div key={key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-2">
                        <div className="text-[11px] font-medium text-[var(--color-text)]">{action.title}</div>
                        {detail ? <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">{detail}</div> : null}
                        {href ? (
                          <a className="aelin-btn mt-2 inline-flex h-7 items-center px-2 text-[11px]" href={href}>
                            打开
                          </a>
                        ) : null}
                      </div>
                    )
                  })}
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
