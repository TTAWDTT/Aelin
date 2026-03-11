import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AelinCitation, AelinAction, AelinToolStep } from '@/shared/api/types'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  expression?: string
  citations?: AelinCitation[]
  actions?: AelinAction[]
  toolTrace?: AelinToolStep[]
  memorySummary?: string
  images?: { dataUrl: string; name: string }[]
  timestamp: number
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
  workspace: string
}

interface ChatStore {
  sessions: ChatSession[]
  activeSessionId: string | null
  isStreaming: boolean
  statusText: string

  createSession: (workspace?: string) => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  renameSession: (id: string, title: string) => void
  addMessage: (sessionId: string, msg: ChatMessage) => void
  updateLastAssistant: (sessionId: string, partial: Partial<ChatMessage>) => void
  appendContent: (sessionId: string, chunk: string) => void
  setStreaming: (v: boolean) => void
  setStatusText: (v: string) => void
  getActiveSession: () => ChatSession | undefined
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isStreaming: false,
      statusText: '',

      createSession: (workspace = 'default') => {
        const id = crypto.randomUUID()
        set(s => ({
          sessions: [{ id, title: '新对话', messages: [], createdAt: Date.now(), workspace }, ...s.sessions],
          activeSessionId: id,
        }))
        return id
      },

      switchSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) => set(s => {
        const rest = s.sessions.filter(x => x.id !== id)
        return { sessions: rest, activeSessionId: s.activeSessionId === id ? (rest[0]?.id ?? null) : s.activeSessionId }
      }),

      renameSession: (id, title) => set(s => ({
        sessions: s.sessions.map(x => x.id === id ? { ...x, title } : x),
      })),

      addMessage: (sessionId, msg) => set(s => ({
        sessions: s.sessions.map(x => x.id === sessionId ? { ...x, messages: [...x.messages, msg] } : x),
      })),

      updateLastAssistant: (sessionId, partial) => set(s => ({
        sessions: s.sessions.map(x => {
          if (x.id !== sessionId) return x
          const lastIndex = x.messages.findLastIndex((m: ChatMessage) => m.role === 'assistant')
          if (lastIndex < 0) return x
          const msgs = [...x.messages]
          msgs[lastIndex] = { ...msgs[lastIndex], ...partial }
          return { ...x, messages: msgs }
        }),
      })),

      appendContent: (sessionId, chunk) => set(s => ({
        sessions: s.sessions.map(x => {
          if (x.id !== sessionId) return x
          const lastIndex = x.messages.findLastIndex((m: ChatMessage) => m.role === 'assistant')
          if (lastIndex < 0) return x
          const msgs = [...x.messages]
          msgs[lastIndex] = {
            ...msgs[lastIndex],
            content: `${msgs[lastIndex]?.content || ''}${chunk}`,
          }
          return { ...x, messages: msgs }
        }),
      })),

      setStreaming: (v) => set(s => (s.isStreaming === v ? s : { isStreaming: v })),
      setStatusText: (v) => set(s => (s.statusText === v ? s : { statusText: v })),
      getActiveSession: () => {
        const s = get()
        return s.sessions.find(x => x.id === s.activeSessionId)
      },
    }),
    {
      name: 'aelin-chat',
      partialize: (state) => ({
        sessions: state.sessions,
        activeSessionId: state.activeSessionId,
      }),
    }
  )
)
