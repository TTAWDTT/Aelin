import { useLocaleStore } from '@/shared/stores/localeStore'

interface ChatStatusBarProps {
  isStreaming: boolean
  statusText: string
  compact?: boolean
}

export function ChatStatusBar({ isStreaming, statusText, compact = false }: ChatStatusBarProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'

  if (!isStreaming && !statusText) return null

  const fallback = isZh ? '正在生成…' : 'Generating…'

  return (
    <div
      className={`mx-auto flex w-full max-w-[880px] items-center gap-2 text-[var(--color-text-muted)] ${
        compact ? 'px-0.5 py-1.5 text-[11px]' : 'px-1 py-2 text-xs'
      }`}
    >
      <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-text)] animate-pulse" />
      <span className="min-w-0 flex-1 truncate" title={statusText || fallback}>
        {statusText || fallback}
      </span>
    </div>
  )
}
