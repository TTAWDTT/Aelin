import type { ChatMessage } from '../chatTypes'
import {
  artifactFromServerPayload,
  artifactMatchesReferencePath,
  extractReferencedArtifactPaths,
  findArtifactsReferencedInText,
  type ChatArtifact,
} from '../artifactUtils'
import type { ExecutionLiveSummary, ExecutionTodoItem, ExecutionToolCall } from '../executionStreamUtils'
import { cn } from '@/shared/utils/cn'
import { AelinAvatar } from '@/shared/components/AelinAvatar'
import { aelinApi } from '@/shared/api/aelin'
import { MessageActionsPanel } from './MessageActionsPanel'
import { MessageCitationsPanel } from './MessageCitationsPanel'
import { MarkdownMessage } from './MarkdownMessage'
import { MessageArtifactsPanel } from './MessageArtifactsPanel'
import { formatExecutionStatus } from './executionPaneShared'
import {
  calculateCompactMaxWidth,
  EXPRESSION_LABELS,
  formatMessageTime,
  resolveExpressionSticker,
} from './messageBubbleUtils'
import { useLocaleStore } from '@/shared/stores/localeStore'
import { useEffect, useMemo, useState } from 'react'

interface MessageBubbleProps {
  message: ChatMessage
  toolCalls?: ExecutionToolCall[]
  artifacts?: ChatArtifact[]
  artifactLookup?: Map<string, ChatArtifact>
  workspace?: string
  liveSummary?: ExecutionLiveSummary
  isThinking?: boolean
  thinkingText?: string
  compact?: boolean
  viewportWidth: number
  onQuickPrompt?: (text: string) => void
  onOpenArtifact: (artifact: ChatArtifact) => void
}

export function MessageBubble({
  message,
  toolCalls = [],
  artifacts = [],
  artifactLookup,
  workspace = 'default',
  liveSummary,
  isThinking = false,
  thinkingText,
  compact = false,
  viewportWidth,
  onQuickPrompt,
  onOpenArtifact,
}: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const compactMaxWidth = calculateCompactMaxWidth(viewportWidth)
  const stickerSrc = !isUser ? resolveExpressionSticker(message.expression) : ''
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const [resolvedReferencedArtifacts, setResolvedReferencedArtifacts] = useState<ChatArtifact[]>([])
  const referencedPaths = useMemo(
    () => extractReferencedArtifactPaths(message.content || ''),
    [message.content],
  )
  const knownReferencedArtifacts = useMemo(
    () => findArtifactsReferencedInText(message.content || '', artifactLookup ?? new Map()),
    [artifactLookup, message.content],
  )

  useEffect(() => {
    if (isUser || referencedPaths.length === 0) {
      setResolvedReferencedArtifacts([])
      return
    }

    const unresolvedPaths = referencedPaths.filter((path) => !knownReferencedArtifacts.some(
      (artifact) => artifactMatchesReferencePath(artifact, path),
    ))
    if (unresolvedPaths.length === 0) {
      setResolvedReferencedArtifacts([])
      return
    }

    let cancelled = false
    void Promise.all(unresolvedPaths.map(async (path) => {
      try {
        const payload = await aelinApi.resolveArtifactPath({
          workspace,
          path,
        })
        return artifactFromServerPayload(payload)
      } catch {
        return null
      }
    })).then((items) => {
      if (cancelled) return
      const seen = new Set<string>()
      const next: ChatArtifact[] = []
      items.forEach((artifact) => {
        if (!artifact || seen.has(artifact.path)) return
        seen.add(artifact.path)
        next.push(artifact)
      })
      setResolvedReferencedArtifacts(next)
    })

    return () => {
      cancelled = true
    }
  }, [isUser, knownReferencedArtifacts, referencedPaths, workspace])

  const visibleArtifacts = useMemo(() => {
    const seen = new Set<string>()
    const merged: ChatArtifact[] = []
    const addArtifact = (artifact: ChatArtifact | null | undefined) => {
      if (!artifact || seen.has(artifact.path)) return
      seen.add(artifact.path)
      merged.push(artifact)
    }

    artifacts.forEach(addArtifact)
    knownReferencedArtifacts.forEach(addArtifact)
    resolvedReferencedArtifacts.forEach(addArtifact)
    return merged
  }, [artifacts, knownReferencedArtifacts, resolvedReferencedArtifacts])
  const stickerLabel = message.expression
    ? EXPRESSION_LABELS[message.expression] ?? (isZh ? 'Aelin 表情' : 'Aelin expression')
    : isZh
      ? 'Aelin 表情'
      : 'Aelin expression'
  const liveHeadline = buildLiveHeadline({ liveSummary, thinkingText, isZh })
  const liveTools = liveSummary?.runningTools ?? []
  const recentTools = liveSummary?.recentCompletedTools ?? []
  const runningSubagents = liveSummary?.runningSubagents ?? []
  const recentSubagents = liveSummary?.recentCompletedSubagents ?? []
  const todos = liveSummary?.todos ?? []

  return (
    <article className={cn(
      'aelin-fade-up flex min-w-0 w-full',
      compact ? 'max-w-full items-start gap-1.5' : 'max-w-[94%] items-end gap-2 sm:max-w-[86%] sm:gap-2.5 md:max-w-[80%]',
      isUser ? 'ml-auto flex-row-reverse' : ''
    )}>
      {/* Avatar */}
      {!isUser && (
        <div className="shrink-0 max-[500px]:hidden">
          <AelinAvatar
            size="sm"
            title="Aelin"
            className={cn('!rounded-[10px]', compact && '!h-6 !w-6')}
          />
        </div>
      )}

      <div className={cn(
        'chat-elevate min-w-0 rounded-[16px]',
        'max-w-full',
        compact ? 'px-2.5 py-2' : 'px-3 py-2.5 sm:px-4 sm:py-3.5',
        isThinking && !isUser && 'chat-thinking-bubble',
        isUser
          ? 'rounded-tr-[6px] border border-[var(--color-border)] bg-[var(--color-panel-alt)]'
          : 'rounded-tl-[6px] border border-[var(--color-border)] bg-[var(--color-panel)]'
      )} style={compact ? { maxWidth: `${compactMaxWidth}px` } : undefined}>
        {!isUser && isThinking && (
          <div className="mb-2.5 rounded-[14px] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-2.5">
            <div className="flex items-center gap-2">
              <img
                src="/gif/action_05.gif"
                alt="Aelin is thinking"
                className="h-7 w-7 rounded-[8px] border border-[var(--color-border)] object-cover"
                draggable={false}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
                  <span className="truncate">{liveHeadline}</span>
                  <span className="chat-thinking-dots shrink-0" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
                {liveSummary?.currentNode && (
                  <div className="mt-1 truncate text-[10px] uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
                    {liveSummary.currentNamespace && liveSummary.currentNamespace !== 'root'
                      ? `${liveSummary.currentNamespace} · ${liveSummary.currentNode}`
                      : liveSummary.currentNode}
                  </div>
                )}
              </div>
            </div>

            {(liveTools.length > 0 || recentTools.length > 0 || runningSubagents.length > 0 || recentSubagents.length > 0 || todos.length > 0) && (
              <div className="mt-2.5 space-y-2">
                {liveTools.length > 0 && (
                  <LiveBlock title={isZh ? '正在调用' : 'Running tools'}>
                    {liveTools.map((tool) => (
                      <LiveToolRow key={`running:${tool.key}`} tool={tool} />
                    ))}
                    {(liveSummary?.runningToolCount ?? 0) > liveTools.length && (
                      <LiveMoreRow count={(liveSummary?.runningToolCount ?? 0) - liveTools.length} />
                    )}
                  </LiveBlock>
                )}

                {runningSubagents.length > 0 && (
                  <LiveBlock title={isZh ? '子代理' : 'Subagents'}>
                    {runningSubagents.map((subagent) => (
                      <LiveSubagentRow key={`running:${subagent.key}`} subagent={subagent} />
                    ))}
                    {(liveSummary?.runningSubagentCount ?? 0) > runningSubagents.length && (
                      <LiveMoreRow count={(liveSummary?.runningSubagentCount ?? 0) - runningSubagents.length} />
                    )}
                  </LiveBlock>
                )}

                {todos.length > 0 && (
                  <LiveBlock title={isZh ? '计划' : 'Plan'}>
                    {todos.map((todo) => (
                      <LiveTodoRow key={todo.key} todo={todo} />
                    ))}
                    {(liveSummary?.todoCount ?? 0) > todos.length && (
                      <LiveMoreRow count={(liveSummary?.todoCount ?? 0) - todos.length} />
                    )}
                  </LiveBlock>
                )}

                {(recentTools.length > 0 || recentSubagents.length > 0) && (
                  <LiveBlock title={isZh ? '刚刚完成' : 'Recently finished'}>
                    {recentTools.map((tool) => (
                      <LiveToolRow key={`done:${tool.key}`} tool={tool} />
                    ))}
                    {recentSubagents.map((subagent) => (
                      <LiveSubagentRow key={`done:${subagent.key}`} subagent={subagent} />
                    ))}
                  </LiveBlock>
                )}
              </div>
            )}
          </div>
        )}

        {/* Images */}
        {message.images && message.images.length > 0 && (
          <div className="mb-2.5 flex gap-2">
            {message.images.map((img, i) => (
              <img key={i} src={img.dataUrl} alt={img.name} className="h-20 w-20 rounded-xl object-cover" />
            ))}
          </div>
        )}

        {/* Content */}
        <MarkdownMessage content={message.content || ''} compact={compact} />

        {!isUser && !isThinking && toolCalls.length > 0 && (
          <div className="mt-2.5 space-y-1.5 border-t border-[var(--color-border)] pt-2">
            {toolCalls.map((tool) => (
              <div
                key={tool.key}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2.5 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-[var(--color-text)]">
                    {tool.name}
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    {formatExecutionStatus(tool.state)}
                  </span>
                </div>
                <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                  {tool.result || tool.args || (isZh ? '已记录本次工具调用。' : 'Tool call recorded.')}
                </div>
              </div>
            ))}
          </div>
        )}

        {!isUser && !isThinking && visibleArtifacts.length > 0 && (
          <MessageArtifactsPanel artifacts={visibleArtifacts} onOpenArtifact={onOpenArtifact} />
        )}

        {!isUser && stickerSrc && !isThinking && (
          <div className="mt-2">
            <img
              src={stickerSrc}
              alt={stickerLabel}
              title={stickerLabel}
              className={cn(
                'block rounded-[18px] object-contain',
                compact ? 'h-16 w-16' : 'h-20 w-20'
              )}
              draggable={false}
            />
          </div>
        )}

        {/* Citations (collapsed by default) */}
        <MessageCitationsPanel citations={message.citations || []} />
        <MessageActionsPanel actions={message.actions || []} />

        <div className="mt-2 text-[10px] tracking-wide text-[var(--color-text-muted)]">
          {formatMessageTime(message.timestamp)}
        </div>
      </div>
    </article>
  )
}

function buildLiveHeadline({
  liveSummary,
  thinkingText,
  isZh,
}: {
  liveSummary?: ExecutionLiveSummary
  thinkingText?: string
  isZh: boolean
}): string {
  if (liveSummary?.runningSubagents?.length) {
    const names = liveSummary.runningSubagents.map((item) => item.name).join(' · ')
    return isZh ? `正在协同子代理：${names}` : `Coordinating subagents: ${names}`
  }
  if (liveSummary?.runningTools?.length) {
    const allPreparing = liveSummary.runningTools.every((item) => item.state === 'preparing')
    const names = liveSummary.runningTools.map((item) => item.name).join(' · ')
    if (allPreparing) {
      return isZh ? `正在生成工具参数：${names}` : `Preparing tool args: ${names}`
    }
    return isZh ? `正在执行工具：${names}` : `Executing tools: ${names}`
  }
  if (liveSummary?.currentNode) {
    return isZh ? `正在执行 ${liveSummary.currentNode}` : `Running ${liveSummary.currentNode}`
  }
  if (thinkingText?.trim()) return thinkingText.trim()
  return isZh ? 'Aelin 正在思考' : 'Aelin is thinking'
}

function LiveBlock({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-1.5">
      <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
        {title}
      </div>
      <div className="space-y-1.5">{children}</div>
    </section>
  )
}

function LiveMoreRow({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
      +{count} more
    </div>
  )
}

function LiveToolRow({ tool }: { tool: ExecutionToolCall }) {
  const summary = tool.result || tool.args || ''
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className="truncate text-[11px] font-medium text-[var(--color-text)]">
          {tool.name}
        </span>
        <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {formatExecutionStatus(tool.state)}
        </span>
      </div>
      {summary && (
        <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
          {summary}
        </div>
      )}
    </div>
  )
}

function LiveSubagentRow({ subagent }: { subagent: ExecutionLiveSummary['runningSubagents'][number] }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className="truncate text-[11px] font-medium text-[var(--color-text)]">
          {subagent.name}
        </span>
        <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {formatExecutionStatus(subagent.status)}
        </span>
      </div>
      <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
        {[subagent.namespace, subagent.preview].filter(Boolean).join(' · ')}
      </div>
    </div>
  )
}

function LiveTodoRow({ todo }: { todo: ExecutionTodoItem }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className={cn(
          'inline-block h-2 w-2 rounded-full',
          todo.status === 'completed' ? 'bg-[var(--color-text)]' : 'bg-[var(--color-text-muted)]',
        )} />
        <span className="truncate text-[11px] font-medium text-[var(--color-text)]">
          {todo.title}
        </span>
        <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {formatExecutionStatus(todo.status)}
        </span>
      </div>
      {todo.detail && (
        <div className="mt-1 break-words text-[11px] text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
          {todo.detail}
        </div>
      )}
    </div>
  )
}
