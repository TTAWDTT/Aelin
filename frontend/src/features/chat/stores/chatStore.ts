import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useLocaleStore } from '@/shared/stores/localeStore'
import { deleteSessionToolCalls } from '../chatExecutionStorage'
import { deleteSessionMessages } from '../chatHistoryStorage'

export interface ChatSession {
  id: string
  title: string
  createdAt: number
  workspace: string
}

export type ChatSessionPhase = 'idle' | 'streaming' | 'background'

export interface ChatSessionRuntime {
  phase: ChatSessionPhase
  statusText: string
  lastErrorCode: string | null
}

export const DEFAULT_CHAT_SESSION_RUNTIME: ChatSessionRuntime = Object.freeze({
  phase: 'idle',
  statusText: '',
  lastErrorCode: null,
})

type PersistedChatStoreState = Pick<ChatStore, 'sessions' | 'activeSessionId'>

function getDefaultSessionRuntime(): ChatSessionRuntime {
  return {
    phase: DEFAULT_CHAT_SESSION_RUNTIME.phase,
    statusText: DEFAULT_CHAT_SESSION_RUNTIME.statusText,
    lastErrorCode: DEFAULT_CHAT_SESSION_RUNTIME.lastErrorCode,
  }
}

function getRuntimeForSession(
  runtimes: Record<string, ChatSessionRuntime>,
  id: string,
): ChatSessionRuntime {
  return runtimes[id] ?? getDefaultSessionRuntime()
}

export function selectSessionRuntime(
  state: Pick<ChatStore, 'sessionRuntimeById'>,
  sessionId: string | null | undefined,
): ChatSessionRuntime {
  const id = String(sessionId || '').trim()
  return id ? (state.sessionRuntimeById[id] ?? DEFAULT_CHAT_SESSION_RUNTIME) : DEFAULT_CHAT_SESSION_RUNTIME
}

interface ChatStore {
  sessions: ChatSession[]
  activeSessionId: string | null
  sessionRuntimeById: Record<string, ChatSessionRuntime>

  createSession: (workspace?: string) => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  renameSession: (id: string, title: string) => void
  setSessionStatusText: (id: string, statusText: string) => void
  setSessionLastErrorCode: (id: string, code: string | null) => void
  setSessionPhase: (id: string, phase: ChatSessionPhase) => void
  clearSessionRuntime: (id: string) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      sessionRuntimeById: {},

      createSession: (workspace = 'default') => {
        const id = crypto.randomUUID()
        const locale = useLocaleStore.getState().locale
        const title = locale === 'en' ? 'New chat' : '新对话'
        set((s) => ({
          sessions: [{ id, title, createdAt: Date.now(), workspace }, ...s.sessions],
          activeSessionId: id,
        }))
        return id
      },

      switchSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) => set(s => {
        deleteSessionMessages(id)
        deleteSessionToolCalls(id)
        const rest = s.sessions.filter(x => x.id !== id)
        const nextRuntimeById = { ...s.sessionRuntimeById }
        delete nextRuntimeById[id]
        return {
          sessions: rest,
          activeSessionId: s.activeSessionId === id ? (rest[0]?.id ?? null) : s.activeSessionId,
          sessionRuntimeById: nextRuntimeById,
        }
      }),

      renameSession: (id, title) => set(s => ({
        sessions: s.sessions.map(x => x.id === id ? { ...x, title } : x),
      })),
      setSessionStatusText: (id, statusText) => set((s) => {
        const sessionId = String(id || '').trim()
        if (!sessionId) return s
        const current = getRuntimeForSession(s.sessionRuntimeById, sessionId)
        if (current.statusText === statusText) return s
        return {
          sessionRuntimeById: {
            ...s.sessionRuntimeById,
            [sessionId]: {
              ...current,
              statusText,
            },
          },
        }
      }),
      setSessionLastErrorCode: (id, code) => set((s) => {
        const sessionId = String(id || '').trim()
        if (!sessionId) return s
        const current = getRuntimeForSession(s.sessionRuntimeById, sessionId)
        if (current.lastErrorCode === code) return s
        return {
          sessionRuntimeById: {
            ...s.sessionRuntimeById,
            [sessionId]: {
              ...current,
              lastErrorCode: code,
            },
          },
        }
      }),
      setSessionPhase: (id, phase) => set((s) => {
        const sessionId = String(id || '').trim()
        if (!sessionId) return s
        const current = getRuntimeForSession(s.sessionRuntimeById, sessionId)
        if (current.phase === phase) return s
        return {
          sessionRuntimeById: {
            ...s.sessionRuntimeById,
            [sessionId]: {
              ...current,
              phase,
            },
          },
        }
      }),
      clearSessionRuntime: (id) => set((s) => {
        const sessionId = String(id || '').trim()
        if (!sessionId || !(sessionId in s.sessionRuntimeById)) return s
        const nextRuntimeById = { ...s.sessionRuntimeById }
        delete nextRuntimeById[sessionId]
        return { sessionRuntimeById: nextRuntimeById }
      }),
    }),
    {
      name: 'aelin-chat-v2',
      partialize: (state): PersistedChatStoreState => ({
        sessions: state.sessions,
        activeSessionId: state.activeSessionId,
      }),
    }
  )
)
