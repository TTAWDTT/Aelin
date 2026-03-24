import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AelinCitation, AelinAction, AelinToolStep, DeepAgentsToolRun } from '@/shared/api/types'
import { useLocaleStore } from '@/shared/stores/localeStore'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  expression?: string
  citations?: AelinCitation[]
  actions?: AelinAction[]
  toolTrace?: AelinToolStep[]
  toolRuns?: DeepAgentsToolRun[]
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
  lastErrorCode: string | null

  createSession: (workspace?: string) => string
  switchSession: (id: string) => void
  deleteSession: (id: string) => void
  renameSession: (id: string, title: string) => void
  addMessage: (sessionId: string, msg: ChatMessage) => void
  updateLastAssistant: (sessionId: string, partial: Partial<ChatMessage>) => void
  appendContent: (sessionId: string, chunk: string) => void
  setStreaming: (v: boolean) => void
  setStatusText: (v: string) => void
  setLastErrorCode: (code: string | null) => void
  getActiveSession: () => ChatSession | undefined
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isStreaming: false,
      statusText: '',
      lastErrorCode: null,

      createSession: (workspace = 'default') => {
        const id = crypto.randomUUID()
        const locale = useLocaleStore.getState().locale
        const title = locale === 'en' ? 'New chat' : '新对话'
        set((s) => ({
          sessions: [{ id, title, messages: [], createdAt: Date.now(), workspace }, ...s.sessions],
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
          const msgs = [...x.messages]
          const last = msgs.findLast((m: ChatMessage) => m.role === 'assistant')
          if (last) Object.assign(last, partial)
          return { ...x, messages: msgs }
        }),
      })),

      appendContent: (sessionId, chunk) => set(s => ({
        sessions: s.sessions.map(x => {
          if (x.id !== sessionId) return x
          const msgs = [...x.messages]
          const last = msgs.findLast((m: ChatMessage) => m.role === 'assistant')
          if (last) last.content += chunk
          return { ...x, messages: msgs }
        }),
      })),

      setStreaming: (v) => set({ isStreaming: v }),
      setStatusText: (v) => set({ statusText: v }),
      setLastErrorCode: (code) => set({ lastErrorCode: code }),
      getActiveSession: () => {
        const s = get()
        return s.sessions.find(x => x.id === s.activeSessionId)
      },
    }),
    { name: 'aelin-chat' }
  )
)
