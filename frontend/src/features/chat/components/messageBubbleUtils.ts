import type {
  ChatAction,
} from '@/shared/api/types'

export const EXPRESSION_LABELS: Record<string, string> = {
  'exp-02': '热情出击',
  'exp-03': '温柔赞同',
  'exp-04': '托腮思考',
  'exp-05': '轻声提醒',
  'exp-06': '偷看观察',
  'exp-07': '低落求助',
  'exp-08': '不满委屈',
  'exp-09': '指着大笑',
  'exp-10': '发财得意',
  'exp-11': '趴桌躺平',
}

export function resolveExpressionSticker(expression?: string) {
  const exp = String(expression || '').trim().toLowerCase()
  if (/^exp-(0[2-9]|1[0-1])$/.test(exp)) return `/expressions/${exp}.png`
  return ''
}

export function calculateCompactMaxWidth(viewportWidth: number) {
  const width = Number.isFinite(viewportWidth) ? viewportWidth : 960
  return Math.max(220, Math.floor(width * 0.72))
}

export function formatMessageTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function resolveActionHref(action: ChatAction): string {
  const kind = String(action.kind || '').trim().toLowerCase()
  const payload = action.payload || {}

  if (kind === 'open_settings') {
    return String(payload.path || '').trim() || '/settings'
  }
  return ''
}

export function isBrowserConfirmAction(action: ChatAction) {
  return String(action.kind || '').trim().toLowerCase() === 'confirm_browser_action'
}
