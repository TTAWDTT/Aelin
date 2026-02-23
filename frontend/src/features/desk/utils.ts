import type { DeskFeedItem } from '@/shared/api/types'
import { SOURCE_OPTIONS, isKnownDeskSource } from './constants'
import type { ChangePreview, TrackingChangeRow } from './types'

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

export function firstHttpUrl(text: string | null | undefined): string {
  const value = String(text || '').trim()
  if (!value) return ''
  const match = value.match(/https?:\/\/[^\s<>"')\]]+/i)
  return normalizeUrl(match?.[0] || '')
}

export function trackingStatusLabel(value: string) {
  if (value === 'active') return '活跃'
  if (value === 'paused') return '暂停'
  if (value === 'error') return '异常'
  return value || 'unknown'
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

export function extractChangePreview(change: TrackingChangeRow, feedItems: DeskFeedItem[]): ChangePreview {
  const diff = (change.diff_json || {}) as Record<string, any>
  const added = (diff.added || {}) as Record<string, any>
  const updated = (diff.updated || {}) as Record<string, any>

  const byDiff = [
    normalizeUrl(added.url),
    normalizeUrl(updated.url),
    normalizeUrl(diff.url),
    normalizeUrl(diff.link),
    firstHttpUrl(change.summary),
    firstHttpUrl(change.title),
  ].find(Boolean) || ''

  const diffTitle =
    String(added.title || '').trim()
    || String(updated.title || '').trim()
    || String(change.summary || '').trim()
    || String(change.title || '').trim()
    || '内容更新'

  let imageUrl = ''
  if (byDiff) {
    const exact = feedItems.find((item) => normalizeUrl(item.external_url) === byDiff)
    if (exact?.image_url) imageUrl = exact.image_url
  }
  if (!imageUrl) {
    const hint = diffTitle.toLowerCase().slice(0, 18)
    if (hint) {
      const fuzzy = feedItems.find((item) => {
        const title = String(item.title || '').toLowerCase()
        return title.includes(hint)
      })
      if (fuzzy?.image_url) imageUrl = fuzzy.image_url
    }
  }

  return {
    title: diffTitle,
    url: byDiff,
    imageUrl: imageUrl || '',
  }
}

export function toUnixTs(value: string | undefined) {
  const parsed = Date.parse(String(value || ''))
  return Number.isFinite(parsed) ? parsed : 0
}
