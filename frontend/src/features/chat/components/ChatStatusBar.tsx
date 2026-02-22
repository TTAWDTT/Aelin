interface ChatStatusBarProps {
  isStreaming: boolean
  statusText: string
  compact?: boolean
}

export function ChatStatusBar({ isStreaming, statusText, compact = false }: ChatStatusBarProps) {
  if (!isStreaming && !statusText) return null

  return (
    <div className={`mx-auto flex w-full max-w-[880px] items-center gap-2 text-[var(--color-text-muted)] ${compact ? 'px-0.5 py-1.5 text-[11px]' : 'px-1 py-2 text-xs'}`}>
      <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-text)] animate-pulse" />
        <span>{statusText || '正在生成…'}</span>
    </div>
  )
}
