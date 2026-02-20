import { formatDistanceToNow, parseISO } from 'date-fns'
import { zhCN } from 'date-fns/locale'

export function relativeTime(iso?: string | null): string {
  if (!iso) return ''
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: zhCN })
  } catch { return iso }
}

export function sourceIcon(source?: string): string {
  const map: Record<string, string> = {
    gmail: '✉️', outlook: '📧', imap: '📬', forward: '📨',
    bilibili: '📺', x: '🐦', github: '🐙', rss: '📡',
    douyin: '🎵', xiaohongshu: '📕', weibo: '🌐',
    web: '🌍', mock: '🧪',
  }
  return map[source?.toLowerCase() || ''] || '📄'
}

export function severityColor(severity: string): string {
  switch (severity) {
    case 'high': case 'critical': return 'text-[var(--color-danger)]'
    case 'medium': return 'text-[var(--color-warning)]'
    default: return 'text-[var(--color-green)]'
  }
}
