import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useLocaleStore } from '@/shared/stores/localeStore'
import { deleteSessionMessages } from '../chatHistoryStorage'

export interface ChatSession {
  id: string
  title: string
  createdAt: number
  workspace: string
}

interface ChatStore {
  sessions: ChatSession[]
  activeSessionId: string | null
  statusText: string
  lastErrorCode: string | null

  createSession: (workspace?: string) => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  renameSession: (id: string, title: string) => void
  setStatusText: (v: string) => void
  setLastErrorCode: (code: string | null) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      statusText: '',
      lastErrorCode: null,

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
        const rest = s.sessions.filter(x => x.id !== id)
        return { sessions: rest, activeSessionId: s.activeSessionId === id ? (rest[0]?.id ?? null) : s.activeSessionId }
      }),

      renameSession: (id, title) => set(s => ({
        sessions: s.sessions.map(x => x.id === id ? { ...x, title } : x),
      })),
      setStatusText: (v) => set({ statusText: v }),
      setLastErrorCode: (code) => set({ lastErrorCode: code }),
    }),
    { name: 'aelin-chat-v2' }
  )
)
