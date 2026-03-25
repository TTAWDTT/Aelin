import type {
  ChatAction,
  AelinBrowserConfirmRequest,
  AelinBrowserConfirmResponse,
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

export function buildBrowserConfirmBody(action: ChatAction): AelinBrowserConfirmRequest {
  const payload = action.payload || {}
  const rawNextCall = String(payload.next_call || '').trim()
  let nextCall: Record<string, unknown> | undefined

  if (rawNextCall) {
    try {
      const parsed = JSON.parse(rawNextCall)
      if (!parsed || typeof parsed !== 'object') throw new Error('invalid_next_call')
      nextCall = parsed as Record<string, unknown>
    } catch {
      throw new Error('next_call 解析失败')
    }
  }

  const loginRequestId = String(payload.login_request_id || '').trim()
  if (!nextCall && !loginRequestId) {
    throw new Error('缺少 next_call 或 login_request_id 参数')
  }

  const rawContinueAfterConfirm = String(payload.continue_after_confirm || '').trim().toLowerCase()
  const continueAfterConfirm = rawContinueAfterConfirm
    ? rawContinueAfterConfirm !== 'false' && rawContinueAfterConfirm !== '0' && rawContinueAfterConfirm !== 'no'
    : true

  return {
    workspace: String(payload.workspace || 'default').trim() || 'default',
    action_kind: String(action.kind || '').trim() || 'confirm_browser_action',
    action: String(payload.action || '').trim(),
    profile_id: String(payload.profile_id || '').trim(),
    login_request_id: loginRequestId || undefined,
    resume_query: String(payload.resume_query || '').trim() || undefined,
    continue_after_confirm: continueAfterConfirm,
    next_call: nextCall,
  }
}

export function formatBrowserConfirmFeedback(res: Pick<AelinBrowserConfirmResponse, 'message' | 'tool_result'>) {
  const base = String(res.message || '确认后执行失败').trim()
  const toolResult = (res.tool_result || {}) as Record<string, unknown>
  const restart = (toolResult.restart || {}) as Record<string, unknown>
  const probeReason = String(restart.probe_reason || '').trim()
  const listenerCount = Number(restart.probe_listener_count || 0)
  if (!probeReason) return base
  const suffix = listenerCount > 0 ? `，probe=${probeReason}，listeners=${listenerCount}` : `，probe=${probeReason}`
  return `${base}${suffix}`
}
