import type { BaseMessage } from '@langchain/core/messages'
import type { ChatRequest } from '@/shared/api/types'
import type { ChatMessage, ChatSession } from '../stores/chatStore'

const MAX_QUERY_CHARS = 1200

export type PendingImage = { dataUrl: string; name: string }

type StreamMessageLike = {
  id?: string
  type?: string
  content?: unknown
  tool_calls?: unknown[]
  tool_call_id?: string
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function normalizeMessageType(value: unknown): 'user' | 'assistant' | 'tool' | 'system' | '' {
  const type = String(value || '').trim().toLowerCase()
  if (type === 'human' || type === 'user') return 'user'
  if (type === 'ai' || type === 'assistant') return 'assistant'
  if (type === 'tool') return 'tool'
  if (type === 'system') return 'system'
  return ''
}

function getMessageId(message: unknown): string {
  const record = asRecord(message)
  const direct = record.id
  if (typeof direct === 'string' && direct.trim()) return direct.trim()
  return crypto.randomUUID()
}

export function normalizeAssistantMarkdown(text: string): string {
  const normalized = String(text || '').replace(/\r\n/g, '\n')
  return normalized.replace(/^(#{1,6})(\S)/gm, '$1 $2')
}

export function formatBytes(size: number): string {
  const bytes = Number.isFinite(size) ? Math.max(0, size) : 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function trimQueryForApi(text: string): string {
  const normalized = String(text || '').trim()
  if (normalized.length <= MAX_QUERY_CHARS) return normalized
  return `${normalized.slice(0, MAX_QUERY_CHARS - 1)}…`
}

export function extractTextContent(content: unknown): string {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''

  return content
    .map((item) => {
      const record = asRecord(item)
      if (record.type === 'text') return String(record.text || '')
      return ''
    })
    .filter(Boolean)
    .join('\n')
    .trim()
}

export function extractImageInputs(content: unknown): PendingImage[] {
  if (!Array.isArray(content)) return []

  return content
    .map((item) => {
      const record = asRecord(item)
      if (record.type !== 'image_url') return null
      const imageUrl = record.image_url
      if (typeof imageUrl === 'string' && imageUrl.startsWith('data:image/')) {
        return { dataUrl: imageUrl, name: '' }
      }
      const imageRecord = asRecord(imageUrl)
      const url = String(imageRecord.url || '').trim()
      if (!url.startsWith('data:image/')) return null
      return {
        dataUrl: url,
        name: String(imageRecord.name || ''),
      }
    })
    .filter((item): item is PendingImage => item != null)
}

export function buildHumanStreamMessage(text: string, images?: PendingImage[]): StreamMessageLike {
  const trimmed = trimQueryForApi(text)
  if (!images?.length) {
    return {
      id: crypto.randomUUID(),
      type: 'human',
      content: trimmed,
    }
  }

  const blocks: Array<Record<string, unknown>> = []
  if (trimmed) {
    blocks.push({ type: 'text', text: trimmed })
  }
  for (const image of images) {
    if (!String(image.dataUrl || '').startsWith('data:image/')) continue
    blocks.push({
      type: 'image_url',
      image_url: { url: image.dataUrl },
    })
  }

  return {
    id: crypto.randomUUID(),
    type: 'human',
    content: blocks.length > 1 ? blocks : trimmed,
  }
}

export function buildUserMessage(text: string, images?: PendingImage[]): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content: text,
    images,
    timestamp: Date.now(),
  }
}

export function buildAssistantMessage(): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
  }
}

export function chatMessageToStreamMessage(message: ChatMessage): StreamMessageLike | null {
  if (message.role === 'user') {
    return buildHumanStreamMessage(message.content, message.images)
  }
  if (message.role === 'assistant') {
    return {
      id: message.id,
      type: 'ai',
      content: normalizeAssistantMarkdown(message.content || ''),
    }
  }
  return null
}

export function buildSessionHistoryMessages(session?: ChatSession): StreamMessageLike[] {
  return (session?.messages ?? [])
    .map(chatMessageToStreamMessage)
    .filter((item): item is StreamMessageLike => item != null)
    .filter((item) => {
      const text = extractTextContent(item.content)
      return Boolean(text || (Array.isArray(item.content) && item.content.length > 0))
    })
}

export function buildChatRequestFromStream(params: {
  historyMessages: StreamMessageLike[]
  inputMessages: StreamMessageLike[]
  workspace: string
  attachmentIds: number[]
  source?: string
}): ChatRequest {
  const fullMessages = [...params.historyMessages, ...params.inputMessages]
  const lastUserIndex = [...fullMessages]
    .map((message, index) => ({ message, index }))
    .reverse()
    .find(({ message }) => normalizeMessageType(message.type) === 'user')
    ?.index

  const latestUser = typeof lastUserIndex === 'number' ? fullMessages[lastUserIndex] : undefined
  const historyMessages = typeof lastUserIndex === 'number'
    ? fullMessages.slice(0, lastUserIndex)
    : fullMessages

  const history = historyMessages
    .map((message) => {
      const role = normalizeMessageType(message.type)
      if (!role || role === 'tool') return null
      const content = extractTextContent(message.content)
      if (!content) return null
      return {
        role: role === 'user' ? 'user' : role === 'assistant' ? 'assistant' : 'system',
        content,
      }
    })
    .filter((item): item is { role: 'user' | 'assistant' | 'system'; content: string } => item != null)

  const query = trimQueryForApi(extractTextContent(latestUser?.content))
  const images = extractImageInputs(latestUser?.content).map((image) => ({
    data_url: image.dataUrl,
    name: image.name,
  }))

  return {
    query:
      query ||
      (images.length > 0
        ? '请结合这些图片给我一个简短说明。'
        : params.attachmentIds.length > 0
          ? '请先基于我上传的附件内容给出结论和建议。'
          : ''),
    source: params.source || 'chat_ui',
    workspace: params.workspace || 'default',
    history,
    images,
    attachment_ids: params.attachmentIds,
  }
}

export function streamMessagesToChatMessages(
  streamMessages: BaseMessage[],
  previousMessages: ChatMessage[],
  isStreaming: boolean,
): ChatMessage[] {
  const previousById = new Map(previousMessages.map((message) => [message.id, message]))
  const next: ChatMessage[] = []

  for (const message of streamMessages) {
      const raw = message as unknown as StreamMessageLike
      const role = normalizeMessageType(
        typeof (message as any)?.getType === 'function' ? (message as any).getType() : raw.type,
      )
      if (role !== 'user' && role !== 'assistant') continue

      const id = getMessageId(raw)
      const previous = previousById.get(id)
      const content = normalizeAssistantMarkdown(extractTextContent((message as any).content ?? raw.content))
      const images = role === 'user'
        ? extractImageInputs((message as any).content ?? raw.content)
        : undefined

      if (role === 'assistant' && !content.trim() && !(raw.tool_calls?.length)) {
        continue
      }

      next.push({
        id,
        role,
        content,
        images: images?.length ? images : previous?.images,
        timestamp: previous?.timestamp ?? Date.now(),
        expression: previous?.expression,
        citations: previous?.citations,
        actions: previous?.actions,
      })
  }

  if (isStreaming) {
    const previousPlaceholder = previousMessages.at(-1)
    const hasAssistant = next.some((message) => message.role === 'assistant')
    if (
      previousPlaceholder?.role === 'assistant'
      && !previousPlaceholder.content
      && !hasAssistant
    ) {
      return [...next, previousPlaceholder]
    }
  }

  return next
}
