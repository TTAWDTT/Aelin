import { cn } from '@/shared/utils/cn'

type ProviderKind = 'google' | 'plane' | 'device' | 'web' | 'core'

interface ProviderIconProps {
  provider: string
  className?: string
  size?: 'sm' | 'md'
}

function resolveKind(raw: string): ProviderKind {
  const p = String(raw || '').toLowerCase()
  if (!p) return 'core'
  if (p.includes('google') || p === 'gws') return 'google'
  if (p.includes('plane') || p.includes('pinchtab') || p === 'browser') return 'plane'
  if (p.includes('device') || p.includes('screen')) return 'device'
  if (p.includes('web')) return 'web'
  return 'core'
}

export function ProviderIcon({ provider, className, size = 'md' }: ProviderIconProps) {
  const kind = resolveKind(provider)
  const baseSize = size === 'sm' ? 'h-4 w-4 text-[8px]' : 'h-5 w-5 text-[9px]'

  const emoji =
    kind === 'google'
      ? '🟢'
      : kind === 'plane'
        ? '🛫'
        : kind === 'device'
          ? '💻'
          : kind === 'web'
            ? '🌐'
            : '◇'

  const label =
    kind === 'google'
      ? 'G'
      : kind === 'plane'
        ? 'P'
        : kind === 'device'
          ? 'D'
          : kind === 'web'
            ? 'W'
            : 'A'

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] uppercase tracking-wide text-[var(--color-text)]',
        baseSize,
        className,
      )}
      aria-hidden="true"
    >
      <span className="leading-none">{emoji}</span>
      <span className="ml-0.5 leading-none">{label}</span>
    </span>
  )
}
