import type { ChatMessage } from './chatTypes'

const STORAGE_KEY = 'aelin-chat-history-v2'

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function readAll(): Record<string, ChatMessage[]> {
  if (!canUseStorage()) return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, ChatMessage[]>
      : {}
  } catch {
    return {}
  }
}

function writeAll(value: Record<string, ChatMessage[]>) {
  if (!canUseStorage()) return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Ignore quota / privacy mode failures and keep the in-memory stream working.
  }
}

export function getSessionMessages(sessionId: string | null | undefined): ChatMessage[] {
  const id = String(sessionId || '').trim()
  if (!id) return []
  return readAll()[id] ?? []
}

export function setSessionMessages(sessionId: string | null | undefined, messages: ChatMessage[]) {
  const id = String(sessionId || '').trim()
  if (!id) return
  const next = readAll()
  next[id] = Array.isArray(messages) ? messages : []
  writeAll(next)
}

export function deleteSessionMessages(sessionId: string | null | undefined) {
  const id = String(sessionId || '').trim()
  if (!id) return
  const next = readAll()
  if (!(id in next)) return
  delete next[id]
  writeAll(next)
}
