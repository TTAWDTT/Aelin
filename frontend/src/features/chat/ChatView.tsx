import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { useChatStore } from './stores/chatStore'
import { useChatStream } from './hooks/useChatStream'
import { ComposerBar } from './components/ComposerBar'
import { ChatStatusBar } from './components/ChatStatusBar'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { ChatTimeline } from './components/ChatTimeline'
import { useAutoScrollToBottom } from './hooks/useAutoScrollToBottom'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { useViewportWidth } from '@/shared/hooks/useViewportWidth'
import type { AttachmentUploadResponse } from '@/shared/api/types'
import { useChatI18n } from './chatI18n'
import { ExecutionPane } from './components/ExecutionPane'
import { getExecutionRuntime, getMessageToolCallMap } from './executionStreamUtils'
import { useExecutionPaneStore } from './stores/executionPaneStore'
import { ArtifactPreviewDialog } from './components/ArtifactPreviewDialog'
import { buildMessageArtifactMap, extractArtifactsFromState, type ChatArtifact } from './artifactUtils'

export function ChatView() {
  const { sessions, activeSessionId, statusText, createSession } = useChatStore()
  const { send, messages, captureAndSend, uploadAttachments, sendWithAttachments, stop, stream, assistantGraph } = useChatStream()
  const scrollRef = useRef<HTMLDivElement>(null)
  const compact = useMediaQuery('(max-width: 960px)')
  const viewportWidth = useViewportWidth()
  const { t } = useChatI18n()
  const {
    open,
    setOpen,
    suppressAutoOpen,
  } = useExecutionPaneStore()
  const isStreaming = stream.isLoading
  const execution = getExecutionRuntime(stream, assistantGraph)
  const messageToolCalls = getMessageToolCallMap(stream)
  const [selectedArtifact, setSelectedArtifact] = useState<ChatArtifact | null>(null)
  const lastMessage = messages.at(-1)
  const hasAssistantReplyStarted = lastMessage?.role === 'assistant'
  const values =
    stream.values && typeof stream.values === 'object' && !Array.isArray(stream.values)
      ? stream.values
      : {}
  const artifactsByPath = useMemo(() => extractArtifactsFromState(values), [values])
  const artifactsByMessage = useMemo(
    () => buildMessageArtifactMap(messageToolCalls, artifactsByPath),
    [artifactsByPath, messageToolCalls],
  )

  useAutoScrollToBottom(scrollRef, [
    messages.length,
    messages.at(-1)?.content,
    isStreaming,
  ], {
    streaming: isStreaming,
  })

  const handleSend = (text: string) => {
    if (!text.trim()) return
    send(text)
  }

  const handleCaptureAndSend = async (mode: 'fullscreen' | 'region', textHint: string) => {
    try {
      await captureAndSend(mode, textHint)
    } catch (error: any) {
      const message = String(error?.message || t('error.screenshot'))
      toast.error(message)
      throw error
    }
  }

  const handleUploadAttachments = async (files: File[]) => {
    try {
      return await uploadAttachments(files)
    } catch (error: any) {
      const message = String(error?.message || t('error.attach.process'))
      toast.error(message)
      throw error
    }
  }

  const handleSendWithAttachments = async (attachments: AttachmentUploadResponse[], textHint: string) => {
    try {
      await sendWithAttachments(attachments, textHint)
    } catch (error: any) {
      const message = String(error?.message || t('error.attach.send'))
      toast.error(message)
      throw error
    }
  }

  useEffect(() => {
    if (sessions.length === 0) createSession()
  }, [sessions.length, createSession])

  useEffect(() => {
    if (!compact && isStreaming && execution.hasExecution && !open && !suppressAutoOpen) {
      setOpen(true)
    }
  }, [compact, execution.hasExecution, isStreaming, open, suppressAutoOpen, setOpen])

  return (
    <PageScaffold
      title={t('nav.title')}
      subtitle={t('nav.subtitle')}
      contentClassName="flex flex-1 min-h-0 flex-col p-0"
    >
      <div className="flex flex-1 min-h-0 flex-col lg:flex-row">
        <section className="flex min-h-0 flex-1 flex-col">
          <ChatStatusBar
            isStreaming={isStreaming}
            statusText={statusText}
            hasAssistantReplyStarted={hasAssistantReplyStarted}
            compact={compact}
            execution={execution}
            onOpenExecution={() => setOpen(true)}
          />
          <ChatTimeline
            scrollRef={scrollRef}
            messages={messages}
            isStreaming={isStreaming}
            statusText={statusText}
            compact={compact}
            viewportWidth={viewportWidth}
            toolCallsByMessage={messageToolCalls}
            artifactsByMessage={artifactsByMessage}
            liveSummary={execution.live}
            onQuickPrompt={handleSend}
            onOpenArtifact={setSelectedArtifact}
          />
          <ComposerBar
            onSend={handleSend}
            onCaptureAndSend={handleCaptureAndSend}
            onUploadAttachments={handleUploadAttachments}
            onSendWithAttachments={handleSendWithAttachments}
            onStop={stop}
            isStreaming={isStreaming}
            compact={compact}
            placeholder={t('composer.placeholder')}
          />
        </section>
        <ExecutionPane runtime={execution} values={values} isStreaming={isStreaming} compact={compact} />
      </div>
      <ArtifactPreviewDialog
        artifact={selectedArtifact}
        open={selectedArtifact != null}
        onOpenChange={(open) => {
          if (!open) setSelectedArtifact(null)
        }}
      />
    </PageScaffold>
  )
}
