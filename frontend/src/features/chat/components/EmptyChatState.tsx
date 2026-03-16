import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { CHAT_EMPTY_QUICK_PROMPTS_ZH, CHAT_EMPTY_QUICK_PROMPTS_EN } from '../constants'
import { useLocaleStore } from '@/shared/stores/localeStore'

interface EmptyChatStateProps {
  onQuickPrompt: (text: string) => void
}

export function EmptyChatState({ onQuickPrompt }: EmptyChatStateProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const greeting = isZh ? '你好，欢迎回来' : 'Hi, welcome back'
  const title = isZh ? '需要我为你做些什么？' : 'What can I help you with today?'
  const description = isZh
    ? '输入消息后，Aelin 会继续在底部输入框中保持会话。'
    : 'Once you send a message, Aelin will keep the conversation going in the bottom input bar.'
  const quickPrompts = isZh ? CHAT_EMPTY_QUICK_PROMPTS_ZH : CHAT_EMPTY_QUICK_PROMPTS_EN

  return (
    <div className="flex min-h-full items-center justify-center py-4 sm:py-8">
      <div className="aelin-fade-up min-w-0 w-full max-w-[1040px]">
        <div className="mx-auto min-w-0 max-w-[760px] rounded-[18px] border border-[var(--color-border)] bg-[var(--color-panel)] p-4 sm:p-6 max-[500px]:rounded-[14px] max-[500px]:p-3">
          <div className="mb-3 flex min-w-0 items-center gap-2.5 text-[var(--color-text-muted)] sm:gap-3">
            <AelinAvatar size="md" className="!rounded-[10px]" />
            <span className="truncate text-xs">{greeting}</span>
          </div>
          <h1 className="mb-2 break-words text-xl font-semibold tracking-tight text-[var(--color-text)] sm:text-2xl max-[500px]:text-lg" style={{ fontFamily: 'var(--font-heading)' }}>
            {title}
          </h1>
          <p className="mb-4 break-words text-[13px] text-[var(--color-text-muted)] sm:mb-5 sm:text-sm max-[500px]:text-[12px]">
            {description}
          </p>
          <div className="flex flex-wrap gap-2">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => onQuickPrompt(prompt)}
                className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-1.5 text-[11px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] sm:px-3 sm:text-xs"
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
