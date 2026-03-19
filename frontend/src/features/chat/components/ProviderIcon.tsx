import { cn } from '@/shared/utils/cn'
import { Plane as PlaneIcon, Globe2, Monitor, Sparkles, Circle } from 'lucide-react'

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
  const baseSize = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'
  const iconSize = size === 'sm' ? 11 : 13

  let Icon: React.ComponentType<{ size?: number }>
  switch (kind) {
    case 'google':
      Icon = Sparkles
      break
    case 'plane':
      Icon = PlaneIcon
      break
    case 'device':
      Icon = Monitor
      break
    case 'web':
      Icon = Globe2
      break
    default:
      Icon = Circle
      break
  }

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-[var(--color-text)]',
        baseSize,
        className,
      )}
      aria-hidden="true"
    >
      <Icon size={iconSize} />
    </span>
  )
}
