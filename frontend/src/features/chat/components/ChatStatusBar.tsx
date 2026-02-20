interface ChatStatusBarProps {
  isStreaming: boolean
  statusText: string
}

export function ChatStatusBar({ isStreaming, statusText }: ChatStatusBarProps) {
  if (!isStreaming && !statusText) return null

  return (
    <div className="border-b border-[var(--color-border)] bg-[var(--color-panel)]">
      <div className="mx-auto flex w-full max-w-4xl items-center gap-2 px-4 py-1.5 text-xs text-[var(--color-text-muted)]">
        <div className="h-2 w-2 rounded-full bg-[var(--color-text)] animate-pulse" />
        <span>{statusText || '正在生成…'}</span>
      </div>
    </div>
  )
}
