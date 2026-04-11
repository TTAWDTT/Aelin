import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type StorageMap = Map<string, string>

function createStorageStub(seed?: Record<string, string>) {
  const store: StorageMap = new Map(Object.entries(seed || {}))
  return {
    getItem: vi.fn((key: string) => (store.has(key) ? store.get(key) ?? null : null)),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, String(value))
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
    }),
    clear: vi.fn(() => {
      store.clear()
    }),
    key: vi.fn((index: number) => Array.from(store.keys())[index] ?? null),
    get length() {
      return store.size
    },
    dump: () => Object.fromEntries(store.entries()),
  }
}

async function loadModule() {
  return import('./chatHistoryStorage')
}

describe('chatHistoryStorage', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('migrates legacy v2 payloads into per-session storage lazily', async () => {
    const localStorage = createStorageStub({
      'aelin-chat-history-v2': JSON.stringify({
        'session-1': [
          {
            id: 'm1',
            role: 'assistant',
            content: 'persisted answer',
            timestamp: 1,
          },
        ],
      }),
    })
    vi.stubGlobal('window', { localStorage })

    const { getSessionMessages } = await loadModule()
    const messages = getSessionMessages('session-1')

    expect(messages).toHaveLength(1)
    expect(messages[0]?.content).toBe('persisted answer')
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'aelin-chat-history-session-v3:session-1',
      expect.any(String),
    )
    expect(localStorage.removeItem).toHaveBeenCalledWith('aelin-chat-history-v2')
  })

  it('writes and deletes only the targeted session entry', async () => {
    const localStorage = createStorageStub()
    vi.stubGlobal('window', { localStorage })

    const { getSessionMessages, setSessionMessages, deleteSessionMessages } = await loadModule()

    setSessionMessages('session-2', [
      {
        id: 'm2',
        role: 'user',
        content: 'hello',
        timestamp: 2,
      },
    ])

    expect(getSessionMessages('session-2')).toEqual([
      expect.objectContaining({ id: 'm2', content: 'hello' }),
    ])
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'aelin-chat-history-session-v3:session-2',
      expect.any(String),
    )
    expect(localStorage.dump()).not.toHaveProperty('aelin-chat-history-v2')

    deleteSessionMessages('session-2')

    expect(getSessionMessages('session-2')).toEqual([])
    expect(localStorage.removeItem).toHaveBeenCalledWith('aelin-chat-history-session-v3:session-2')
  })
})
