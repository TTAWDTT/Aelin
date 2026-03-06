import { useRef, useCallback } from 'react'
import { useChatStore, type ChatMessage } from '../stores/chatStore'
import { streamChat } from '@/shared/api/sse'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinAttachmentUploadResponse, AelinChatRequest, AelinToolStep } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'

const MAX_QUERY_CHARS = 1200

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

function trimQueryForApi(text: string): string {
  const normalized = String(text || '').trim()
  if (normalized.length <= MAX_QUERY_CHARS) return normalized
  return `${normalized.slice(0, MAX_QUERY_CHARS - 1)}…`
}

export function useChatStream() {
  const store = useChatStore()
  const abortRef = useRef<(() => void) | null>(null)

  const send = useCallback(
    (
      text: string,
      images?: { dataUrl: string; name: string }[],
      attachmentIds?: number[],
    ) => {
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
      const normalizedAttachmentIds = Array.from(new Set((attachmentIds || []).filter((id) => Number.isFinite(id) && id > 0))).slice(0, 20)

      if ((session?.messages.length ?? 0) === 0) {
        const seed = String(text || '').trim() || (images?.length || normalizedAttachmentIds.length ? '附件分析' : '新对话')
        const title = seed.length > 20 ? seed.slice(0, 20) + '…' : seed
        store.renameSession(sessionId!, title)
      }

      const normalizedQuery = trimQueryForApi(String(text || '').trim())
      const body: AelinChatRequest = {
        query: normalizedQuery || (images?.length || normalizedAttachmentIds.length ? '请先分析我上传的附件，然后给我结论和建议。' : ''),
        workspace: session?.workspace || 'default',
        history,
        images: images?.map(i => ({ data_url: i.dataUrl, name: i.name })),
        attachment_ids: normalizedAttachmentIds,
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
    },
    [store]
  )

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

  const uploadAttachments = useCallback(async (files: File[]): Promise<AelinAttachmentUploadResponse[]> => {
    if (store.isStreaming) return []
    const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
    if (picked.length === 0) return []

    let sessionId = store.activeSessionId
    if (!sessionId) sessionId = store.createSession() || store.activeSessionId
    const resolvedSessionId = String(sessionId || '')
    const session = store.sessions.find(s => s.id === sessionId)
    const workspace = session?.workspace || 'default'

    store.setStatusText('附件处理中…')
    try {
      const settled = await Promise.allSettled(
        picked.map((file) => aelinApi.uploadAttachment(file, { workspace, session_id: resolvedSessionId }))
      )
      const uploaded: AelinAttachmentUploadResponse[] = []
      const failedNames: string[] = []
      settled.forEach((item, index) => {
        if (item.status === 'fulfilled') {
          uploaded.push(item.value)
          return
        }
        failedNames.push(picked[index]?.name || `attachment-${index + 1}`)
      })
      store.setStatusText('')
      if (uploaded.length === 0 && failedNames.length > 0) {
        throw new Error(`附件上传失败：${failedNames.join('、')}`)
      }
      return uploaded
    } catch (error) {
      store.setStatusText('')
      throw error
    }
  }, [store])

  const sendWithAttachments = useCallback(async (attachments: AelinAttachmentUploadResponse[], textHint = '') => {
    if (store.isStreaming) return
    const rows = Array.from(attachments || []).slice(0, MAX_PENDING_ATTACHMENTS)
    if (rows.length === 0) return
    const attachmentIds = rows.map((item) => Number(item.attachment_id)).filter((id) => Number.isFinite(id) && id > 0)
    if (attachmentIds.length === 0) return
    const attachmentBlock = `附件清单:\n${rows.map((item) => {
      const parsed = Number(item.chunk_count || 0)
      const parsedNote = parsed > 0 ? `已解析 ${parsed} chunks` : '已接入'
      return `- ${item.file_name || 'attachment'} (${formatBytes(Number(item.size_bytes || 0))}) [${parsedNote}]`
    }).join('\n')}`
    const finalPrompt = trimQueryForApi([String(textHint || '').trim(), attachmentBlock].filter(Boolean).join('\n\n').trim())
    send(finalPrompt || '我上传了附件，请先基于附件内容回答。', undefined, attachmentIds)
  }, [send, store])

  const stop = useCallback(() => {
    abortRef.current?.()
    store.setStreaming(false)
    store.setStatusText('')
  }, [store])

  return { send, captureAndSend, uploadAttachments, sendWithAttachments, stop }
}
