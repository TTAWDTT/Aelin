import { startTransition, useEffect, useMemo, useRef } from 'react'
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
import type { AelinAttachmentUploadResponse, DeepAgentsExecutionEvent } from '@/shared/api/types'
import { useChatI18n } from './chatI18n'
import { ExecutionPane } from './components/ExecutionPane'
import { useExecutionPaneStore } from './stores/executionPaneStore'
import { executionEventsFromRunState } from './executionEventUtils'

export function ChatView() {
  const { sessions, activeSessionId, isStreaming, statusText, createSession } = useChatStore()
  const session = sessions.find((s) => s.id === activeSessionId)
  const messages = session?.messages ?? []
  const { send, captureAndSend, uploadAttachments, sendWithAttachments, stop } = useChatStream()
  const scrollRef = useRef<HTMLDivElement>(null)
  const compact = useMediaQuery('(max-width: 960px)')
  const viewportWidth = useViewportWidth()
  const { t } = useChatI18n()
  const {
    openForMessage,
    focusedMessageId,
    setFocusedMessageId,
    open,
    setOpen,
    suppressAutoOpen,
  } = useExecutionPaneStore()

  useAutoScrollToBottom(scrollRef, [
    messages.length,
    messages.at(-1)?.content,
    isStreaming,
  ])

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

  const handleSendWithAttachments = async (attachments: AelinAttachmentUploadResponse[], textHint: string) => {
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
    // 切换 session 时，让 Execution Pane 自动跟随该会话的最新执行信息。
    startTransition(() => setFocusedMessageId(null))
  }, [activeSessionId, setFocusedMessageId])

  const latestAssistantWithExecution = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant' && (m.runState?.parts.length ?? 0) > 0)

  const focusedRunState =
    focusedMessageId && messages.length
      ? messages.find((m) => m.id === focusedMessageId && m.role === 'assistant')
          ?.runState ?? null
      : null

  const currentRunState = focusedRunState ?? latestAssistantWithExecution?.runState

  const executionEvents: DeepAgentsExecutionEvent[] = useMemo(
    () => executionEventsFromRunState(currentRunState),
    [currentRunState]
  )

  // 桌面模式下，当本轮已经产生执行事件且正在流式时，自动展开右侧 ExecutionPane。
  useEffect(() => {
    if (!compact && isStreaming && executionEvents.length > 0 && !open && !suppressAutoOpen) {
      setOpen(true)
    }
  }, [compact, isStreaming, executionEvents.length, open, suppressAutoOpen, setOpen])

  const handleOpenExecutionForLatest = () => {
    openForMessage(latestAssistantWithExecution?.id ?? null)
  }

  const handleOpenExecutionForMessage = (messageId: string | null) => {
    openForMessage(messageId)
  }

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
            compact={compact}
            runState={currentRunState}
            onOpenExecution={handleOpenExecutionForLatest}
          />
          <ChatTimeline
            scrollRef={scrollRef}
            messages={messages}
            isStreaming={isStreaming}
            statusText={statusText}
            compact={compact}
            viewportWidth={viewportWidth}
            onQuickPrompt={handleSend}
            onOpenExecutionForMessage={handleOpenExecutionForMessage}
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
        <ExecutionPane runState={currentRunState} isStreaming={isStreaming} compact={compact} />
      </div>
    </PageScaffold>
  )
}
