import { useRef, useCallback } from 'react'
import { useChatStore, type ChatMessage } from '../stores/chatStore'
import { streamChat } from '@/shared/api/sse'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinChatRequest, AelinToolStep } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'

const MAX_IMAGE_ATTACHMENTS = 4
const MAX_TEXT_ATTACHMENT_SIZE = 256 * 1024
const MAX_TEXT_ATTACHMENT_CHARS = 480
const MAX_QUERY_CHARS = 1200
const TEXT_ATTACHMENT_EXTENSIONS = new Set([
  'txt', 'md', 'markdown', 'json', 'csv', 'log', 'xml', 'yaml', 'yml', 'html', 'htm', 'ini', 'conf', 'py', 'js', 'ts',
])

function mergeToolTrace(prev: AelinToolStep[] | undefined, step: AelinToolStep): AelinToolStep[] {
  const existing = [...(prev ?? [])]
  const stage = String(step.stage || '').trim()
  if (!stage) return existing

  const index = existing.findIndex((item) => String(item.stage || '').trim() === stage)
  if (index === -1) return [...existing, step]

  existing[index] = {
    ...existing[index],
    ...step,
    stage,
  }
  return existing
}

function formatBytes(size: number): string {
  const bytes = Number.isFinite(size) ? Math.max(0, size) : 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function normalizeText(text: string): string {
  return String(text || '').replace(/\s+/g, ' ').trim()
}

function capText(text: string, max: number): string {
  if (text.length <= max) return text
  return `${text.slice(0, Math.max(0, max - 1))}…`
}

function getFileExt(name: string): string {
  const idx = name.lastIndexOf('.')
  if (idx < 0) return ''
  return name.slice(idx + 1).toLowerCase()
}

function isTextLikeFile(file: File): boolean {
  if (String(file.type || '').toLowerCase().startsWith('text/')) return true
  return TEXT_ATTACHMENT_EXTENSIONS.has(getFileExt(file.name || ''))
}

async function fileToDataUrl(file: File): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('file_read_failed'))
    reader.readAsDataURL(file)
  })
}

async function buildNonImageAttachmentLine(file: File): Promise<string> {
  const base = `${file.name || 'unnamed'} (${file.type || 'unknown'}, ${formatBytes(file.size)})`
  if (!isTextLikeFile(file)) {
    return `${base} [二进制文件，当前仅附带文件信息]`
  }
  if (file.size > MAX_TEXT_ATTACHMENT_SIZE) {
    return `${base} [文本过大，当前仅附带文件信息]`
  }
  try {
    const text = normalizeText(await file.text())
    if (!text) return `${base} [文本为空]`
    return `${base} 摘要: ${capText(text, MAX_TEXT_ATTACHMENT_CHARS)}`
  } catch {
    return `${base} [读取失败，当前仅附带文件信息]`
  }
}

function trimQueryForApi(text: string): string {
  const normalized = String(text || '').trim()
  if (normalized.length <= MAX_QUERY_CHARS) return normalized
  return `${normalized.slice(0, MAX_QUERY_CHARS - 1)}…`
}

export function useChatStream() {
  const store = useChatStore()
  const abortRef = useRef<(() => void) | null>(null)

  const send = useCallback((text: string, images?: { dataUrl: string; name: string }[]) => {
    let sessionId = store.activeSessionId
    if (!sessionId) sessionId = store.createSession()

    const session = store.sessions.find(s => s.id === sessionId)
    const history = (session?.messages ?? [])
      .slice(-20)
      .filter(m => {
        const role = String(m.role || '').trim()
        const content = String(m.content || '').trim()
        return (role === 'user' || role === 'assistant') && content.length > 0
      })
      .map(m => ({ role: m.role, content: String(m.content || '').trim() }))

    // Add user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(), role: 'user', content: text,
      images, timestamp: Date.now(),
    }
    store.addMessage(sessionId!, userMsg)

    // Add empty assistant message
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(), role: 'assistant', content: '',
      timestamp: Date.now(),
    }
    store.addMessage(sessionId!, assistantMsg)
    store.setStreaming(true)
    store.setStatusText('正在思考…')

    // Auto-title from first message
    if ((session?.messages.length ?? 0) === 0) {
      const seed = String(text || '').trim() || (images?.length ? '附件分析' : '新对话')
      const title = seed.length > 20 ? seed.slice(0, 20) + '…' : seed
      store.renameSession(sessionId!, title)
    }

    const normalizedQuery = trimQueryForApi(String(text || '').trim())
    const body: AelinChatRequest = {
      query: normalizedQuery || (images?.length ? '请先分析我上传的附件，然后给我结论和建议。' : ''),
      workspace: session?.workspace || 'default',
      history,
      images: images?.map(i => ({ data_url: i.dataUrl, name: i.name })),
    }

    const cancel = streamChat(body, {
      onIntent: (d) => store.setStatusText(`意图: ${d.intent_type}`),
      onPlan: (d) => store.setStatusText(`计划: ${d.steps?.length || 0} 步`),
      onToolStep: (step) => {
        store.setStatusText(`${step.stage}…`)
        const currentTrace = store.getActiveSession()?.messages.findLast((m: ChatMessage) => m.role === 'assistant')?.toolTrace
        store.updateLastAssistant(sessionId!, {
          toolTrace: mergeToolTrace(currentTrace, step),
        })
      },
      onCitations: (citations) => store.updateLastAssistant(sessionId!, { citations }),
      onActions: (actions) => store.updateLastAssistant(sessionId!, { actions }),
      onReplyChunk: (chunk) => store.appendContent(sessionId!, chunk),
      onDone: (d) => {
        store.updateLastAssistant(sessionId!, { expression: d.expression, memorySummary: d.memory_summary })
        store.setStreaming(false)
        store.setStatusText('')
      },
      onError: (err) => {
        store.appendContent(sessionId!, `\n\n> ⚠️ 错误: ${err.message}`)
        store.setStreaming(false)
        store.setStatusText('')
      },
    })

    abortRef.current = cancel
  }, [store])

  const captureAndSend = useCallback(async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
    if (store.isStreaming) return
    store.setStatusText(mode === 'region' ? '等待框选截图…' : '正在全屏截图…')
    try {
      const capture = await aelinApi.deviceScreenCapture({ mode })
      const prompt = String(textHint || '').trim()
      send(prompt, [{ dataUrl: capture.data_url, name: capture.name || `screen-${Date.now()}.jpg` }])
    } catch (error) {
      store.setStatusText('')
      throw error
    }
  }, [send, store])

  const attachAndSend = useCallback(async (files: File[], textHint = '') => {
    if (store.isStreaming) return
    const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
    if (picked.length === 0) return

    store.setStatusText('正在处理附件…')
    try {
      const imageFiles = picked.filter((file) => String(file.type || '').toLowerCase().startsWith('image/'))
      const sentImageFiles = imageFiles.slice(0, MAX_IMAGE_ATTACHMENTS)
      const droppedImageFiles = imageFiles.slice(MAX_IMAGE_ATTACHMENTS)
      const nonImageFiles = picked.filter((file) => !String(file.type || '').toLowerCase().startsWith('image/'))

      const images = await Promise.all(
        sentImageFiles.map(async (file) => ({
          dataUrl: await fileToDataUrl(file),
          name: file.name || `image-${Date.now()}.png`,
        }))
      )

      const attachmentLines: string[] = []
      for (const file of sentImageFiles) {
        attachmentLines.push(`${file.name || 'image'} (${formatBytes(file.size)}) [图片已附带]`)
      }
      for (const file of droppedImageFiles) {
        attachmentLines.push(`${file.name || 'image'} (${formatBytes(file.size)}) [未发送，超过 ${MAX_IMAGE_ATTACHMENTS} 张图片上限]`)
      }
      for (const file of nonImageFiles) {
        attachmentLines.push(await buildNonImageAttachmentLine(file))
      }

      const basePrompt = String(textHint || '').trim()
      const attachmentBlock = attachmentLines.length > 0 ? `附件清单:\n${attachmentLines.map((line) => `- ${line}`).join('\n')}` : ''
      let finalPrompt = [basePrompt, attachmentBlock].filter(Boolean).join('\n\n').trim()

      if (!finalPrompt && images.length === 0) {
        finalPrompt = '我上传了附件，请先根据附件清单整理要点，并告诉我下一步建议。'
      }

      send(trimQueryForApi(finalPrompt), images)
    } catch (error) {
      store.setStatusText('')
      throw error
    }
  }, [send, store])

  const stop = useCallback(() => {
    abortRef.current?.()
    store.setStreaming(false)
    store.setStatusText('')
  }, [store])

  return { send, captureAndSend, attachAndSend, stop }
}
