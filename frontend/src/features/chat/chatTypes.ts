import type { ChatAction, ChatCitation } from '@/shared/api/types'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  expression?: string
  citations?: ChatCitation[]
  actions?: ChatAction[]
  images?: { dataUrl: string; name: string }[]
  timestamp: number
}
