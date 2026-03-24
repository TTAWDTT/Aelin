import type { DeepAgentsToolRun } from '@/shared/api/types'
import { useChatI18n } from '../chatI18n'
import { extractToolCallsFromToolRuns } from '../traceUtils'
import { PanelRightOpen } from 'lucide-react'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import { ProviderIcon } from './ProviderIcon'

interface ChatStatusBarProps {
  isStreaming: boolean
  statusText: string
  compact?: boolean
  toolRuns?: DeepAgentsToolRun[]
  onOpenExecution?: () => void
}

export function ChatStatusBar({
  isStreaming,
  statusText,
  compact = false,
  toolRuns,
  onOpenExecution,
}: ChatStatusBarProps) {
  const { t } = useChatI18n()
  const { open, setOpen, setFocusedMessageId, setSuppressAutoOpen } = useExecutionPaneStore()

  const hasRuns = !!toolRuns && toolRuns.length > 0
  if (!isStreaming && !statusText && !hasRuns) return null

  const fallback = t('timeline.generating')
  const tools = hasRuns ? extractToolCallsFromToolRuns(toolRuns) : []
  const toolNames = Array.from(new Set(tools.map((call) => call.name || '').filter(Boolean)))
  const joinedTools = toolNames.slice(0, 4).join(' · ')
  const providers = Array.from(new Set(tools.map((call) => call.provider || '').filter(Boolean))).slice(0, 3)

  let text = statusText || ''

  if (!text && isStreaming && joinedTools) {
    text = t('status.tools.invoking', { tools: joinedTools })
  } else if (!text && !isStreaming && hasRuns && joinedTools) {
    const totalCalls = tools.length || 1
    text = t('status.tools.summary', {
      count: totalCalls,
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
      <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-text)] animate-pulse" />
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
              setFocusedMessageId(null)
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
      {hasRuns && providers.length > 0 && (
        <div className="flex items-center gap-1 pl-1">
          {providers.map((p) => (
            <ProviderIcon key={p} provider={p} size="sm" />
          ))}
        </div>
      )}
    </div>
  )
}
