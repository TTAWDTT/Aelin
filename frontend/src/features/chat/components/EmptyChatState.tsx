import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { ComposerBar } from './ComposerBar'
import { CHAT_EMPTY_GREETING, CHAT_EMPTY_TITLE, CHAT_QUICK_PROMPTS } from '../constants'

interface EmptyChatStateProps {
  onSend: (text: string, images?: { dataUrl: string; name: string }[]) => void
  onStop: () => void
  isStreaming: boolean
  searchMode: 'auto' | 'local' | 'web'
  onSearchModeChange: (v: 'auto' | 'local' | 'web') => void
}

export function EmptyChatState({
  onSend,
  onStop,
  isStreaming,
  searchMode,
  onSearchModeChange,
}: EmptyChatStateProps) {
  return (
    <div className="flex flex-1 items-center justify-center px-4 py-10 sm:px-6">
      <div className="aelin-fade-up w-full max-w-[820px]">
        <div className="mb-5 flex items-center gap-3 text-[var(--color-text-muted)]">
          <AelinAvatar size="md" />
          <span className="text-sm">{CHAT_EMPTY_GREETING}</span>
        </div>
        <h1 className="mb-7 text-4xl font-semibold tracking-tight text-[var(--color-text)] sm:text-5xl" style={{ fontFamily: 'var(--font-heading)' }}>
          {CHAT_EMPTY_TITLE}
        </h1>

        <ComposerBar
          variant="hero"
          placeholder="问问 Aelin..."
          onSend={onSend}
          onStop={onStop}
          isStreaming={isStreaming}
          searchMode={searchMode}
          onSearchModeChange={onSearchModeChange}
        />

        <div className="mt-5 flex flex-wrap gap-2.5">
          {CHAT_QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => onSend(prompt)}
              className="rounded-full bg-[var(--color-accent-soft)] px-4 py-2 text-sm text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-text)] hover:text-[var(--color-bg)]"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
