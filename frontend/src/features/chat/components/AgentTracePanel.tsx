import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  Compass,
  Database,
  Globe2,
  Search,
  Sparkles,
  XCircle,
} from 'lucide-react'
import type { AelinToolStep } from '@/shared/api/types'
import { cn } from '@/shared/utils/cn'
import { useChatI18n } from '../chatI18n'

const STEP_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  intent_lens: Brain,
  plan_critic: Compass,
  query_decomposer: Search,
  local_search: Database,
  file_memory_search: Database,
  web_search: Globe2,
  message_hub: CircleDashed,
  generation: Sparkles,
  reply_verifier: CheckCircle2,
}

function compactTrace(trace: AelinToolStep[]): AelinToolStep[] {
  const out: AelinToolStep[] = []
  const indexByStage = new Map<string, number>()
  for (const step of trace) {
    const stage = String(step.stage || '').trim()
    if (!stage) continue
    const idx = indexByStage.get(stage)
    if (idx == null) {
      indexByStage.set(stage, out.length)
      out.push(step)
      continue
    }
    out[idx] = step
  }
  return out
}

function stageLabel(stage: string): string {
  return stage
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (m) => m.toUpperCase())
}

export function AgentTracePanel({
  trace,
  live = false,
}: {
  trace: AelinToolStep[]
  live?: boolean
}) {
  const [open, setOpen] = useState(live)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const wasRunningRef = useRef(false)
  const items = useMemo(() => compactTrace(trace), [trace])
  const preview = items.slice(-4)
  const runningCount = items.filter((it) => String(it.status || '').toLowerCase() === 'running').length
  const isRunning = live || runningCount > 0
  const { t } = useChatI18n()

  useEffect(() => {
    if (live) setOpen(true)
  }, [live])

  useEffect(() => {
    if (!open || !bodyRef.current) return
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [open, items, live])

  useEffect(() => {
    if (wasRunningRef.current && !isRunning) {
      setOpen(false)
    }
    wasRunningRef.current = isRunning
  }, [isRunning])

  if (!items.length) return null

  return (
    <section className="mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-2.5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full min-w-0 items-center justify-between rounded-lg px-1 text-left"
      >
        <div className="flex items-center gap-2">
          <span className={cn('inline-flex h-2 w-2 rounded-full', live || runningCount ? 'animate-pulse bg-[var(--color-accent)]' : 'bg-[var(--color-text-muted)]')} />
          <span className="truncate text-[11px] font-semibold tracking-wide text-[var(--color-text)]">
            {t('trace.title')}
          </span>
          <span className="rounded-full border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
            {t('trace.steps', { count: items.length })}
          </span>
        </div>
        {open ? <ChevronUp size={14} className="text-[var(--color-text-muted)]" /> : <ChevronDown size={14} className="text-[var(--color-text-muted)]" />}
      </button>

      {!open && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {preview.map((step, idx) => {
            const status = String(step.status || '').toLowerCase()
            return (
              <span
                key={`${step.stage}-${idx}`}
                className={cn(
                  'rounded-full border px-2 py-1 text-[10px]',
                  status === 'completed' && 'border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-text)]',
                  status === 'running' && 'border-[var(--color-border-strong)] bg-[var(--color-panel)] text-[var(--color-text)] animate-pulse',
                  status === 'failed' && 'border-[var(--color-border-strong)] bg-[var(--color-panel)] text-[var(--color-text)]',
                  status === 'skipped' && 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-muted)]'
                )}
              >
                {stageLabel(step.stage)}
              </span>
            )
          })}
        </div>
      )}

      <div
        ref={bodyRef}
        className={cn(
          'mt-2 pr-1 overflow-hidden transition-[max-height,opacity] duration-250 ease-out',
          open ? 'max-h-[999px] opacity-100' : 'max-h-0 opacity-0 pointer-events-none',
        )}
      >
        <ol className="space-y-1.5">
          {items.map((step, idx) => {
            const status = String(step.status || '').toLowerCase()
            const Icon = STEP_ICON[step.stage] ?? CircleDashed
            return (
              <li
                key={`${step.stage}-${idx}`}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-2"
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
                    <Icon size={12} className="text-[var(--color-text)]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <div className="min-w-0 truncate text-[11px] font-semibold text-[var(--color-text)]">
                        {stageLabel(step.stage)}
                      </div>
                      <span className="text-[10px] text-[var(--color-text-muted)]">
                        {t(
                          status === 'running'
                            ? 'trace.status.running'
                            : status === 'completed'
                              ? 'trace.status.completed'
                              : status === 'skipped'
                                ? 'trace.status.skipped'
                                : status === 'failed'
                                  ? 'trace.status.failed'
                                  : 'trace.status.unknown',
                        )}
                      </span>
                    </div>
                    {step.detail && (
                      <div className="mt-0.5 break-words text-[10px] leading-relaxed text-[var(--color-text-muted)] [overflow-wrap:anywhere]">
                        {step.detail}
                      </div>
                    )}
                  </div>
                  <span className="pt-0.5">
                    {status === 'completed' && <CheckCircle2 size={13} className="text-[var(--color-text)]" />}
                    {status === 'running' && <CircleDashed size={13} className="animate-spin text-[var(--color-text)]" />}
                    {status === 'failed' && <XCircle size={13} className="text-[var(--color-text)]" />}
                  </span>
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
