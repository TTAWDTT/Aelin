import { useState } from 'react'
import { cn } from '@/shared/utils/cn'

const SIZE_STYLES = {
  sm: 'h-8 w-8 text-[11px]',
  md: 'h-10 w-10 text-xs',
  lg: 'h-14 w-14 text-sm',
} as const

const AELIN_ICON_SRC = '/aelin-icon.ico'

const EXPRESSION_GLYPHS: Record<string, string> = {
  'exp-01': '✦',
  'exp-02': '✧',
  'exp-03': '♡',
  'exp-04': '◌',
  'exp-05': '◍',
  'exp-06': '◔',
  'exp-07': '·',
  'exp-08': '•',
  'exp-09': '✶',
  'exp-10': '◆',
  'exp-11': '○',
}

interface AelinAvatarProps {
  size?: keyof typeof SIZE_STYLES
  expression?: string
  className?: string
  title?: string
  pulse?: boolean
}

export function AelinAvatar({ size = 'md', expression, className, title, pulse = false }: AelinAvatarProps) {
  const [iconFailed, setIconFailed] = useState(false)
  const glyph = expression ? (EXPRESSION_GLYPHS[expression] ?? 'A') : 'A'

  return (
    <span
      className={cn('aelin-avatar', SIZE_STYLES[size], pulse && 'aelin-avatar-pulse', className)}
      title={title}
      aria-hidden="true"
    >
      <span className="aelin-avatar-inner">
        {iconFailed ? (
          <span className="aelin-avatar-fallback">{glyph}</span>
        ) : (
          <img
            src={AELIN_ICON_SRC}
            alt=""
            className="aelin-avatar-img"
            draggable={false}
            onError={() => setIconFailed(true)}
          />
        )}
      </span>
    </span>
  )
}
