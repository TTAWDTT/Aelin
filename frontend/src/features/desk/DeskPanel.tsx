import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinTrackingChangeItem, AelinTrackingItem, DeskFeedItem } from '@/shared/api/types'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { X, ExternalLink, RefreshCw, Search } from 'lucide-react'
import toast from 'react-hot-toast'

export type DeskPanelContext = {
  targetId?: number | null
  source?: string | null
  keyword?: string | null
  title?: string | null
}

type Props = {
  onClose?: () => void
  context?: DeskPanelContext | null
  onClearContext?: () => void
  onSelectContext?: (context: DeskPanelContext) => void
}

type TrackingChangeRow = AelinTrackingChangeItem & {
  target_name: string
  target_source: string
}

const SOURCE_OPTIONS: Array<{ key: string; label: string }> = [
  { key: '', label: '全部来源' },
  { key: 'x', label: 'X' },
  { key: 'weibo', label: '微博' },
  { key: 'xiaohongshu', label: '小红书' },
  { key: 'douyin', label: '抖音' },
  { key: 'bilibili', label: 'Bilibili' },
  { key: 'rss', label: 'RSS' },
  { key: 'web', label: 'Web' },
]

const DESK_SOURCE_SET = new Set(SOURCE_OPTIONS.map((item) => item.key).filter(Boolean))

function normalizeSource(raw: string | null | undefined): string {
  const value = String(raw || '').trim().toLowerCase()
  if (!value) return ''
  if (DESK_SOURCE_SET.has(value)) return value
  if (value === 'xhs') return 'xiaohongshu'
  if (value === 'news' || value === 'website') return 'web'
  return ''
}

export function DeskPanel({ onClose, context, onClearContext, onSelectContext }: Props) {
  const qc = useQueryClient()
  const [trackingStatus, setTrackingStatus] = useState<'all' | 'active' | 'paused' | 'error'>('all')
  const [trackingKeyword, setTrackingKeyword] = useState('')
  const [activeTag, setActiveTag] = useState('all')
  const [items, setItems] = useState<DeskFeedItem[]>([])
  const [cursor, setCursor] = useState<{ at?: string | null; id?: number | null }>({})
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [linkedMode, setLinkedMode] = useState(false)

  const { data: tags, isLoading: tagsLoading, isFetching: tagsFetching } = useQuery({
    queryKey: ['desk-tags'],
    queryFn: () => aelinApi.deskTags(),
    staleTime: 20_000,
  })

  const contextTargetId = useMemo(() => Number(context?.targetId || 0), [context?.targetId])
  const contextSource = useMemo(() => normalizeSource(context?.source), [context?.source])
  const contextKeyword = useMemo(() => String(context?.keyword || '').trim(), [context?.keyword])
  const contextTitle = useMemo(() => String(context?.title || '').trim(), [context?.title])
  const hasContext = Boolean(contextTargetId > 0 || contextSource || contextKeyword || contextTitle)

  const {
    data: linkedChangesData,
    isFetching: linkedChangesFetching,
    refetch: refetchLinkedChanges,
  } = useQuery({
    queryKey: ['desk-linked-changes', contextTargetId],
    queryFn: () => aelinApi.trackingChanges(contextTargetId, { limit: '20' }),
    enabled: hasContext && contextTargetId > 0,
    staleTime: 20_000,
  })

  const {
    data: trackingListData,
    isFetching: trackingListFetching,
  } = useQuery({
    queryKey: ['desk-tracking-list', trackingStatus],
    queryFn: () => aelinApi.trackingList({
      limit: '200',
      ...(trackingStatus !== 'all' ? { status: trackingStatus } : {}),
    }),
    staleTime: 10_000,
    refetchInterval: 30_000,
  })

  const runTrackingNow = useMutation({
    mutationFn: (targetId: number) => aelinApi.trackingRun(targetId),
    onSuccess: (result, targetId) => {
      toast.success(result.message || '已触发运行')
      void qc.invalidateQueries({ queryKey: ['desk-tracking-list'] })
      void qc.invalidateQueries({ queryKey: ['tracking'] })
      void qc.invalidateQueries({ queryKey: ['desk-recent-tracking-changes'] })
      if (targetId > 0) void qc.invalidateQueries({ queryKey: ['desk-linked-changes', targetId] })
    },
    onError: () => toast.error('运行失败'),
  })

  const loadFeed = async (reset: boolean) => {
    const resp = await aelinApi.deskFeed({
      tag: activeTag,
      source: sourceFilter || undefined,
      q: searchQuery || undefined,
      limit: 20,
      before_received_at: reset ? undefined : cursor.at || undefined,
      before_id: reset ? undefined : cursor.id || undefined,
    })
    const rows = resp.items || []
    setItems((prev) => {
      if (reset) return rows
      const map = new Map<number, DeskFeedItem>()
      for (const x of prev) map.set(x.message_id, x)
      for (const x of rows) map.set(x.message_id, x)
      return Array.from(map.values())
    })
    setCursor({ at: resp.next_before_received_at, id: resp.next_before_id })
    setHasMore(Boolean(resp.next_before_received_at && resp.next_before_id))
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchQuery(searchInput.trim())
    }, 250)
    return () => clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    if (!hasContext) {
      if (linkedMode) {
        setActiveTag('all')
        setSourceFilter('')
        setSearchInput('')
        setSearchQuery('')
        setLinkedMode(false)
      }
      return
    }
    setActiveTag('all')
    if (contextSource) setSourceFilter(contextSource)
    if (contextKeyword) {
      setSearchInput(contextKeyword)
      setSearchQuery(contextKeyword)
    }
    setLinkedMode(true)
  }, [hasContext, contextKeyword, contextSource, linkedMode])

  useEffect(() => {
    setItems([])
    setCursor({})
    setHasMore(true)
    void loadFeed(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTag, searchQuery, sourceFilter])

  const followedTags = useMemo(() => tags?.followed ?? [], [tags?.followed])
  const discoverTags = useMemo(() => tags?.discover ?? [], [tags?.discover])
  const recommendedTags = useMemo(() => tags?.recommended ?? [], [tags?.recommended])
  const trackingItems = useMemo<AelinTrackingItem[]>(() => trackingListData?.items ?? [], [trackingListData?.items])
  const linkedChanges = useMemo<AelinTrackingChangeItem[]>(
    () => linkedChangesData?.items ?? [],
    [linkedChangesData?.items]
  )
  const filteredTrackingItems = useMemo<AelinTrackingItem[]>(() => {
    const keyword = trackingKeyword.trim().toLowerCase()
    return trackingItems.filter((item) => {
      const normalizedSource = normalizeSource(item.source || '')
      if (sourceFilter && normalizedSource !== sourceFilter) return false
      if (!keyword) return true
      return `${item.target || ''} ${item.description || ''} ${item.source || ''}`
        .toLowerCase()
        .includes(keyword)
    })
  }, [trackingItems, trackingKeyword, sourceFilter])
  const recentTargetIds = useMemo<number[]>(
    () => filteredTrackingItems
      .map((item) => Number(item.target_id || 0))
      .filter((id) => id > 0)
      .slice(0, 12),
    [filteredTrackingItems]
  )

  const {
    data: recentTrackingChanges,
    isFetching: recentTrackingChangesFetching,
  } = useQuery<TrackingChangeRow[]>({
    queryKey: ['desk-recent-tracking-changes', trackingStatus, sourceFilter || 'all-source', recentTargetIds.join(',')],
    enabled: contextTargetId <= 0 && recentTargetIds.length > 0,
    queryFn: async () => {
      const targetMeta = new Map<number, { target_name: string; target_source: string }>()
      for (const item of filteredTrackingItems) {
        const targetId = Number(item.target_id || 0)
        if (targetId <= 0 || targetMeta.has(targetId)) continue
        targetMeta.set(targetId, {
          target_name: String(item.target || '').trim() || `目标 #${targetId}`,
          target_source: String(item.source || '').trim(),
        })
      }

      const rows = await Promise.all(
        recentTargetIds.map(async (targetId) => {
          const response = await aelinApi.trackingChanges(targetId, { limit: '3' })
          const meta = targetMeta.get(targetId) || { target_name: `目标 #${targetId}`, target_source: '' }
          return (response.items || []).map((item) => ({
            ...item,
            target_name: meta.target_name,
            target_source: meta.target_source,
          }))
        })
      )

      const toTs = (value: string | undefined) => {
        const parsed = Date.parse(String(value || ''))
        return Number.isFinite(parsed) ? parsed : 0
      }

      return rows
        .flat()
        .sort((a, b) => toTs(b.created_at) - toTs(a.created_at))
        .slice(0, 24)
    },
    staleTime: 15_000,
  })

  const firstRowTags = useMemo(() => {
    const seen = new Set<string>(['all'])
    const out: string[] = ['all']
    for (const row of followedTags) {
      const t = String(row.tag || '').trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
    }
    for (const row of discoverTags) {
      const t = String(row.tag || '').trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
    }
    return out.slice(0, 12)
  }, [discoverTags, followedTags])

  const toggleFollow = async (tag: string) => {
    const normalized = String(tag || '').trim()
    if (!normalized) return
    const followed = followedTags.some((x) => x.tag === normalized)
    if (followed) await aelinApi.deskUnfollowTag(normalized)
    else await aelinApi.deskFollowTag(normalized)
    await qc.invalidateQueries({ queryKey: ['desk-tags'] })
  }

  const applyTrackingContext = (item: AelinTrackingItem) => {
    const normalizedSource = normalizeSource(item.source || '')
    const nextContext: DeskPanelContext = {
      targetId: typeof item.target_id === 'number' ? item.target_id : undefined,
      source: normalizedSource || undefined,
      keyword: String(item.query || item.target || '').trim() || undefined,
      title: String(item.target || '').trim() || '追踪联动',
    }
    if (onSelectContext) {
      onSelectContext(nextContext)
      return
    }
    setActiveTag('all')
    setSourceFilter(nextContext.source || '')
    setSearchInput(nextContext.keyword || '')
    setSearchQuery(nextContext.keyword || '')
  }

  const changeStreamRows = useMemo<TrackingChangeRow[]>(() => {
    if (contextTargetId > 0) {
      const target = trackingItems.find((item) => Number(item.target_id || 0) === contextTargetId)
      const targetName = contextTitle || String(target?.target || '').trim() || `目标 #${contextTargetId}`
      const targetSource = contextSource || String(target?.source || '').trim()
      return linkedChanges.map((item) => ({
        ...item,
        target_name: targetName,
        target_source: targetSource,
      }))
    }
    return recentTrackingChanges ?? []
  }, [contextTargetId, contextSource, contextTitle, linkedChanges, recentTrackingChanges, trackingItems])
  const changeStreamLoading = contextTargetId > 0 ? linkedChangesFetching : recentTrackingChangesFetching

  const emptyHint = contextTargetId > 0
    ? '该追踪目标暂无可展示内容，可先查看上方「追踪变更流」或点击「运行」后刷新。'
    : searchQuery || sourceFilter
      ? '暂未命中与当前条件相关的内容，可尝试调整关键词或来源。'
      : '暂无可展示内容。请先绑定内容平台并同步。'

  const trackingStatusLabel = (value: string) => {
    if (value === 'active') return '活跃'
    if (value === 'paused') return '暂停'
    if (value === 'error') return '异常'
    return value || 'unknown'
  }
  const activeSourceLabel = sourceFilter
    ? (SOURCE_OPTIONS.find((item) => item.key === sourceFilter)?.label || sourceFilter)
    : '全部来源'

  return (
    <section className="flex h-full min-h-0 flex-col bg-[var(--color-panel)]">
      <header className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2.5">
        <div className="min-w-0">
          <h2 className="truncate text-[0.92rem] font-semibold">Desk 观察</h2>
          <p className="text-[11px] text-[var(--color-text-muted)]">跨平台内容流 · 时间倒序</p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => {
              setItems([])
              setCursor({})
              setHasMore(true)
              void loadFeed(true)
              if (contextTargetId > 0) void refetchLinkedChanges()
              void qc.invalidateQueries({ queryKey: ['desk-tags'] })
              void qc.invalidateQueries({ queryKey: ['desk-tracking-list'] })
              void qc.invalidateQueries({ queryKey: ['desk-recent-tracking-changes'] })
            }}
            className="aelin-btn h-8 px-2.5 text-[11px]"
            title="刷新"
          >
            <RefreshCw size={13} />
          </button>
          {onClose ? (
            <button onClick={onClose} className="aelin-btn h-8 px-2.5 text-[11px]" title="关闭">
              <X size={14} />
            </button>
          ) : null}
        </div>
      </header>

      {hasContext ? (
        <div className="mx-3 mt-2 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 text-[11px] text-[var(--color-text-muted)]">
              <p className="truncate text-[12px] font-medium text-[var(--color-text)]">{contextTitle || '追踪联动'}</p>
              <p className="truncate">
                {contextTargetId > 0 ? `目标 #${contextTargetId}` : ''}
                {contextTargetId > 0 && (contextSource || contextKeyword) ? ' · ' : ''}
                {contextSource ? `来源: ${SOURCE_OPTIONS.find((x) => x.key === contextSource)?.label || contextSource}` : ''}
                {contextSource && contextKeyword ? ' · ' : ''}
                {contextKeyword ? `关键词: ${contextKeyword}` : ''}
              </p>
            </div>
            {onClearContext ? (
              <button onClick={onClearContext} className="aelin-btn h-7 px-2 text-[11px]">清除联动</button>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="border-b border-[var(--color-border)] px-3 py-2">
        <div className="relative mb-2">
          <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="搜索标题、作者或摘要"
            className="aelin-input h-8 pl-8 text-xs"
            style={{ paddingLeft: '2rem' }}
          />
        </div>

        <div className="mb-2 flex flex-wrap gap-1.5">
          {SOURCE_OPTIONS.map((source) => (
            <button
              key={source.key || 'all-source'}
              onClick={() => setSourceFilter(source.key)}
              className={`rounded-full border px-2.5 py-1 text-[11px] ${
                sourceFilter === source.key
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-[var(--color-bg)]'
                  : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              }`}
            >
              {source.label}
            </button>
          ))}
        </div>

        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {firstRowTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setActiveTag(tag)}
              className={`rounded-full border px-2.5 py-1 text-[11px] ${
                activeTag === tag
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-[var(--color-bg)]'
                  : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              }`}
            >
              {tag === 'all' ? '全部标签' : tag}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-1.5">
          {(recommendedTags || []).slice(0, 6).map((row) => {
            const followed = followedTags.some((x) => x.tag === row.tag)
            return (
              <button
                key={`rec-${row.tag}`}
                onClick={() => void toggleFollow(row.tag)}
                className="aelin-btn h-7 px-2 text-[11px]"
              >
                {followed ? `已关注 ${row.tag}` : `+关注 ${row.tag}`}
              </button>
            )
          })}
          {(tagsLoading || tagsFetching) && (
            <span className="text-[11px] text-[var(--color-text-muted)]">标签加载中…</span>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
        <section className="mb-3 rounded-[12px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                {'全部追踪目标'}
                {` (${filteredTrackingItems.length}/${trackingListData?.total ?? trackingItems.length})`}
              </p>
              <p className="text-[11px] text-[var(--color-text-muted)]">{`和 Tracking 页面同步 · ${activeSourceLabel}`}</p>
            </div>
            <a href="/tracking" className="aelin-btn h-7 px-2 text-[11px]">
              {'打开 Tracking'}
            </a>
          </div>

          <div className="mb-2 flex flex-wrap gap-1.5">
            {(['all', 'active', 'paused', 'error'] as const).map((status) => (
              <button
                key={`tracking-${status}`}
                onClick={() => setTrackingStatus(status)}
                className={`rounded-full border px-2.5 py-1 text-[11px] ${
                  trackingStatus === status
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-[var(--color-bg)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
                }`}
              >
                {status === 'all' ? '全部' : trackingStatusLabel(status)}
              </button>
            ))}
          </div>

          <div className="relative mb-2">
            <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              value={trackingKeyword}
              onChange={(e) => setTrackingKeyword(e.target.value)}
              placeholder={'搜索追踪目标'}
              className="aelin-input h-8 pl-8 text-xs"
              style={{ paddingLeft: '2rem' }}
            />
          </div>

          <div className="max-h-[300px] space-y-2 overflow-y-auto pr-1">
            {filteredTrackingItems.map((item) => (
              <article key={`tracking-item-${item.target_id ?? item.target}`} className="aelin-card p-2">
                <div className="mb-1 flex items-start justify-between gap-2">
                  <p className="line-clamp-1 text-[12px] font-medium">{item.target}</p>
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[10px]',
                      item.status === 'active'
                        ? 'bg-[color-mix(in_srgb,var(--color-green)_15%,transparent)] text-[var(--color-green)]'
                        : item.status === 'paused'
                          ? 'bg-[var(--color-accent-soft)] text-[var(--color-text-muted)]'
                          : 'bg-[color-mix(in_srgb,var(--color-danger)_15%,transparent)] text-[var(--color-danger)]'
                    )}
                  >
                    {trackingStatusLabel(item.status)}
                  </span>
                </div>
                <p className="line-clamp-1 text-[11px] text-[var(--color-text-muted)]">
                  {`${item.source || 'web'} · 每 ${item.interval_seconds}s`}
                  {item.last_checked_at ? ` · ${relativeTime(item.last_checked_at)}` : ''}
                </p>
                {item.unread_changes > 0 ? (
                  <p className="mt-1 text-[11px] font-medium text-[var(--color-orange)]">
                    {`未读变化 ${item.unread_changes} 条`}
                  </p>
                ) : null}
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <button onClick={() => applyTrackingContext(item)} className="aelin-btn h-7 px-2 text-[11px]">
                    {'联动内容'}
                  </button>
                  {item.target_id ? (
                    <button
                      onClick={() => runTrackingNow.mutate(item.target_id as number)}
                      className="aelin-btn h-7 px-2 text-[11px]"
                      disabled={runTrackingNow.isPending && Number(runTrackingNow.variables || 0) === Number(item.target_id)}
                    >
                      {runTrackingNow.isPending && Number(runTrackingNow.variables || 0) === Number(item.target_id)
                        ? '运行中…'
                        : '运行'}
                    </button>
                  ) : null}
                  {item.target_id ? (
                    <a href={`/tracking/${item.target_id}`} className="aelin-btn h-7 px-2 text-[11px]">
                      {'详情'}
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
            {filteredTrackingItems.length === 0 ? (
              <p className="py-4 text-center text-[11px] text-[var(--color-text-muted)]">
                {trackingListFetching ? '追踪加载中…' : '暂无追踪目标'}
              </p>
            ) : null}
          </div>
        </section>

        <section className="mb-3 rounded-[12px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[12px] font-semibold text-[var(--color-text)]">
                {contextTargetId > 0 ? '追踪变更流 (当前联动)' : '追踪变更流 (全部)'}
              </p>
              <p className="text-[11px] text-[var(--color-text-muted)]">
                {contextTargetId > 0 ? '只显示当前目标变更' : '聚合所有追踪目标的最新变更'}
              </p>
            </div>
          </div>
          <div className="max-h-[250px] space-y-2 overflow-y-auto pr-1">
            {changeStreamRows.map((change) => (
              <article key={`tracking-change-${change.id}`} className="aelin-card p-2">
                <div className="mb-1 flex items-start justify-between gap-2">
                  <p className="line-clamp-1 text-[12px] font-medium">{change.title || '变更'}</p>
                  <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                    {change.severity || 'info'}
                  </span>
                </div>
                <p className="line-clamp-1 text-[11px] text-[var(--color-text-muted)]">
                  {change.target_name}
                  {change.target_source ? ` · ${change.target_source}` : ''}
                  {change.created_at ? ` · ${relativeTime(change.created_at) || change.created_at}` : ''}
                </p>
                <p className="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-muted)]">
                  {change.summary || '本次变更暂无摘要。'}
                </p>
                {contextTargetId <= 0 && change.target_id ? (
                  <div className="mt-1.5">
                    <button
                      onClick={() => {
                        const target = trackingItems.find((item) => Number(item.target_id || 0) === Number(change.target_id || 0))
                        if (target) applyTrackingContext(target)
                      }}
                      className="aelin-btn h-7 px-2 text-[11px]"
                    >
                      {'联动到该目标'}
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
            {changeStreamRows.length === 0 ? (
              <p className="py-4 text-center text-[11px] text-[var(--color-text-muted)]">
                {changeStreamLoading ? '变更加载中…' : '暂无变更'}
              </p>
            ) : null}
          </div>
        </section>

        <div className="space-y-2.5">
          {items.map((item) => (
            <article key={item.message_id} className="aelin-card p-2.5">
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-semibold">{item.sender || item.source_label}</p>
                  <p className="truncate text-[11px] text-[var(--color-text-muted)]">
                    {item.source_label} · {relativeTime(item.received_at) || item.received_at}
                  </p>
                </div>
                {item.external_url ? (
                  <a
                    href={item.external_url}
                    target="_blank"
                    rel="noreferrer"
                    className="aelin-btn h-7 px-2 text-[11px]"
                    title="查看原文"
                  >
                    <ExternalLink size={12} />
                  </a>
                ) : null}
              </div>

              <h3 className="mb-1.5 line-clamp-2 text-[13px] font-semibold">{item.title}</h3>
              {item.image_url ? (
                <img
                  src={item.image_url}
                  alt={item.title}
                  className="mb-2 max-h-[220px] w-full rounded-[10px] border border-[var(--color-border)] object-cover"
                  loading="lazy"
                />
              ) : null}
              {!!item.preview && (
                <p className="line-clamp-3 text-[12px] text-[var(--color-text-muted)]">{item.preview}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(item.tags || []).slice(0, 5).map((tag) => (
                  <span
                    key={`${item.message_id}-${tag}`}
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${
                      tag === item.primary_tag
                        ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-[var(--color-bg)]'
                        : 'border-[var(--color-border)] text-[var(--color-text-muted)]'
                    }`}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </article>
          ))}

        </div>

        {items.length === 0 && (
          <div className="py-12 text-center text-[12px] text-[var(--color-text-muted)]">{emptyHint}</div>
        )}

        {hasMore && items.length > 0 && (
          <div className="mt-3 flex justify-center">
            <button
              onClick={async () => {
                setLoadingMore(true)
                try {
                  await loadFeed(false)
                } finally {
                  setLoadingMore(false)
                }
              }}
              disabled={loadingMore}
              className="aelin-btn h-8 px-3 text-[11px]"
            >
              {loadingMore ? '加载中…' : '加载更多'}
            </button>
          </div>
        )}
      </div>
    </section>
  )
}

