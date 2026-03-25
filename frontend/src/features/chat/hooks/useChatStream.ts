import { useCallback } from 'react'
import { useChatStore } from '../stores/chatStore'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinAttachmentUploadResponse } from '@/shared/api/types'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import { useChatI18n } from '../chatI18n'
import {
  formatBytes,
  trimQueryForApi,
  type PendingImage,
} from './chatStreamHelpers'
import { useDeepAgentsStream } from './useDeepAgentsStream'

export function useChatStream() {
  const store = useChatStore()
  const { t } = useChatI18n()
  const { send, stop } = useDeepAgentsStream()

  const captureAndSend = useCallback(
    async (mode: 'fullscreen' | 'region' = 'fullscreen', textHint = '') => {
      if (store.isStreaming) return
      store.setStatusText(
        mode === 'region' ? t('status.capture.region') : t('status.capture.fullscreen')
      )
      try {
        const capture = await aelinApi.deviceScreenCapture({ mode })
        const prompt = String(textHint || '').trim()
        send(prompt, [{ dataUrl: capture.data_url, name: capture.name || `screen-${Date.now()}.jpg` }])
      } catch (error) {
        store.setStatusText('')
        throw error
      }
    },
    [send, store, t]
  )

  const uploadAttachments = useCallback(
    async (files: File[]): Promise<AelinAttachmentUploadResponse[]> => {
      if (store.isStreaming) return []
      const picked = Array.from(files || []).slice(0, MAX_PENDING_ATTACHMENTS)
      if (picked.length === 0) return []

      let sessionId = store.activeSessionId
      if (!sessionId) sessionId = store.createSession() || store.activeSessionId
      const resolvedSessionId = String(sessionId || '')
      const session = store.sessions.find(s => s.id === sessionId)
      const workspace = session?.workspace || 'default'

      store.setStatusText(t('status.attach.processing'))
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
          throw new Error(
            t('composer.attach.partialFail', { names: failedNames.join(', ') })
          )
        }
        return uploaded
      } catch (error) {
        store.setStatusText('')
        throw error
      }
    },
    [store, t]
  )

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

  return { send, captureAndSend, uploadAttachments, sendWithAttachments, stop }
}
