export const SOURCE_OPTIONS: Array<{ key: string; label: string }> = [
  { key: '', label: '全部来源' },
  { key: 'x', label: 'X' },
  { key: 'weibo', label: '微博' },
  { key: 'xiaohongshu', label: '小红书' },
  { key: 'douyin', label: '抖音' },
  { key: 'bilibili', label: 'Bilibili' },
  { key: 'rss', label: 'RSS' },
  { key: 'web', label: 'Web' },
]

export const TRACKING_STATUS_OPTIONS = ['all', 'active', 'paused', 'error'] as const

const SOURCE_SET = new Set(SOURCE_OPTIONS.map((item) => item.key).filter(Boolean))

export function isKnownDeskSource(source: string) {
  return SOURCE_SET.has(source)
}
