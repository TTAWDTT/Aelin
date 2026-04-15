import type { ExecutionToolCall } from './executionStreamUtils'

const SESSION_TOOL_CALLS_KEY_PREFIX = 'aelin-chat-execution-tools-v1'

const sessionToolCallsCache = new Map<string, Map<string, ExecutionToolCall[]>>()

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function normalizeSessionId(sessionId: string | null | undefined): string {
  return String(sessionId || '').trim()
}

function storageKey(sessionId: string): string {
  return `${SESSION_TOOL_CALLS_KEY_PREFIX}:${sessionId}`
}

function cloneToolCallsByMessage(
  value: Map<string, ExecutionToolCall[]>,
): Map<string, ExecutionToolCall[]> {
  return new Map(
    Array.from(value.entries()).map(([messageId, toolCalls]) => [messageId, Array.from(toolCalls || [])]),
  )
}

function parseToolCallsByMessage(raw: string | null): Map<string, ExecutionToolCall[]> {
  if (!raw) return new Map()
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return new Map()
    const map = new Map<string, ExecutionToolCall[]>()
    Object.entries(parsed).forEach(([messageId, toolCalls]) => {
      if (!Array.isArray(toolCalls)) return
      map.set(String(messageId || '').trim(), toolCalls as ExecutionToolCall[])
    })
    return map
  } catch {
    return new Map()
  }
}

export function getSessionToolCalls(sessionId: string | null | undefined): Map<string, ExecutionToolCall[]> {
  const id = normalizeSessionId(sessionId)
  if (!id) return new Map()

  const cached = sessionToolCallsCache.get(id)
  if (cached) return cloneToolCallsByMessage(cached)
  if (!canUseStorage()) return new Map()

  const parsed = parseToolCallsByMessage(window.localStorage.getItem(storageKey(id)))
  sessionToolCallsCache.set(id, parsed)
  return cloneToolCallsByMessage(parsed)
}

export function setSessionToolCalls(
  sessionId: string | null | undefined,
  value: Map<string, ExecutionToolCall[]>,
): void {
  const id = normalizeSessionId(sessionId)
  if (!id) return

  const normalized = cloneToolCallsByMessage(value)
  sessionToolCallsCache.set(id, normalized)
  if (!canUseStorage()) return

  try {
    const payload = Object.fromEntries(normalized)
    if (Object.keys(payload).length === 0) {
      window.localStorage.removeItem(storageKey(id))
      return
    }
    window.localStorage.setItem(storageKey(id), JSON.stringify(payload))
  } catch {
    // Keep in-memory tool metadata available even when storage writes fail.
  }
}

export function deleteSessionToolCalls(sessionId: string | null | undefined): void {
  const id = normalizeSessionId(sessionId)
  if (!id) return
  sessionToolCallsCache.delete(id)
  if (!canUseStorage()) return
  try {
    window.localStorage.removeItem(storageKey(id))
  } catch {
    // Ignore storage failures during cleanup.
  }
}
