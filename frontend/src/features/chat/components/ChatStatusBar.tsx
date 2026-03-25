import { PanelRightOpen } from 'lucide-react'
import type { ChatRuntimeStream } from '../executionStreamUtils'
import {
  getExecutionSubagents,
  getExecutionToolCalls,
  hasExecutionData,
  summarizeExecutionStatus,
} from '../executionStreamUtils'
import { useChatI18n } from '../chatI18n'
import { useExecutionPaneStore } from '../stores/executionPaneStore'

interface ChatStatusBarProps {
  isStreaming: boolean
  statusText: string
  compact?: boolean
  stream: ChatRuntimeStream
  onOpenExecution?: () => void
}

export function ChatStatusBar({
  isStreaming,
  statusText,
  compact = false,
  stream,
  onOpenExecution,
}: ChatStatusBarProps) {
  const { t, locale } = useChatI18n()
  const { open, setOpen, setSuppressAutoOpen } = useExecutionPaneStore()
  const tools = getExecutionToolCalls(stream)
  const subagents = getExecutionSubagents(stream)
  const hasRuns = hasExecutionData(stream)

  if (!isStreaming && !statusText && !hasRuns) return null

  const toolNames = Array.from(new Set(tools.map((call) => call.name).filter(Boolean)))
  const joinedTools = toolNames.slice(0, 4).join(' · ')
  const fallback = t('timeline.generating')

  let text = statusText.trim() || summarizeExecutionStatus(stream, '')
  if (!text && isStreaming && subagents.length > 0) {
    text =
      locale === 'zh'
        ? `正在运行 ${subagents.length} 个子代理…`
        : `Running ${subagents.length} subagent(s)…`
  } else if (!text && isStreaming && joinedTools) {
    text = t('status.tools.invoking', { tools: joinedTools })
  } else if (!text && !isStreaming && hasRuns && joinedTools) {
    text = t('status.tools.summary', {
      count: tools.length || 1,
      tools: joinedTools,
    })
  }

  const displayText = text || fallback

  return (
    <div
      className={`mx-auto flex w-full max-w-[880px] items-center gap-2 text-[var(--color-text-muted)] ${
        compact ? 'px-0.5 py-1.5 text-[11px]' : 'px-1 py-2 text-xs'
      }`}
    >
      <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-text)]" />
      <span className="min-w-0 flex-1 truncate" title={displayText}>
        {displayText}
      </span>
      {hasRuns && onOpenExecution && (
        <button
          type="button"
          onClick={() => {
            if (open) {
              setOpen(false)
              setSuppressAutoOpen(true)
            } else {
              setSuppressAutoOpen(false)
              onOpenExecution()
            }
          }}
          aria-label={t('trace.executionPane.headerOpen')}
          className="ml-1 aelin-rail-control h-8 w-8"
        >
          <PanelRightOpen size={12} />
        </button>
      )}
    </div>
  )
}
