import type { ChatMessage } from './chatTypes'

const LEGACY_STORAGE_KEY = 'aelin-chat-history-v2'
const SESSION_INDEX_KEY = 'aelin-chat-history-session-index-v3'
const SESSION_KEY_PREFIX = 'aelin-chat-history-session-v3'

const sessionCache = new Map<string, ChatMessage[]>()

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function normalizeSessionId(sessionId: string | null | undefined): string {
  return String(sessionId || '').trim()
}

function sessionStorageKey(sessionId: string): string {
  return `${SESSION_KEY_PREFIX}:${sessionId}`
}

function parseMessageArray(raw: string | null): ChatMessage[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed as ChatMessage[] : []
  } catch {
    return []
  }
}

function readLegacyAll(): Record<string, ChatMessage[]> {
  if (!canUseStorage()) return {}
  try {
    const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, ChatMessage[]>
      : {}
  } catch {
    return {}
  }
}

function writeLegacyAll(value: Record<string, ChatMessage[]>) {
  if (!canUseStorage()) return
  try {
    const keys = Object.keys(value)
    if (keys.length === 0) {
      window.localStorage.removeItem(LEGACY_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Keep the in-memory session usable even when storage writes fail.
  }
}

function readSessionIndex(): string[] {
  if (!canUseStorage()) return []
  try {
    const raw = window.localStorage.getItem(SESSION_INDEX_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const seen = new Set<string>()
    const ids: string[] = []
    parsed.forEach((value) => {
      const id = normalizeSessionId(typeof value === 'string' ? value : '')
      if (!id || seen.has(id)) return
      seen.add(id)
      ids.push(id)
    })
    return ids
  } catch {
    return []
  }
}

function writeSessionIndex(sessionIds: string[]) {
  if (!canUseStorage()) return
  try {
    if (sessionIds.length === 0) {
      window.localStorage.removeItem(SESSION_INDEX_KEY)
      return
    }
    window.localStorage.setItem(SESSION_INDEX_KEY, JSON.stringify(sessionIds))
  } catch {
    // Ignore quota/privacy failures.
  }
}

function rememberSessionIndex(sessionId: string) {
  if (!sessionId || !canUseStorage()) return
  const next = readSessionIndex()
  if (next.includes(sessionId)) return
  next.push(sessionId)
  writeSessionIndex(next)
}

function forgetSessionIndex(sessionId: string) {
  if (!sessionId || !canUseStorage()) return
  const next = readSessionIndex().filter((value) => value !== sessionId)
  writeSessionIndex(next)
}

function cacheSessionMessages(sessionId: string, messages: ChatMessage[]): ChatMessage[] {
  const normalized = Array.isArray(messages) ? messages : []
  sessionCache.set(sessionId, normalized)
  return normalized
}

function migrateLegacySession(sessionId: string): ChatMessage[] {
  if (!canUseStorage()) return []
  const legacy = readLegacyAll()
  const messages = Array.isArray(legacy[sessionId]) ? legacy[sessionId] : []
  if (messages.length === 0) return []
  try {
    window.localStorage.setItem(sessionStorageKey(sessionId), JSON.stringify(messages))
    rememberSessionIndex(sessionId)
    delete legacy[sessionId]
    writeLegacyAll(legacy)
  } catch {
    // Best-effort migration only.
  }
  return cacheSessionMessages(sessionId, messages)
}

export function getSessionMessages(sessionId: string | null | undefined): ChatMessage[] {
  const id = normalizeSessionId(sessionId)
  if (!id) return []

  const cached = sessionCache.get(id)
  if (cached) return cached
  if (!canUseStorage()) return []

  const direct = parseMessageArray(window.localStorage.getItem(sessionStorageKey(id)))
  if (direct.length > 0) {
    rememberSessionIndex(id)
    return cacheSessionMessages(id, direct)
  }

  return migrateLegacySession(id)
}

export function setSessionMessages(sessionId: string | null | undefined, messages: ChatMessage[]) {
  const id = normalizeSessionId(sessionId)
  if (!id) return
  const normalized = cacheSessionMessages(id, Array.isArray(messages) ? messages : [])
  if (!canUseStorage()) return

  try {
    window.localStorage.setItem(sessionStorageKey(id), JSON.stringify(normalized))
    rememberSessionIndex(id)
    const legacy = readLegacyAll()
    if (id in legacy) {
      delete legacy[id]
      writeLegacyAll(legacy)
    }
  } catch {
    // Ignore quota / privacy mode failures and keep the in-memory stream working.
  }
}

export function deleteSessionMessages(sessionId: string | null | undefined) {
  const id = normalizeSessionId(sessionId)
  if (!id) return
  sessionCache.delete(id)
  if (!canUseStorage()) return

  try {
    window.localStorage.removeItem(sessionStorageKey(id))
    forgetSessionIndex(id)
    const legacy = readLegacyAll()
    if (id in legacy) {
      delete legacy[id]
      writeLegacyAll(legacy)
    }
  } catch {
    // Ignore storage failures while allowing the active session to keep running.
  }
}
