import type { ChatMessage } from '../chatTypes'

const MAX_QUERY_CHARS = 1200

export type PendingImage = { dataUrl: string; name: string }

type StreamMessageLike = {
  id?: string
  type?: string
  content?: unknown
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function normalizeAssistantMarkdown(text: string): string {
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

function extractTextContent(content: unknown): string {
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

function extractImageInputs(content: unknown): PendingImage[] {
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

export function buildHumanStreamMessage(
  text: string,
  images?: PendingImage[],
  id?: string,
): StreamMessageLike {
  const trimmed = trimQueryForApi(text)
  const messageId = String(id || '').trim() || crypto.randomUUID()
  if (!images?.length) {
    return {
      id: messageId,
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
    id: messageId,
    type: 'human',
    content: blocks.length > 1 ? blocks : trimmed,
  }
}

function chatMessageToStreamMessage(message: ChatMessage): StreamMessageLike | null {
  if (message.role === 'user') {
    return buildHumanStreamMessage(message.content, message.images, message.id)
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

export function buildSessionHistoryMessages(messages?: ChatMessage[]): StreamMessageLike[] {
  return (messages ?? [])
    .map(chatMessageToStreamMessage)
    .filter((item): item is StreamMessageLike => item != null)
    .filter((item) => {
      const text = extractTextContent(item.content)
      return Boolean(text || (Array.isArray(item.content) && item.content.length > 0))
    })
}
