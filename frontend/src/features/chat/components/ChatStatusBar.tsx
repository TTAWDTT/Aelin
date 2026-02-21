interface ChatStatusBarProps {
  isStreaming: boolean
  statusText: string
}

export function ChatStatusBar({ isStreaming, statusText }: ChatStatusBarProps) {
  if (!isStreaming && !statusText) return null

  return (
    <div className="mx-auto flex w-full max-w-[760px] items-center gap-2 px-1 py-2 text-xs text-[var(--color-text-muted)]">
      <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-text)] animate-pulse" />
        <span>{statusText || '正在生成…'}</span>
    </div>
  )
}
