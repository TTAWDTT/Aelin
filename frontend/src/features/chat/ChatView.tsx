import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { useChatStore } from './stores/chatStore'
import { getSessionToolCalls, setSessionToolCalls } from './chatExecutionStorage'
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
import { analyzeExecutionStream, type ChatRuntimeStream } from './executionStreamUtils'
import { useExecutionPaneStore } from './stores/executionPaneStore'
import { ArtifactPreviewDialog } from './components/ArtifactPreviewDialog'
import {
  buildMessageArtifactMap,
  extractArtifactsFromState,
  extractArtifactsFromToolCalls,
  sortArtifacts,
  type ChatArtifact,
} from './artifactUtils'

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
  const runtimeStream = stream as ChatRuntimeStream
  const deferredStreamMessages = useDeferredValue(runtimeStream.messages)
  const deferredStreamValues = useDeferredValue(runtimeStream.values)
  const deferredStreamSubagents = useDeferredValue(runtimeStream.subagents)
  const executionStream = useMemo(
    () => ({
      messages: deferredStreamMessages,
      values: deferredStreamValues,
      isLoading: stream.isLoading,
      subagents: deferredStreamSubagents,
      getToolCalls: runtimeStream.getToolCalls,
      getSubagentsByMessage: runtimeStream.getSubagentsByMessage,
      getMessagesMetadata: runtimeStream.getMessagesMetadata,
    }),
    [
      deferredStreamMessages,
      deferredStreamSubagents,
      deferredStreamValues,
      runtimeStream.getMessagesMetadata,
      runtimeStream.getSubagentsByMessage,
      runtimeStream.getToolCalls,
      stream.isLoading,
    ],
  )
  const executionAnalysis = useMemo(
    () => analyzeExecutionStream(executionStream, assistantGraph),
    [assistantGraph, executionStream],
  )
  const execution = executionAnalysis.runtime
  const messageToolCalls = executionAnalysis.toolCallsByMessage
  const [selectedArtifact, setSelectedArtifact] = useState<ChatArtifact | null>(null)
  const activeSession = useMemo(
    () => sessions.find((item) => item.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  )
  const activeWorkspace = String(activeSession?.workspace || 'default').trim() || 'default'
  const lastMessage = messages.at(-1)
  const hasAssistantReplyStarted = lastMessage?.role === 'assistant'
  const values =
    deferredStreamValues && typeof deferredStreamValues === 'object' && !Array.isArray(deferredStreamValues)
      ? deferredStreamValues
      : {}
  const artifactsByPath = useMemo(() => extractArtifactsFromState(values), [values])
  const persistedToolCallsByMessage = useMemo(
    () => getSessionToolCalls(activeSessionId),
    [activeSessionId],
  )
  const combinedToolCallsByMessage = useMemo(() => {
    const merged = new Map(persistedToolCallsByMessage)
    messageToolCalls.forEach((toolCalls, messageId) => {
      const existing = merged.get(messageId) ?? []
      const deduped = new Map(existing.map((tool) => [tool.key, tool]))
      toolCalls.forEach((tool) => deduped.set(tool.key, tool))
      merged.set(messageId, Array.from(deduped.values()))
    })
    return merged
  }, [messageToolCalls, persistedToolCallsByMessage])
  const toolArtifacts = useMemo(() => extractArtifactsFromToolCalls(combinedToolCallsByMessage), [combinedToolCallsByMessage])
  const mergedArtifactsByPath = useMemo(() => {
    const merged = new Map(toolArtifacts)
    artifactsByPath.forEach((artifact, path) => merged.set(path, artifact))
    return merged
  }, [artifactsByPath, toolArtifacts])
  const runtimeArtifacts = useMemo(() => {
    return sortArtifacts(mergedArtifactsByPath.values())
  }, [mergedArtifactsByPath])
  const artifactsByMessage = useMemo(
    () => buildMessageArtifactMap(combinedToolCallsByMessage, artifactsByPath),
    [artifactsByPath, combinedToolCallsByMessage],
  )
  const displayedArtifactsByMessage = useMemo(() => {
    const next = new Map(artifactsByMessage)
    const attachedPaths = new Set<string>()
    artifactsByMessage.forEach((artifacts) => {
      artifacts.forEach((artifact) => attachedPaths.add(artifact.path))
    })

    const unassignedArtifacts = sortArtifacts(
      Array.from(mergedArtifactsByPath.values()).filter((artifact) => !attachedPaths.has(artifact.path)),
    )
    if (unassignedArtifacts.length === 0) return next

    const artifactTime = (artifact: ChatArtifact): number => {
      const modified = Date.parse(String(artifact.modifiedAt || ''))
      if (Number.isFinite(modified)) return modified
      const created = Date.parse(String(artifact.createdAt || ''))
      if (Number.isFinite(created)) return created
      return 0
    }

    const newestTime = artifactTime(unassignedArtifacts[0])
    const fallbackArtifacts = newestTime > 0
      ? unassignedArtifacts.filter((artifact) => artifactTime(artifact) >= newestTime - 60_000)
      : unassignedArtifacts.slice(0, 3)
    if (fallbackArtifacts.length === 0) return next

    const lastAssistantMessage = [...messages].reverse().find((message) => message.role === 'assistant')
    if (!lastAssistantMessage) return next

    const existing = next.get(lastAssistantMessage.id) ?? []
    const seen = new Set(existing.map((artifact) => artifact.path))
    const merged = [...existing]
    fallbackArtifacts.forEach((artifact) => {
      if (seen.has(artifact.path)) return
      seen.add(artifact.path)
      merged.push(artifact)
    })
    next.set(lastAssistantMessage.id, sortArtifacts(merged))
    return next
  }, [artifactsByMessage, mergedArtifactsByPath, messages])

  useAutoScrollToBottom(scrollRef, [
    messages.length,
    messages.at(-1)?.content,
    isStreaming,
  ], {
    streaming: isStreaming,
  })

  useEffect(() => {
    if (!activeSessionId) return
    setSessionToolCalls(activeSessionId, combinedToolCallsByMessage)
  }, [activeSessionId, combinedToolCallsByMessage])

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
            toolCallsByMessage={combinedToolCallsByMessage}
            artifactsByMessage={displayedArtifactsByMessage}
            artifactLookup={mergedArtifactsByPath}
            workspace={activeWorkspace}
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
        <ExecutionPane
          runtime={execution}
          values={values}
          artifacts={runtimeArtifacts}
          isStreaming={isStreaming}
          compact={compact}
          onOpenArtifact={setSelectedArtifact}
        />
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
