import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { CHAT_EMPTY_GREETING, CHAT_EMPTY_TITLE, CHAT_QUICK_PROMPTS } from '../constants'

interface EmptyChatStateProps {
  onQuickPrompt: (text: string) => void
}

export function EmptyChatState({ onQuickPrompt }: EmptyChatStateProps) {
  return (
    <div className="flex min-h-full items-center justify-center py-8">
      <div className="aelin-fade-up w-full max-w-[1040px]">
        <div className="mx-auto max-w-[760px] rounded-[18px] border border-[var(--color-border)] bg-[var(--color-panel)] p-6">
          <div className="mb-3 flex items-center gap-3 text-[var(--color-text-muted)]">
            <AelinAvatar size="md" className="!rounded-[10px]" />
            <span className="text-xs">{CHAT_EMPTY_GREETING}</span>
          </div>
          <h1 className="mb-2 text-2xl font-semibold tracking-tight text-[var(--color-text)]" style={{ fontFamily: 'var(--font-heading)' }}>
            {CHAT_EMPTY_TITLE}
          </h1>
          <p className="mb-5 text-sm text-[var(--color-text-muted)]">输入消息后，Aelin 会继续在底部输入框中保持会话。</p>
          <div className="flex flex-wrap gap-2">
            {CHAT_QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                onClick={() => onQuickPrompt(prompt)}
                className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
