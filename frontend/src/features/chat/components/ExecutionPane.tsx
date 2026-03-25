import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Bot,
  CheckCircle2,
  CircleDashed,
  GitBranch,
  Hammer,
  Workflow,
  XCircle,
} from 'lucide-react'
import type { DeepAgentsRunState } from '@/shared/api/types'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'
import {
  buildGraphModelFromRunState,
  taskSnapshotsFromRunState,
  type RunGraphCluster,
  type RunGraphModel,
  type RunGraphNode,
} from '../executionEventUtils'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import { ProviderIcon } from './ProviderIcon'

interface ExecutionPaneProps {
  runState?: DeepAgentsRunState
  isStreaming: boolean
  compact?: boolean
}

type ExecutionTab = 'graph' | 'tools' | 'state'

export function ExecutionPane({
  runState,
  isStreaming,
  compact = false,
}: ExecutionPaneProps) {
  const { t } = useChatI18n()
  const { open } = useExecutionPaneStore()
  const graphModel = useMemo(() => buildGraphModelFromRunState(runState), [runState])
  const hasExecution = graphModel.nodes.length > 0 || (runState?.parts.length ?? 0) > 0
  const taskSnapshots = useMemo(() => taskSnapshotsFromRunState(runState), [runState])
  const toolSnapshots = useMemo(
    () => taskSnapshots.filter((task) => task.kind === 'tool'),
    [taskSnapshots],
  )
  const hasStateSnapshot = Object.keys(runState?.latestValues ?? {}).length > 0
  const [tab, setTab] = useState<ExecutionTab>('graph')

  useEffect(() => {
    if (!hasExecution) return
    setTab('graph')
  }, [hasExecution])

  const label = hasExecution ? t('trace.executionPane.title') : t('trace.executionPane.empty')

  return (
    <aside
      aria-label={label}
      className={cn(
        'flex shrink-0 flex-col overflow-hidden bg-[var(--color-bg)] text-[var(--color-text)] transition-[width,height] duration-200',
        compact ? 'mt-1 w-full border-t border-[var(--color-border)]' : 'hidden min-w-0 max-w-md lg:flex',
        compact
          ? open
            ? 'h-64'
            : 'h-7'
          : open
            ? 'w-[360px]'
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
                <ExecutionTabButton
                  id="graph"
                  active={tab === 'graph'}
                  label="Graph"
                  onClick={() => setTab('graph')}
                />
                <ExecutionTabButton
                  id="tools"
                  active={tab === 'tools'}
                  label={t('trace.tab.tools')}
                  disabled={toolSnapshots.length === 0}
                  onClick={() => toolSnapshots.length > 0 && setTab('tools')}
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
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'graph'
                      ? 'pointer-events-auto translate-y-0 opacity-100'
                      : 'pointer-events-none translate-y-1 opacity-0',
                  )}
                >
                  <RunGraphView graphModel={graphModel} isStreaming={isStreaming} />
                </div>
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'tools'
                      ? 'pointer-events-auto translate-y-0 opacity-100'
                      : 'pointer-events-none translate-y-1 opacity-0',
                  )}
                >
                  <TaskRunsView taskSnapshots={taskSnapshots} />
                </div>
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'state'
                      ? 'pointer-events-auto translate-y-0 opacity-100'
                      : 'pointer-events-none translate-y-1 opacity-0',
                  )}
                >
                  <StateSnapshotView runState={runState} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

interface ExecutionTabButtonProps {
  id: string
  active: boolean
  label: string
  disabled?: boolean
  onClick: () => void
}

function ExecutionTabButton({ id, active, label, disabled, onClick }: ExecutionTabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={`execution-pane-${id}`}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex-1 rounded-md px-1.5 py-1 text-[11px] transition-colors',
        active
          ? 'bg-[var(--color-panel)] text-[var(--color-text)]'
          : 'text-[var(--color-text-muted)] hover:bg-[var(--color-panel)] hover:text-[var(--color-text)]',
        disabled && 'opacity-50 hover:bg-transparent hover:text-[var(--color-text-muted)]',
      )}
    >
      <span className="block truncate">{label}</span>
    </button>
  )
}

function statusIcon(status?: string) {
  const lowered = String(status || '').toLowerCase()
  if (lowered === 'completed' || lowered === 'success') {
    return <CheckCircle2 size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'failed' || lowered === 'error') {
    return <XCircle size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'running' || lowered === 'pending') {
    return <CircleDashed size={13} className="animate-spin text-[var(--color-text)]" />
  }
  return null
}

function GraphNodeIcon({ node }: { node: RunGraphNode }) {
  if (node.kind === 'tool') return <Hammer size={12} className="text-[var(--color-text)]" />
  if (node.kind === 'model') return <Bot size={12} className="text-[var(--color-text)]" />
  if (node.kind === 'middleware') return <Workflow size={12} className="text-[var(--color-text)]" />
  if (node.kind === 'final') return <CheckCircle2 size={12} className="text-[var(--color-text)]" />
  if (node.kind === 'error') return <XCircle size={12} className="text-[var(--color-text)]" />
  return <GitBranch size={12} className="text-[var(--color-text)]" />
}

function RunGraphView({
  graphModel,
  isStreaming,
}: {
  graphModel: RunGraphModel
  isStreaming: boolean
}) {
  const { t } = useChatI18n()
  const rootCluster = graphModel.clusters.find((cluster) => cluster.key === graphModel.rootClusterKey)
  const branchClusters = graphModel.clusters
    .filter((cluster) => cluster.key !== graphModel.rootClusterKey)
    .sort((a, b) => a.startTs - b.startTs)
  const activeNode = graphModel.nodes.find((node) => node.key === graphModel.activeNodeKey)
  const focusNode = activeNode ?? graphModel.nodes.find((node) => node.key === graphModel.latestNodeKey)

  if (!graphModel.nodes.length || !rootCluster) {
    return (
      <p id="execution-pane-graph" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {t('trace.executionPane.emptyDetail')}
      </p>
    )
  }

  return (
    <div id="execution-pane-graph" className="space-y-2.5 text-[11px]">
      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
        <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
          <span className="font-medium">Topology</span>
          <span>{graphModel.nodes.length} nodes · {branchClusters.length} branches</span>
        </div>
        <div className="mt-2">
          <ClusterCard graphModel={graphModel} cluster={rootCluster} isStreaming={isStreaming} variant="root" />
        </div>
        {branchClusters.length > 0 && (
          <div className="mt-3 grid gap-2">
            {branchClusters.map((cluster) => (
              <ClusterCard
                key={cluster.key}
                graphModel={graphModel}
                cluster={cluster}
                isStreaming={isStreaming}
                variant="branch"
              />
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
        <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
          <span className="font-medium">Runtime</span>
          <span>{isStreaming ? 'live' : 'settled'}</span>
        </div>
        {focusNode ? (
          <div className="mt-2 space-y-2">
            <div className="flex items-start gap-2">
              <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
                <GraphNodeIcon node={focusNode} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                    {focusNode.title}
                  </span>
                  <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    {focusNode.status || 'ready'}
                  </span>
                </div>
                {focusNode.summary && (
                  <div className="mt-1 break-words text-[11px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                    {focusNode.summary}
                  </div>
                )}
              </div>
              <span className="pt-0.5">{statusIcon(focusNode.status)}</span>
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              <RuntimeStat label="Edges" value={String(graphModel.edges.length)} />
              <RuntimeStat label="Clusters" value={String(graphModel.clusters.length)} />
            </div>
          </div>
        ) : (
          <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
            No focused runtime node yet.
          </p>
        )}
      </section>
    </div>
  )
}

function ClusterCard({
  graphModel,
  cluster,
  isStreaming,
  variant,
}: {
  graphModel: RunGraphModel
  cluster: RunGraphCluster
  isStreaming: boolean
  variant: 'root' | 'branch'
}) {
  const nodes = cluster.nodeKeys
    .map((key) => graphModel.nodes.find((node) => node.key === key))
    .filter((node): node is RunGraphNode => node != null)
  const active = cluster.key === graphModel.activeClusterKey
  const anchorNode = cluster.anchorNodeKey
    ? graphModel.nodes.find((node) => node.key === cluster.anchorNodeKey)
    : null

  return (
    <section
      className={cn(
        'rounded-2xl border p-2.5',
        active
          ? 'border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)]'
          : 'border-[var(--color-border)] bg-[var(--color-panel-alt)]',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold text-[var(--color-text)]">
              {variant === 'root' ? 'Main graph' : cluster.label}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              {cluster.status || 'ready'}
            </span>
          </div>
          <div className="mt-0.5 text-[10px] text-[var(--color-text-muted)]">
            {variant === 'root'
              ? `${nodes.length} nodes`
              : `${cluster.pathLabel} · ${nodes.length} nodes`}
          </div>
        </div>
        {active && isStreaming && (
          <motion.span
            className="inline-flex h-2.5 w-2.5 rounded-full bg-[var(--color-text)]"
            initial={{ opacity: 0.35, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1.06 }}
            transition={{ repeat: Infinity, repeatType: "reverse", duration: 0.8 }}
          />
        )}
      </div>

      {anchorNode && variant === 'branch' && (
        <div className="mt-2 flex items-center gap-2 text-[10px] text-[var(--color-text-muted)]">
          <span className="inline-flex h-px w-4 bg-[var(--color-border-strong)]" />
          <span>forked from</span>
          <span className="truncate text-[var(--color-text)]">{anchorNode.title}</span>
        </div>
      )}

      <div className="mt-2 overflow-x-auto pb-1">
        <div className="flex min-w-max items-center gap-2">
          {nodes.map((node, index) => (
            <div key={node.key} className="flex items-center gap-2">
              <GraphNodeCard
                node={node}
                active={node.key === graphModel.activeNodeKey}
                latest={node.key === graphModel.latestNodeKey}
              />
              {index < nodes.length - 1 && (
                <div className="flex min-w-[28px] justify-center">
                  <motion.div
                    className="h-px w-8 bg-[var(--color-border-strong)]"
                    initial={{ scaleX: 0.5, opacity: 0.3 }}
                    animate={{ scaleX: 1, opacity: 0.9 }}
                    transition={{ duration: 0.25, delay: Math.min(index * 0.04, 0.24) }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function GraphNodeCard({
  node,
  active,
  latest,
}: {
  node: RunGraphNode
  active: boolean
  latest: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.18 }}
      className={cn(
        'group relative min-w-[144px] rounded-2xl border px-3 py-2.5',
        active
          ? 'border-[var(--color-border-strong)] bg-[var(--color-bg)]'
          : latest
            ? 'border-[var(--color-border-strong)] bg-[var(--color-bg)]/80'
            : 'border-[var(--color-border)] bg-[var(--color-panel)]',
      )}
    >
      {active && (
        <motion.span
          className="absolute inset-0 rounded-2xl border border-[var(--color-border-strong)]"
          initial={{ opacity: 0.16, scale: 0.96 }}
          animate={{ opacity: 0.36, scale: 1.02 }}
          transition={{ repeat: Infinity, repeatType: 'reverse', duration: 0.9 }}
        />
      )}
      <div className="relative flex items-start gap-2">
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-panel-alt)]">
          {node.kind === 'tool' && node.provider ? (
            <ProviderIcon provider={node.provider} size="md" className="h-8 w-8 border-0 bg-transparent" />
          ) : (
            <GraphNodeIcon node={node} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11px] font-semibold text-[var(--color-text)]">
            {node.title}
          </div>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
            {node.status || 'ready'}
          </div>
          {node.summary && (
            <div className="mt-1 line-clamp-3 break-words text-[10px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
              {node.summary}
            </div>
          )}
        </div>
        <span className="pt-0.5">{statusIcon(node.status)}</span>
      </div>
    </motion.div>
  )
}

function TaskRunsView({
  taskSnapshots,
}: {
  taskSnapshots: ReturnType<typeof taskSnapshotsFromRunState>
}) {
  const { t } = useChatI18n()
  const toolSnapshots = taskSnapshots.filter((task) => task.kind === 'tool')

  if (!toolSnapshots.length) {
    return (
      <p id="execution-pane-tools" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {t('trace.tools.empty')}
      </p>
    )
  }

  return (
    <div id="execution-pane-tools" className="space-y-2 text-[11px]">
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span className="font-medium">Tool calls</span>
        <span>{t('trace.tools.count', { count: toolSnapshots.length })}</span>
      </div>
      <ul className="space-y-1.5">
        {toolSnapshots.map((task) => (
          <li key={task.key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
            <div className="flex items-start gap-2">
              <ProviderIcon provider={task.toolName || 'core'} size="md" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                    {task.name}
                  </span>
                  <span className="text-[11px] text-[var(--color-text-muted)]">{task.status || '-'}</span>
                  <span className="text-[10px] text-[var(--color-text-muted)]">{task.updates} updates</span>
                </div>
                {task.summary && (
                  <div className="mt-1 break-words text-[11px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                    {task.summary}
                  </div>
                )}
                {task.ns.length > 0 && (
                  <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">
                    {task.ns.join(' / ')}
                  </div>
                )}
                {task.error && (
                  <div className="mt-1 text-[10px] leading-relaxed text-[var(--color-text-muted)]">
                    {task.error}
                  </div>
                )}
              </div>
              <span className="pt-0.5">{statusIcon(task.status)}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function StateSnapshotView({ runState }: { runState?: DeepAgentsRunState }) {
  const snapshot = runState?.latestValues ?? {}
  const todos = Array.isArray(snapshot.todos) ? snapshot.todos : []
  const answer = String(snapshot.answer || '').trim()
  const messagesCount = Number(snapshot.messages_count || 0)
  const todosCount = Number(snapshot.todos_count || todos.length || 0)
  const plan = snapshot.plan
  const planText =
    typeof plan === 'string'
      ? plan
      : plan != null
        ? JSON.stringify(plan)
        : ''

  if (!Object.keys(snapshot).length) {
    return (
      <p id="execution-pane-state" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        No state snapshot yet.
      </p>
    )
  }

  return (
    <div id="execution-pane-state" className="space-y-2 text-[11px]">
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span className="font-medium">Latest values</span>
        <span>{runState?.parts.length ?? 0} parts</span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <RuntimeStat label="Messages" value={String(messagesCount)} />
        <RuntimeStat label="Todos" value={String(todosCount)} />
      </div>

      {runState?.runId && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
          <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Run id
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-[var(--color-text)]">
            {runState.runId}
          </div>
        </section>
      )}

      {answer && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
          <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Answer snapshot
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-[var(--color-text)]">
            {answer}
          </div>
        </section>
      )}

      {todos.length > 0 && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
          <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Todos
          </div>
          <ul className="mt-1 space-y-1">
            {todos.slice(0, 6).map((todo, index) => (
              <li
                key={`todo-${index}`}
                className="rounded-md bg-[var(--color-bg-elevated)] px-2 py-1 text-[11px] leading-relaxed text-[var(--color-text)]"
              >
                {typeof todo === 'string' ? todo : JSON.stringify(todo)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {planText && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
          <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Plan
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-[var(--color-text)] [overflow-wrap:anywhere]">
            {planText}
          </div>
        </section>
      )}
    </div>
  )
}

function RuntimeStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1 text-[13px] font-semibold text-[var(--color-text)]">{value}</div>
    </div>
  )
}
