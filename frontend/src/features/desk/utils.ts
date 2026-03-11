import { SOURCE_OPTIONS, isKnownDeskSource } from './constants'

export function normalizeSource(raw: string | null | undefined): string {
  const value = String(raw || '').trim().toLowerCase()
  if (!value) return ''
  if (isKnownDeskSource(value)) return value
  if (value === 'xhs') return 'xiaohongshu'
  if (value === 'news' || value === 'website') return 'web'
  return ''
}

export function normalizeUrl(raw: string | null | undefined): string {
  const text = String(raw || '').trim()
  if (!text) return ''
  try {
    return new URL(text).toString()
  } catch {
    return ''
  }
}

export function sourceLabel(sourceKey: string) {
  if (!sourceKey) return '全部来源'
  return SOURCE_OPTIONS.find((item) => item.key === sourceKey)?.label || sourceKey
}

export function filterChipClass(selected: boolean) {
  if (selected) {
    return 'rounded-full border border-[var(--color-accent)] bg-[var(--color-accent)] px-2.5 py-1 text-[11px] text-[var(--color-bg)]'
  }
  return 'rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[11px] text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
}
