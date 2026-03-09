import { useRef, useCallback } from 'react'
import { useChatStore } from '../stores/chatStore'
import { streamChat } from '@/shared/api/sse'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinAttachmentUploadResponse } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import { formatBytes } from '../utils/formatBytes'
import {
  buildAssistantMessage,
  buildChatRequest,
  buildHistory,
  buildStreamCallbacks,
  buildUserMessage,
  maybeRenameFreshSession,
  normalizeAttachmentIds,
  resolveSessionForSend,
  trimQueryForApi,
  type PendingImage,
} from './chatStreamHelpers'

export function useChatStream() {
  const store = useChatStore()
  const abortRef = useRef<(() => void) | null>(null)

  const send = useCallback(
    (
      text: string,
      images?: PendingImage[],
      attachmentIds?: number[],
    ) => {
      abortRef.current?.()
      abortRef.current = null

      const { sessionId, session } = resolveSessionForSend(store)
      const normalizedAttachmentIds = normalizeAttachmentIds(attachmentIds)
      const history = buildHistory(session)

      store.addMessage(sessionId, buildUserMessage(text, images))
      store.addMessage(sessionId, buildAssistantMessage())
      store.setStreaming(true)
      store.setStatusText('正在思考…')

      maybeRenameFreshSession(store, sessionId, session, text, images, normalizedAttachmentIds)

      const body = buildChatRequest({
        text,
        session,
        history,
        images,
        attachmentIds: normalizedAttachmentIds,
      })

      let cancel = () => {}
      cancel = streamChat(
        body,
        buildStreamCallbacks({
          store,
          sessionId,
          abortRef,
          getCancel: () => cancel,
        }),
      )

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
    abortRef.current = null
    store.setStreaming(false)
    store.setStatusText('')
  }, [store])

  return { send, captureAndSend, uploadAttachments, sendWithAttachments, stop }
}
