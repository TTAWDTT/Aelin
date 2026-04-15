import { beforeEach, describe, expect, it } from 'vitest'
import {
  deleteSessionMessages,
  getSessionMessages,
  setSessionMessages,
} from './chatHistoryStorage'
import type { ChatMessage } from './chatTypes'

const LEGACY_STORAGE_KEY = 'aelin-chat-history-v2'
const SESSION_INDEX_KEY = 'aelin-chat-history-session-index-v3'
const SESSION_KEY_PREFIX = 'aelin-chat-history-session-v3'

function installLocalStorageMock() {
  const store = new Map<string, string>()
  const localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
    clear: () => {
      store.clear()
    },
  }

  Object.defineProperty(globalThis, 'window', {
    value: { localStorage },
    configurable: true,
    writable: true,
  })
  Object.defineProperty(globalThis, 'localStorage', {
    value: localStorage,
    configurable: true,
    writable: true,
  })

  return { store, localStorage }
}

const demoMessages: ChatMessage[] = [
  {
    id: 'assistant-1',
    role: 'assistant',
    content: 'hello',
    timestamp: 1,
  },
]

describe('chatHistoryStorage', () => {
  beforeEach(() => {
    installLocalStorageMock().localStorage.clear()
  })

  it('stores each session under its own key and tracks the session index', () => {
    setSessionMessages('session-a', demoMessages)

    expect(getSessionMessages('session-a')).toEqual(demoMessages)
    expect(globalThis.localStorage.getItem(`${SESSION_KEY_PREFIX}:session-a`)).toBeTruthy()
    expect(globalThis.localStorage.getItem(SESSION_INDEX_KEY)).toBe(JSON.stringify(['session-a']))
  })

  it('migrates a legacy v2 session on first read', () => {
    globalThis.localStorage.setItem(
      LEGACY_STORAGE_KEY,
      JSON.stringify({
        'legacy-session': demoMessages,
      }),
    )

    expect(getSessionMessages('legacy-session')).toEqual(demoMessages)
    expect(globalThis.localStorage.getItem(`${SESSION_KEY_PREFIX}:legacy-session`)).toBeTruthy()
    expect(globalThis.localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull()
    expect(globalThis.localStorage.getItem(SESSION_INDEX_KEY)).toBe(JSON.stringify(['legacy-session']))
  })

  it('deletes both the per-session key and the index entry', () => {
    setSessionMessages('session-b', demoMessages)

    deleteSessionMessages('session-b')

    expect(getSessionMessages('session-b')).toEqual([])
    expect(globalThis.localStorage.getItem(`${SESSION_KEY_PREFIX}:session-b`)).toBeNull()
    expect(globalThis.localStorage.getItem(SESSION_INDEX_KEY)).toBeNull()
  })
})
