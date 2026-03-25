import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
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
  graphNodesFromRunState,
  subagentSnapshotsFromRunState,
  taskSnapshotsFromRunState,
} from '../executionEventUtils'
import { useExecutionPaneStore } from '../stores/executionPaneStore'
import { ProviderIcon } from './ProviderIcon'

interface ExecutionPaneProps {
  runState?: DeepAgentsRunState
  isStreaming: boolean
  compact?: boolean
}

type ExecutionTab = 'graph' | 'tools' | 'state' | 'agents'

export function ExecutionPane({
  runState,
  isStreaming,
  compact = false,
}: ExecutionPaneProps) {
  const { t } = useChatI18n()
  const { open } = useExecutionPaneStore()
  const graphNodes = useMemo(
    () => graphNodesFromRunState(runState),
    [runState],
  )
  const hasExecution = graphNodes.length > 0 || (runState?.parts.length ?? 0) > 0
  const taskSnapshots = useMemo(
    () => taskSnapshotsFromRunState(runState),
    [runState],
  )
  const toolSnapshots = useMemo(
    () => taskSnapshots.filter((task) => task.kind === 'tool'),
    [taskSnapshots],
  )
  const subagentSnapshots = useMemo(
    () => subagentSnapshotsFromRunState(runState),
    [runState],
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
        compact ? 'mt-1 w-full border-t border-[var(--color-border)]' : 'hidden min-w-0 max-w-sm lg:flex',
        compact
          ? open
            ? 'h-56'
            : 'h-7'
          : open
            ? 'w-[320px]'
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
                <ExecutionTabButton
                  id="agents"
                  active={tab === 'agents'}
                  label="Agents"
                  disabled={subagentSnapshots.length === 0}
                  onClick={() => subagentSnapshots.length > 0 && setTab('agents')}
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
                  <RunGraphView runState={runState} isStreaming={isStreaming} />
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
                <div
                  className={cn(
                    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
                    tab === 'agents'
                      ? 'pointer-events-auto translate-y-0 opacity-100'
                      : 'pointer-events-none translate-y-1 opacity-0',
                  )}
                >
                  <SubagentView subagents={subagentSnapshots} />
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

function GraphNodeIcon({ kind }: { kind: 'start' | 'tool' | 'model' | 'middleware' | 'final' | 'error' }) {
  if (kind === 'tool') return <Hammer size={12} className="text-[var(--color-text)]" />
  if (kind === 'model') return <Bot size={12} className="text-[var(--color-text)]" />
  if (kind === 'middleware') return <Workflow size={12} className="text-[var(--color-text)]" />
  if (kind === 'final') return <CheckCircle2 size={12} className="text-[var(--color-text)]" />
  if (kind === 'error') return <XCircle size={12} className="text-[var(--color-text)]" />
  return <GitBranch size={12} className="text-[var(--color-text)]" />
}

function RunGraphView({
  runState,
  isStreaming,
}: {
  runState?: DeepAgentsRunState
  isStreaming: boolean
}) {
  const { t } = useChatI18n()
  const nodes = useMemo(() => graphNodesFromRunState(runState), [runState])

  if (!nodes.length) {
    return (
      <p id="execution-pane-graph" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {t('trace.executionPane.emptyDetail')}
      </p>
    )
  }

  const activeIndex = isStreaming ? Math.max(0, nodes.length - 1) : -1

  return (
    <div id="execution-pane-graph" className="space-y-2 text-[11px]">
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span className="font-medium">Run graph</span>
        <span>{isStreaming ? 'live' : `${nodes.length} nodes`}</span>
      </div>

      <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {nodes.map((node, index) => (
            <div key={node.key} className="flex items-center gap-2">
              <motion.div
                initial={{ opacity: 0, y: 6, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.18, delay: Math.min(index * 0.04, 0.24) }}
                className={cn(
                  'group relative min-w-[132px] rounded-2xl border px-3 py-2',
                  activeIndex === index
                    ? 'border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)]'
                    : 'border-[var(--color-border)] bg-[var(--color-panel-alt)]',
                )}
              >
                {activeIndex === index && (
                  <motion.span
                    className="absolute inset-0 rounded-2xl border border-[var(--color-border-strong)]"
                    initial={{ opacity: 0.16, scale: 0.96 }}
                    animate={{ opacity: 0.34, scale: 1.02 }}
                    transition={{ repeat: Infinity, repeatType: 'reverse', duration: 0.9 }}
                  />
                )}
                <div className="relative flex items-center gap-2">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)]">
                    <GraphNodeIcon kind={node.kind} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[11px] font-semibold text-[var(--color-text)]">
                      {node.title}
                    </div>
                    <div className="mt-0.5 truncate text-[10px] text-[var(--color-text-muted)]">
                      {node.status || 'ready'}
                    </div>
                  </div>
                </div>
              </motion.div>
              {index < nodes.length - 1 && (
                <div className="flex min-w-[26px] justify-center">
                  <motion.div
                    className="h-px w-8 bg-[var(--color-border-strong)]"
                    initial={{ scaleX: 0.5, opacity: 0.4 }}
                    animate={{ scaleX: 1, opacity: 0.9 }}
                    transition={{ duration: 0.24, delay: Math.min(index * 0.05, 0.3) }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <ol className="space-y-1.5">
        <AnimatePresence initial={false}>
          {nodes.map((node, index) => (
            <motion.li
              key={node.key}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18 }}
              className={cn(
                'rounded-xl border px-2.5 py-2',
                activeIndex === index
                  ? 'border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)]'
                  : 'border-[var(--color-border)] bg-[var(--color-panel)]',
              )}
            >
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)]">
                  <GraphNodeIcon kind={node.kind} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[var(--color-text-muted)]">{index + 1}.</span>
                    <span className="truncate text-[11px] font-semibold text-[var(--color-text)]">
                      {node.title}
                    </span>
                    <span className="text-[10px] text-[var(--color-text-muted)]">{node.status}</span>
                  </div>
                  {node.summary && (
                    <div className="mt-1 break-words text-[10px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                      {node.summary}
                    </div>
                  )}
                </div>
                <span className="pt-0.5">{statusIcon(node.status)}</span>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </div>
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
        <StateStatCard label="Messages" value={String(messagesCount)} />
        <StateStatCard label="Todos" value={String(todosCount)} />
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

function SubagentView({
  subagents,
}: {
  subagents: ReturnType<typeof subagentSnapshotsFromRunState>
}) {
  if (!subagents.length) {
    return (
      <p id="execution-pane-agents" className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        No subagent namespaces yet.
      </p>
    )
  }

  return (
    <div id="execution-pane-agents" className="space-y-2 text-[11px]">
      <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span className="font-medium">Subagents</span>
        <span>{subagents.length}</span>
      </div>
      <ul className="space-y-1.5">
        {subagents.map((item) => (
          <li key={item.key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
            <div className="flex items-start gap-2">
              <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
                <Bot size={12} className="text-[var(--color-text)]" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                    {item.label}
                  </span>
                  <span className="text-[11px] text-[var(--color-text-muted)]">{item.status || '-'}</span>
                </div>
                <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">
                  {item.taskCount} task{item.taskCount === 1 ? '' : 's'}
                </div>
              </div>
              <span className="pt-0.5">{statusIcon(item.status)}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function StateStatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1 text-[13px] font-semibold text-[var(--color-text)]">{value}</div>
    </div>
  )
}
