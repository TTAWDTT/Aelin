import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronUp, CircleDashed, Search, Wrench, XCircle } from 'lucide-react'
import type { AelinToolStep } from '@/shared/api/types'
import { cn } from '@/shared/utils/cn'

type StageStatus = 'waiting' | 'running' | 'success' | 'error'
type StageEventTone = 'progress' | 'info' | 'success' | 'error'

type StageCard = {
  key: string
  title: string
  status: StageStatus
  toolName: string
  runCount: number
  hitCount: number
  latencyMs: number
  startedAt: number
  endedAt: number
  paramsText: string
  currentText: string
  currentTone: StageEventTone
  debugText: string
}

const RUNNING_STATUSES = new Set(['running', 'in_progress'])
const SUCCESS_STATUSES = new Set(['completed'])
const ERROR_STATUSES = new Set(['failed'])
const IGNORED_STAGES = new Set([
  'agent_loop',
  'agent_loop_round',
  'tool_scheduler',
  'agent_loop_read_batch',
  'agent_loop_tool',
  'intent_router',
  'model_decision',
  'forced_tool',
])

const STATUS_LABEL: Record<StageStatus, string> = {
  waiting: '等待中',
  running: '⏳ 运行中',
  success: '✓ 完成',
  error: '✕ 失败',
}

function normalizeText(text: unknown): string {
  return String(text || '').trim()
}

function normalizeStage(raw: unknown): string {
  return normalizeText(raw).toLowerCase()
}

function normalizeStatus(raw: unknown): string {
  return normalizeText(raw).toLowerCase()
}

function compactText(text: string, limit = 160): string {
  const oneLine = normalizeText(text).replace(/\s+/g, ' ')
  if (!oneLine) return ''
  if (oneLine.length <= limit) return oneLine
  return `${oneLine.slice(0, Math.max(0, limit - 1))}…`
}

function parseJson(text: string): unknown {
  const raw = normalizeText(text)
  if (!raw || (!raw.startsWith('{') && !raw.startsWith('[') && !raw.startsWith('"'))) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function parseDetailMap(detail: string): Record<string, string> {
  const output: Record<string, string> = {}
  const raw = normalizeText(detail)
  if (!raw) return output
  for (const item of raw.split(';').map((part) => part.trim()).filter(Boolean)) {
    const splitAt = item.indexOf('=')
    if (splitAt <= 0) continue
    const key = item.slice(0, splitAt).trim()
    const value = item.slice(splitAt + 1).trim()
    if (!key) continue
    output[key] = value
  }
  return output
}

function toStatus(rawStatus: string): StageStatus | null {
  if (RUNNING_STATUSES.has(rawStatus)) return 'running'
  if (SUCCESS_STATUSES.has(rawStatus)) return 'success'
  if (ERROR_STATUSES.has(rawStatus)) return 'error'
  return null
}

function resolveToolName(stage: string): string {
  if (!stage.startsWith('tool_call:')) return ''
  return normalizeText(stage.split(':')[1] || '')
}

function classifyStage(step: AelinToolStep): { key: string; title: string; toolName: string } | null {
  const stage = normalizeStage(step.stage)
  if (!stage || IGNORED_STAGES.has(stage) || stage === 'model_plan') return null

  const toolName = resolveToolName(stage)
  if (stage === 'attachment_prefetch') return { key: 'parse_attachment', title: '解析附件', toolName: 'attachment_prefetch' }
  if (stage === 'generation') return { key: 'organize_results', title: '整理检索结果', toolName: '' }
  if (stage === 'final_answer') return { key: 'generate_answer', title: '生成回答', toolName: '' }

  if (toolName === 'attachment_search') return { key: 'search_attachment', title: '搜索附件内容', toolName }
  if (toolName === 'web_search' || stage === 'web_search') return { key: 'search_web', title: '搜索网页内容', toolName: toolName || 'web_search' }
  if (toolName === 'file_memory_search' || stage === 'file_memory_search') return { key: 'search_attachment', title: '搜索附件内容', toolName: toolName || 'file_memory_search' }
  if (toolName === 'local_search' || stage === 'local_search') return { key: 'search_attachment', title: '搜索附件内容', toolName: toolName || 'local_search' }
  if (toolName) return { key: `tool_${toolName}`, title: `调用 ${toolName}`, toolName }
  return null
}

function formatElapsed(ms: number): string {
  const safe = Math.max(0, Math.round(ms))
  if (safe < 1000) return `${safe} ms`
  const sec = safe / 1000
  return `${sec.toFixed(sec < 10 ? 1 : 0)} s`
}

function stageSummary(card: StageCard, nowTs: number): string {
  const parts: string[] = []
  if (card.runCount > 1) parts.push(`已执行 ${card.runCount} 次`)
  if (card.hitCount > 0) parts.push(`命中 ${card.hitCount} 条内容`)
  if (card.latencyMs > 0) parts.push(`${card.latencyMs} ms`)
  if (card.status === 'running' && card.startedAt > 0) {
    parts.push(`运行 ${formatElapsed(Math.max(0, nowTs - card.startedAt))}`)
  }
  if (parts.length === 0) {
    if (card.status === 'waiting') return '等待执行…'
    if (card.status === 'running') return '处理中…'
    if (card.status === 'error') return '执行失败'
    return '已完成'
  }
  return parts.join(' · ')
}

function runningDots(nowTs: number): string {
  const frame = Math.floor(nowTs / 240) % 4
  return '.'.repeat(frame === 0 ? 1 : frame)
}

function runningVerb(card: StageCard, nowTs: number): string {
  const frames = card.key === 'parse_attachment'
    ? ['正在读取附件', '正在解析文本', '正在建立索引']
    : card.key === 'search_attachment'
      ? ['正在检索附件内容', '正在筛选相关片段', '正在补充结果']
      : card.key === 'organize_results'
        ? ['正在整理检索结果', '正在归并片段', '正在压缩上下文']
        : card.key === 'generate_answer'
          ? ['正在生成回答', '正在组织表述', '正在补全内容']
          : ['正在执行', '正在处理中', '正在更新状态']
  return frames[Math.floor(nowTs / 720) % frames.length] || frames[0]
}

function animatedProgressText(text: string, nowTs: number): string {
  const normalized = normalizeText(text)
  if (!normalized) return ''
  const noDots = normalized.replace(/[.。…]+$/u, '')
  return `${noDots}${runningDots(nowTs)}`
}

function setCurrentState(card: StageCard, text: string, tone: StageEventTone): void {
  const normalized = normalizeText(text)
  if (!normalized) {
    card.currentText = ''
    card.currentTone = tone
    return
  }
  card.currentText = normalized
  card.currentTone = tone
}

function parsePositiveNumber(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return 0
  return Math.round(parsed)
}

function extractKeyParams(detailMap: Record<string, string>): string {
  const argsText = normalizeText(detailMap.args)
  const parsed = parseJson(argsText)
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const data = parsed as Record<string, unknown>
    const lines: string[] = []
    const query = normalizeText(data.query)
    if (query) lines.push(`query: ${compactText(query, 120)}`)
    const topK = parsePositiveNumber(data.top_k ?? data.k ?? data.limit)
    if (topK > 0) lines.push(`top_k: ${topK}`)
    const ids = Array.isArray(data.attachment_ids) ? data.attachment_ids : []
    if (ids.length > 0) lines.push(`attachment_ids: [${ids.slice(0, 8).join(', ')}${ids.length > 8 ? ', …' : ''}]`)
    return lines.join('\n')
  }
  return ''
}

function extractHitCount(detailMap: Record<string, string>): number {
  const direct = parsePositiveNumber(detailMap.hits || detailMap.hit_count || detailMap.total || detailMap.count || detailMap.matched)
  if (direct > 0) return direct
  const summary = normalizeText(detailMap.summary || detailMap.effect_summary || detailMap.message)
  const match = summary.match(/(?:hits|命中)\s*[=:]?\s*(\d+)/i) || summary.match(/(\d+)\s*条/)
  if (!match) return 0
  return parsePositiveNumber(match[1])
}

function extractReadableSummary(detailMap: Record<string, string>): string {
  const summaryRaw = normalizeText(detailMap.effect_summary || detailMap.summary || detailMap.message || detailMap.error)
  if (!summaryRaw) return ''
  const parsed = parseJson(summaryRaw)
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const payload = parsed as Record<string, unknown>
    if (payload.ok === true) return '找到可用内容片段'
    if (payload.ok === false) return '未找到可用内容'
    return ''
  }
  return compactText(summaryRaw, 140)
}

function extractStructuredProgressText(card: StageCard, detailMap: Record<string, string>): string {
  const currentAction = decodeCompactValue(detailMap.current_action)
  const partial = decodeCompactValue(detailMap.partial)
  const foundCount = parsePositiveNumber(detailMap.found_count)
  const processed = parsePositiveNumber(detailMap.processed)
  const matched = parsePositiveNumber(detailMap.matched)
  const total = parsePositiveNumber(detailMap.total)
  const progressLabel = normalizeText(detailMap.progress_label)
  const progressText = processed > 0 && total > 0 ? `（${processed}/${total}）` : total > 0 ? `（0/${total}）` : ''

  if (card.key === 'search_attachment') {
    const effectiveCount = Math.max(foundCount, matched)
    if (progressLabel === 'found_candidates' && effectiveCount > 0) return `已找到 ${effectiveCount} 条候选片段${progressText}`
    if (progressLabel === 'organizing') return effectiveCount > 0 ? `正在整理 ${effectiveCount} 条候选结果` : `正在整理检索结果${progressText}`
    if (progressLabel === 'loading_candidates') return `正在读取附件${progressText}`
    if (progressLabel === 'scanning_candidates' || progressLabel === 'searching') {
      if (effectiveCount > 0) return `正在检索附件内容${progressText} · 已命中 ${effectiveCount} 条`
      return `正在检索附件内容${progressText}`
    }
  }
  if (card.key === 'parse_attachment') {
    if (progressLabel === 'parsing') return '正在解析附件'
    if (progressLabel === 'indexing') return '正在切分内容并建立索引'
    if (progressLabel === 'caching') return '正在写入检索缓存'
  }
  if (currentAction) return currentAction
  if (partial) return partial
  return ''
}

function decodeCompactValue(text: string): string {
  const raw = normalizeText(text)
  if (!raw) return ''
  const parsed = parseJson(raw)
  if (typeof parsed === 'string') return normalizeText(parsed)
  return raw
}

function buildTimeline(trace: AelinToolStep[]): { planText: string; cards: StageCard[] } {
  const cardOrder: string[] = []
  const cardsByKey = new Map<string, StageCard>()
  let planText = ''

  const ensureCard = (key: string, title: string, toolName: string): StageCard => {
    const existing = cardsByKey.get(key)
    if (existing) return existing
    const created: StageCard = {
      key,
      title,
      status: 'waiting',
      toolName: toolName || '',
      runCount: 0,
      hitCount: 0,
      latencyMs: 0,
      startedAt: 0,
      endedAt: 0,
      paramsText: '',
      currentText: '',
      currentTone: 'info',
      debugText: '',
    }
    cardsByKey.set(key, created)
    cardOrder.push(key)
    return created
  }

  for (const step of trace) {
    const stepTs = Number.isFinite(Number(step.ts)) ? Number(step.ts) : Date.now()
    const stage = normalizeStage(step.stage)
    if (!stage) continue
    if (stage === 'model_plan') {
      const plan = normalizeText(step.detail)
      if (plan) planText = `执行计划：${compactText(plan, 220)}`
      continue
    }

    const classified = classifyStage(step)
    if (!classified) continue
    const card = ensureCard(classified.key, classified.title, classified.toolName)
    const status = toStatus(normalizeStatus(step.status))
    if (status) {
      if (status === 'running') {
        if (card.startedAt <= 0) card.startedAt = stepTs
        card.endedAt = 0
        if (card.status !== 'error') card.status = 'running'
      } else if (status === 'success') {
        if (card.startedAt <= 0) card.startedAt = stepTs
        card.endedAt = stepTs
        if (card.status !== 'error') card.status = 'success'
      } else if (status === 'error') {
        if (card.startedAt <= 0) card.startedAt = stepTs
        card.endedAt = stepTs
        card.status = 'error'
      }
    }

    if (classified.toolName) card.toolName = classified.toolName
    const detailMap = parseDetailMap(step.detail || '')
    card.debugText = normalizeText(step.detail || '')
    const latencyMs = parsePositiveNumber(detailMap.latency_ms || detailMap.latency)
    if (latencyMs > 0) card.latencyMs = latencyMs
    const hits = extractHitCount(detailMap)
    if (hits > 0) card.hitCount = Math.max(card.hitCount, hits)
    const keyParams = extractKeyParams(detailMap)
    if (keyParams) card.paramsText = keyParams
    const partialText = compactText(
      decodeCompactValue(detailMap.partial || detailMap.progress || detailMap.message),
      160,
    )

    if (status === 'running') {
      const structuredProgressText = extractStructuredProgressText(card, detailMap)
      if (structuredProgressText) setCurrentState(card, structuredProgressText, 'progress')
      else if (partialText) setCurrentState(card, partialText, 'progress')
      else if (card.key === 'parse_attachment') setCurrentState(card, '正在读取附件...', 'progress')
      else if (card.key === 'search_attachment') setCurrentState(card, '正在检索...', 'progress')
      else if (card.key === 'organize_results') setCurrentState(card, '正在整理检索结果...', 'progress')
      else if (card.key === 'generate_answer') setCurrentState(card, '正在生成回答...', 'progress')
      else setCurrentState(card, '正在执行...', 'progress')
      continue
    }

    if (status === 'success') {
      if (card.toolName === 'attachment_search') card.runCount += 1
      if (card.key === 'parse_attachment') {
        setCurrentState(card, hits > 0 ? '' : '附件解析完成', 'success')
      } else if (card.key === 'search_attachment') {
        if (hits > 0) setCurrentState(card, '', 'success')
        else setCurrentState(card, extractReadableSummary(detailMap) || '检索完成', 'success')
      } else if (card.key === 'organize_results') {
        setCurrentState(card, '', 'success')
      } else if (card.key === 'generate_answer') {
        setCurrentState(card, '', 'success')
      } else {
        setCurrentState(card, extractReadableSummary(detailMap) || '步骤完成', 'success')
      }
      continue
    }

    if (status === 'error') {
      const reason = compactText(
        normalizeText(detailMap.error || detailMap.blocked || detailMap.message || step.detail || '未知错误'),
        140,
      )
      setCurrentState(card, `执行失败：${reason}`, 'error')
    }
  }

  const cards = cardOrder
    .map((key) => cardsByKey.get(key))
    .filter((item): item is StageCard => Boolean(item))
    .filter((card) => card.startedAt > 0 || Boolean(card.currentText || card.paramsText))

  if (!planText && cards.some((card) => card.key === 'parse_attachment' || card.key === 'search_attachment')) {
    planText = '执行计划：解析附件 → 搜索附件内容 → 整理检索结果 → 生成回答'
  }
  return { planText, cards }
}

function statusClass(status: StageStatus): string {
  if (status === 'waiting') return 'text-[var(--color-text-muted)]'
  if (status === 'running') return 'text-[var(--color-accent)]'
  if (status === 'error') return 'text-[#d9534f]'
  return 'text-[#2f8e53]'
}

function toneClass(tone: StageEventTone): string {
  if (tone === 'error') return 'text-[#d9534f]'
  if (tone === 'progress') return 'text-[var(--color-text-muted)]'
  if (tone === 'success') return 'text-[#2f8e53]'
  return 'text-[var(--color-text)]'
}

function RunningLabel({ card, nowTs }: { card: StageCard; nowTs: number }) {
  return (
    <span className="inline-flex items-center gap-1 font-semibold text-[var(--color-accent)] animate-pulse">
      <span>{`${STATUS_LABEL.running} · ${runningVerb(card, nowTs)}`}</span>
      <span className="inline-block min-w-[14px] text-left">{runningDots(nowTs)}</span>
    </span>
  )
}

function RunningSummary({ card, nowTs }: { card: StageCard; nowTs: number }) {
  const elapsed = card.startedAt > 0 ? formatElapsed(Math.max(0, nowTs - card.startedAt)) : '0 ms'
  const parts: string[] = []
  if (card.runCount > 1) parts.push(`已执行 ${card.runCount} 次`)
  if (card.hitCount > 0) parts.push(`命中 ${card.hitCount} 条内容`)
  if (card.latencyMs > 0) parts.push(`${card.latencyMs} ms`)
  return (
    <span className="inline-flex items-center gap-1 text-[var(--color-text-muted)]">
      {parts.length > 0 && <span>{parts.join(' · ')}</span>}
      <span className="text-[var(--color-accent)]">{`· ${runningVerb(card, nowTs)} ${runningDots(nowTs)}`}</span>
      <span>{`· ${elapsed}`}</span>
    </span>
  )
}

function TypewriterText({ text, active, className }: { text: string; active: boolean; className?: string }) {
  const normalized = String(text || '')
  const [visible, setVisible] = useState(active ? '' : normalized)

  useEffect(() => {
    if (!active) {
      setVisible(normalized)
      return
    }
    if (!normalized) {
      setVisible('')
      return
    }
    let index = 0
    setVisible('')
    const chunk = Math.max(1, Math.ceil(normalized.length / 32))
    const timer = window.setInterval(() => {
      index += chunk
      if (index >= normalized.length) {
        setVisible(normalized)
        window.clearInterval(timer)
        return
      }
      setVisible(normalized.slice(0, index))
    }, 24)
    return () => window.clearInterval(timer)
  }, [normalized, active])

  return <span className={className}>{visible}</span>
}

function EventText({
  text,
  active,
  animateProgress = false,
  nowTs,
  className,
}: {
  text: string
  active: boolean
  animateProgress?: boolean
  nowTs: number
  className?: string
}) {
  const displayText = animateProgress ? animatedProgressText(text, nowTs) : text
  return <TypewriterText text={displayText} active={active} className={className} />
}

export function AgentTracePanel({ trace, live = false }: { trace: AelinToolStep[]; live?: boolean }) {
  const timeline = useMemo(() => buildTimeline(trace), [trace])
  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({})
  const [visibleCardKeys, setVisibleCardKeys] = useState<string[]>([])
  const [nowTs, setNowTs] = useState<number>(() => Date.now())
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const revealTimerRef = useRef<number | null>(null)
  const signature = useMemo(
    () => timeline.cards.map((card) => `${card.key}:${card.status}:${card.currentText}:${card.latencyMs}:${card.hitCount}`).join('|'),
    [timeline.cards],
  )
  const startedCards = useMemo(
    () => timeline.cards.filter((card) => card.startedAt > 0 || card.status !== 'waiting'),
    [timeline.cards],
  )
  const visibleCards = useMemo(
    () => timeline.cards.filter((card) => visibleCardKeys.includes(card.key)),
    [timeline.cards, visibleCardKeys],
  )

  useEffect(() => {
    return () => {
      if (revealTimerRef.current) {
        window.clearTimeout(revealTimerRef.current)
        revealTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const nextKeys = startedCards.map((card) => card.key)
    if (!live) {
      setVisibleCardKeys(nextKeys)
      return
    }

    setVisibleCardKeys((prev) => {
      const visibleSet = new Set(prev)
      const missingKeys = nextKeys.filter((key) => !visibleSet.has(key))
      const filteredPrev = prev.filter((key) => nextKeys.includes(key))

      if (missingKeys.length === 0) return filteredPrev

      const nextVisible = [...filteredPrev, missingKeys[0]]

      if (revealTimerRef.current) {
        window.clearTimeout(revealTimerRef.current)
        revealTimerRef.current = null
      }

      if (missingKeys.length > 1) {
        revealTimerRef.current = window.setTimeout(() => {
          setVisibleCardKeys((current) => {
            const currentSet = new Set(current)
            const pendingKeys = nextKeys.filter((key) => !currentSet.has(key))
            if (pendingKeys.length === 0) return current.filter((key) => nextKeys.includes(key))
            return [...current.filter((key) => nextKeys.includes(key)), pendingKeys[0]]
          })
        }, 140)
      }

      return nextVisible
    })
  }, [live, startedCards])

  useEffect(() => {
    setExpandedMap((prev) => {
      const next: Record<string, boolean> = { ...prev }
      for (const card of visibleCards) {
        if (!(card.key in next)) next[card.key] = true
        if (card.status === 'running') next[card.key] = true
        else if (card.status === 'error') next[card.key] = true
      }
      return next
    })
  }, [signature, visibleCards, live])

  useEffect(() => {
    if (!live) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [live, visibleCardKeys, signature, timeline.planText])

  useEffect(() => {
    if (!live) return
    if (!timeline.cards.some((card) => card.status === 'running')) return
    const timer = window.setInterval(() => setNowTs(Date.now()), 180)
    return () => window.clearInterval(timer)
  }, [live, signature, timeline.cards])

  if (!timeline.planText && visibleCards.length === 0) return null

  return (
    <section className="mt-3 space-y-2.5">
      {timeline.planText && (
        <p className="text-[13px] leading-relaxed text-[var(--color-text)]">{timeline.planText}</p>
      )}

      {visibleCards.map((card) => {
        const isExpanded = expandedMap[card.key] ?? card.status === 'running'
        const panelId = `agent-trace-panel-${card.key}`
        return (
          <article key={card.key} className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)]">
            <div className={cn('px-3 py-2.5', card.status === 'running' && 'shadow-[0_0_0_1px_color-mix(in_srgb,var(--color-accent)_24%,transparent)]')}>
              <button
                type="button"
                className="flex w-full items-start gap-2 text-left"
                aria-expanded={isExpanded}
                aria-controls={panelId}
                onClick={() => setExpandedMap((prev) => ({ ...prev, [card.key]: !(prev[card.key] ?? card.status === 'running') }))}
              >
                <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-panel)]">
                  {card.toolName ? <Wrench size={12} className="text-[var(--color-text)]" /> : <Search size={12} className="text-[var(--color-text)]" />}
                </span>

                <span className="min-w-0 flex-1 space-y-0.5">
                  <span className={cn('block text-[13px] font-medium', card.status === 'running' ? 'text-[var(--color-accent)] animate-pulse' : 'text-[var(--color-text)]')}>
                    {card.title}
                  </span>
                  {(card.status === 'running' || card.status === 'error') && (
                    <span className={cn('block text-[11px]', statusClass(card.status), card.status === 'running' && 'font-semibold')}>
                      {card.status === 'running' ? <RunningLabel card={card} nowTs={nowTs} /> : STATUS_LABEL[card.status]}
                    </span>
                  )}
                  <span className="block text-[11px] text-[var(--color-text-muted)]">
                    {card.status === 'running' ? <RunningSummary card={card} nowTs={nowTs} /> : stageSummary(card, nowTs)}
                  </span>
                  {card.currentText && (
                    <EventText
                      text={card.currentText}
                      active={live && card.status === 'running'}
                      animateProgress={card.status === 'running' && card.currentTone === 'progress'}
                      nowTs={nowTs}
                      className={cn('block text-[12px]', toneClass(card.currentTone))}
                    />
                  )}
                </span>

                <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-[var(--color-text-muted)]">
                  {card.status === 'success' && <CheckCircle2 size={13} className="text-[#2f8e53]" />}
                  {card.status === 'error' && <XCircle size={13} className="text-[#d9534f]" />}
                  {card.status === 'running' && <CircleDashed size={13} className="animate-spin text-[var(--color-accent)]" />}
                  {card.status === 'waiting' && <CircleDashed size={13} className="text-[var(--color-text-muted)]" />}
                  {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                </span>
              </button>

              {(card.paramsText || card.debugText) && isExpanded && (
                <div id={panelId} className="mt-2 border-t border-[var(--color-border)] pt-2 text-[11px] leading-relaxed">
                  <div className="space-y-2">
                    {card.toolName && (
                      <div className="text-[var(--color-text-muted)]">
                        <span className="mr-2">调用</span>
                        <span className="text-[var(--color-text)]">{card.toolName}</span>
                      </div>
                    )}
                    {card.paramsText && (
                      <div className="space-y-1">
                        <div className="text-[var(--color-text-muted)]">参数</div>
                        <pre className="whitespace-pre-wrap break-words rounded-md bg-[var(--color-surface)] px-2 py-1.5 text-[11px] text-[var(--color-text)]">
                          {card.paramsText}
                        </pre>
                      </div>
                    )}
                    {card.debugText && card.status !== 'running' && (
                      <details className="text-[var(--color-text-muted)]">
                        <summary className="cursor-pointer select-none">调试详情</summary>
                        <pre className="mt-1 whitespace-pre-wrap break-words rounded-md bg-[var(--color-surface)] px-2 py-1.5 text-[11px] text-[var(--color-text-muted)]">
                          {card.debugText}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              )}
            </div>
          </article>
        )
      })}

      {live && visibleCards.some((card) => card.status === 'running') && (
        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1.5 text-[11px] text-[var(--color-text-muted)]">
          正在持续更新执行过程...
        </div>
      )}
      <div ref={bottomRef} />
    </section>
  )
}
