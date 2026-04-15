import { useEffect, useState } from 'react'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'
import type { ExecutionRuntime } from '../executionStreamUtils'
import type { ChatArtifact } from '../artifactUtils'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import {
  ExecutionTabButton,
  GraphBoard,
  JsonBlock,
  NamespaceLaneCard,
  SubagentCard,
  ToolCard,
} from './ExecutionPaneParts'
import {
  asRecord,
  compactText,
  statusIcon,
  tabClassName,
} from './executionPaneShared'
import { ArtifactCardGrid } from './ArtifactCardGrid'

interface ExecutionPaneProps {
  runtime: ExecutionRuntime
  values: Record<string, unknown>
  artifacts: ChatArtifact[]
  isStreaming: boolean
  compact?: boolean
  onOpenArtifact: (artifact: ChatArtifact) => void
}

type ExecutionTab = 'graph' | 'tools' | 'state'

export function ExecutionPane({
  runtime,
  values,
  artifacts,
  isStreaming,
  compact = false,
  onOpenArtifact,
}: ExecutionPaneProps) {
  const { t, locale } = useChatI18n()
  const { open } = useExecutionPaneStore()
  const { tools, hasExecution } = runtime
  const todos = Array.isArray(values.todos) ? values.todos : []
  const hasStateSnapshot = Object.keys(values).some((key) => key !== 'messages')
  const [tab, setTab] = useState<ExecutionTab>('graph')

  useEffect(() => {
    if (hasExecution) setTab('graph')
  }, [hasExecution])

  const label = hasExecution ? t('trace.executionPane.title') : t('trace.executionPane.empty')

  return (
    <aside
      aria-label={label}
      className={cn(
        'flex shrink-0 flex-col overflow-hidden bg-[var(--color-bg)] text-[var(--color-text)] transition-[width,height] duration-200',
        compact ? 'mt-1 w-full border-t border-[var(--color-border)]' : 'hidden min-w-0 max-w-[560px] lg:flex',
        compact
          ? open
            ? 'h-80'
            : 'h-7'
          : open
            ? 'w-[min(46vw,540px)]'
            : 'w-0',
      )}
    >
      {open && (
        <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1">
          {!hasExecution && (
            <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {t('trace.executionPane.emptyDetail')}
            </p>
          )}

          {hasExecution && (
            <div className="flex h-full flex-col">
              <div
                role="tablist"
                aria-label={t('trace.executionPane.title')}
                className="mb-1.5 flex gap-1 rounded-lg bg-[var(--color-bg)] p-0.5"
              >
                <ExecutionTabButton id="graph" active={tab === 'graph'} label="Graph" onClick={() => setTab('graph')} />
                <ExecutionTabButton
                  id="tools"
                  active={tab === 'tools'}
                  label={t('trace.tab.tools')}
                  disabled={tools.length === 0}
                  onClick={() => tools.length > 0 && setTab('tools')}
                />
                <ExecutionTabButton
                  id="state"
                  active={tab === 'state'}
                  label="State"
                  disabled={!hasStateSnapshot}
                  onClick={() => hasStateSnapshot && setTab('state')}
                />
              </div>

              <div className="relative mt-1 flex-1 pr-1">
                <div className={tabClassName(tab === 'graph')}>
                  <GraphTab
                    runtime={runtime}
                    isStreaming={isStreaming}
                    locale={locale}
                    emptyDetail={t('trace.executionPane.emptyDetail')}
                  />
                </div>

                <div className={tabClassName(tab === 'tools')}>
                  <ToolsTab
                    tools={tools}
                    emptyLabel={t('trace.tools.empty')}
                    title={t('trace.tab.tools')}
                  />
                </div>

                <div className={tabClassName(tab === 'state')}>
                  <StateTab
                    todos={todos}
                    values={values}
                    artifacts={artifacts}
                    filesHeading={t('trace.files.heading')}
                    filesHelper={t('trace.files.helper')}
                    filesEmpty={t('trace.files.empty')}
                    onOpenArtifact={onOpenArtifact}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

function GraphTab({
  runtime,
  isStreaming,
  locale,
  emptyDetail,
}: {
  runtime: ExecutionRuntime
  isStreaming: boolean
  locale: string
  emptyDetail: string
}) {
  const { graph, lanes, subagents, hasOfficialGraph } = runtime

  return (
    <div id="execution-pane-graph" className="space-y-2.5 text-[11px]">
      <section className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
              Graph
            </div>
            <div className="mt-1 text-[15px] font-semibold text-[var(--color-text)]">
              Live execution map
            </div>
            <p className="mt-1 max-w-[40ch] text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              A quieter view of the official runtime graph, with the active path kept in focus.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1">
              {graph.nodes.length} nodes
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1">
              {graph.edges.length} edges
            </span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1">
              {isStreaming ? 'live' : 'settled'}
            </span>
          </div>
        </div>
        <GraphBoard nodes={graph.nodes} edges={graph.edges} isStreaming={isStreaming} />
        {!hasOfficialGraph && (
          <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
            Runtime did not publish a graph.
          </p>
        )}
      </section>

      <section className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
        <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.18em]">Branches</div>
            <div className="mt-1 text-[14px] font-semibold text-[var(--color-text)]">Active paths</div>
          </div>
          <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1 text-[10px] uppercase tracking-[0.16em]">
            {lanes.length}
          </span>
        </div>
        <div className="mt-3 space-y-2">
          {lanes.length > 0 ? (
            <div className="grid gap-2">
              {lanes.map((lane) => (
                <NamespaceLaneCard key={lane.key} lane={lane} />
              ))}
            </div>
          ) : (
            <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {emptyDetail}
            </p>
          )}
        </div>
      </section>

      {subagents.length > 0 && (
        <section className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)] p-3">
          <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
            <div>
              <div className="text-[10px] font-medium uppercase tracking-[0.18em]">Subagents</div>
              <div className="mt-1 text-[14px] font-semibold text-[var(--color-text)]">Delegation</div>
            </div>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1 text-[10px] uppercase tracking-[0.16em]">
              {locale === 'zh' ? (isStreaming ? '实时' : '已结束') : (isStreaming ? 'live' : 'settled')}
            </span>
          </div>
          <div className="mt-2 space-y-2">
            {subagents.map((subagent) => (
              <SubagentCard key={`runtime:${subagent.key}`} subagent={subagent} compact />
            ))}
          </div>
        </section>
      )}

      {subagents.length === 0 && lanes.length === 0 && !hasOfficialGraph && (
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
          <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
            {emptyDetail}
          </p>
        </section>
      )}
    </div>
  )
}

function ToolsTab({
  tools,
  emptyLabel,
  title,
}: {
  tools: ExecutionRuntime['tools']
  emptyLabel: string
  title: string
}) {
  return (
    <div id="execution-pane-tools" className="space-y-2 text-[11px]">
      {tools.length === 0
        ? (
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {emptyLabel}
            </p>
          )
        : (
            <section className="space-y-2 rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
              <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                <span className="font-medium">{title}</span>
                <span>{tools.length} calls</span>
              </div>
              {tools.map((tool) => <ToolCard key={tool.key} tool={tool} compact />)}
            </section>
          )}
    </div>
  )
}

function StateTab({
  todos,
  values,
  artifacts,
  filesHeading,
  filesHelper,
  filesEmpty,
  onOpenArtifact,
}: {
  todos: unknown[]
  values: Record<string, unknown>
  artifacts: ChatArtifact[]
  filesHeading: string
  filesHelper: string
  filesEmpty: string
  onOpenArtifact: (artifact: ChatArtifact) => void
}) {
  return (
    <div id="execution-pane-state" className="space-y-2 text-[11px]">
      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
        <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-[var(--color-text-muted)]">
          <div>
            <div className="font-medium text-[var(--color-text-muted)]">
              {filesHeading}
            </div>
            <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {filesHelper}
            </p>
          </div>
          <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1 text-[10px] uppercase tracking-[0.16em]">
            {artifacts.length}
          </span>
        </div>
        {artifacts.length > 0
          ? <ArtifactCardGrid artifacts={artifacts} onOpenArtifact={onOpenArtifact} />
          : (
              <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
                {filesEmpty}
              </p>
            )}
      </section>

      {todos.length > 0 && (
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
          <div className="mb-2 text-[11px] font-medium text-[var(--color-text-muted)]">
            Todos
          </div>
          <div className="space-y-1.5">
            {todos.map((item, index) => {
              const record = asRecord(item)
              const title = String(record.title || record.content || `Todo ${index + 1}`)
              return (
                <div
                  key={`${title}:${index}`}
                  className="flex items-start gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5"
                >
                  <span className="pt-0.5">{statusIcon(record.done ? 'completed' : 'pending')}</span>
                  <div className="min-w-0 flex-1">
                    <div className="break-words text-[12px] text-[var(--color-text)]">
                      {title}
                    </div>
                    {Boolean(record.detail) && (
                      <div className="mt-0.5 break-words text-[11px] text-[var(--color-text-muted)]">
                        {compactText(String(record.detail))}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
        <div className="mb-2 text-[11px] font-medium text-[var(--color-text-muted)]">
          Snapshot
        </div>
        <JsonBlock value={values} />
      </section>
    </div>
  )
}
