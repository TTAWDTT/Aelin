import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Search, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { aelinApi } from '@/shared/api/aelin'
import type { AelinTrackingChangeItem, AelinTrackingItem, DeskFeedItem } from '@/shared/api/types'
import { SOURCE_OPTIONS } from './constants'
import { ChangeStreamSection } from './components/ChangeStreamSection'
import { FeedItemsSection } from './components/FeedItemsSection'
import { FilterChip } from './components/FilterChip'
import { TrackingTargetsSection } from './components/TrackingTargetsSection'
import type { DeskPanelContext, TrackingChangeRow } from './types'
import {
  extractChangePreview,
  normalizeSource,
  normalizeUrl,
  sourceLabel,
  toUnixTs,
} from './utils'

export type { DeskPanelContext } from './types'

type Props = {
  onClose?: () => void
  context?: DeskPanelContext | null
  onClearContext?: () => void
  onSelectContext?: (context: DeskPanelContext) => void
}

type TrackingStatus = 'all' | 'active' | 'paused' | 'error'

export function DeskPanel({ onClose, context, onClearContext, onSelectContext }: Props) {
  const qc = useQueryClient()
  const [trackingStatus, setTrackingStatus] = useState<TrackingStatus>('all')
  const [trackingKeyword, setTrackingKeyword] = useState('')
  const [activeTag, setActiveTag] = useState('all')
  const [items, setItems] = useState<DeskFeedItem[]>([])
  const [cursor, setCursor] = useState<{ at?: string | null; id?: number | null }>({})
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const prevHasContextRef = useRef(false)

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
      for (const row of prev) map.set(row.message_id, row)
      for (const row of rows) map.set(row.message_id, row)
      return Array.from(map.values())
    })
    setCursor({ at: resp.next_before_received_at, id: resp.next_before_id })
    setHasMore(Boolean(resp.next_before_received_at && resp.next_before_id))
  }

  useEffect(() => {
    const timer = setTimeout(() => setSearchQuery(searchInput.trim()), 250)
    return () => clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    if (!hasContext) {
      if (prevHasContextRef.current) {
        setActiveTag('all')
        setSourceFilter('')
        setSearchInput('')
        setSearchQuery('')
      }
      prevHasContextRef.current = false
      return
    }

    setActiveTag('all')
    setSourceFilter(contextSource || '')
    setSearchInput(contextKeyword || '')
    setSearchQuery(contextKeyword || '')
    prevHasContextRef.current = true
  }, [contextKeyword, contextSource, hasContext])

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
      const normalized = normalizeSource(item.source || '')
      if (sourceFilter && normalized !== sourceFilter) return false
      if (!keyword) return true
      return `${item.target || ''} ${item.description || ''} ${item.source || ''}`.toLowerCase().includes(keyword)
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

      return rows
        .flat()
        .sort((a, b) => toUnixTs(b.created_at) - toUnixTs(a.created_at))
        .slice(0, 24)
    },
    staleTime: 15_000,
  })

  const firstRowTags = useMemo(() => {
    const seen = new Set<string>(['all'])
    const out: string[] = ['all']

    for (const row of followedTags) {
      const tag = String(row.tag || '').trim()
      if (!tag || seen.has(tag)) continue
      seen.add(tag)
      out.push(tag)
    }

    for (const row of discoverTags) {
      const tag = String(row.tag || '').trim()
      if (!tag || seen.has(tag)) continue
      seen.add(tag)
      out.push(tag)
    }
    return out.slice(0, 12)
  }, [discoverTags, followedTags])

  const toggleFollow = async (tag: string) => {
    const normalized = String(tag || '').trim()
    if (!normalized) return
    const followed = followedTags.some((item) => item.tag === normalized)
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
  const changePreviewRows = useMemo(
    () => changeStreamRows.map((row) => ({ row, preview: extractChangePreview(row, items) })),
    [changeStreamRows, items]
  )

  const emptyHint = contextTargetId > 0
    ? '该追踪目标暂无可展示内容，可先查看上方「追踪变更流」或点击「运行」后刷新。'
    : searchQuery || sourceFilter
      ? '暂未命中与当前条件相关的内容，可尝试调整关键词或来源。'
      : '暂无可展示内容。请先绑定内容平台并同步。'

  const activeSourceLabel = sourceLabel(sourceFilter)

  const openExternal = (rawUrl: string | null | undefined) => {
    const url = normalizeUrl(rawUrl)
    if (!url) return
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const refreshDesk = () => {
    setItems([])
    setCursor({})
    setHasMore(true)
    void loadFeed(true)
    if (contextTargetId > 0) void refetchLinkedChanges()
    void qc.invalidateQueries({ queryKey: ['desk-tags'] })
    void qc.invalidateQueries({ queryKey: ['desk-tracking-list'] })
    void qc.invalidateQueries({ queryKey: ['desk-recent-tracking-changes'] })
  }

  const runTrackingPendingTargetId = runTrackingNow.isPending ? Number(runTrackingNow.variables || 0) : null

  return (
    <section className="flex h-full min-h-0 flex-col bg-[var(--color-panel)]">
      <header className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2.5">
        <div className="min-w-0">
          <h2 className="truncate text-[0.92rem] font-semibold">Desk 观察</h2>
          <p className="text-[11px] text-[var(--color-text-muted)]">跨平台内容流 · 时间倒序</p>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={refreshDesk} className="aelin-btn h-8 px-2.5 text-[11px]" title="刷新">
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
                {contextSource ? `来源: ${sourceLabel(contextSource)}` : ''}
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
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="搜索标题、作者或摘要"
            className="aelin-input h-8 pl-8 text-xs"
            style={{ paddingLeft: '2rem' }}
          />
        </div>

        <div className="mb-2 flex flex-wrap gap-1.5">
          {SOURCE_OPTIONS.map((source) => (
            <FilterChip
              key={source.key || 'all-source'}
              selected={sourceFilter === source.key}
              label={source.label}
              onClick={() => setSourceFilter(source.key)}
            />
          ))}
        </div>

        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {firstRowTags.map((tag) => (
            <FilterChip
              key={tag}
              selected={activeTag === tag}
              label={tag === 'all' ? '全部标签' : tag}
              onClick={() => setActiveTag(tag)}
            />
          ))}
        </div>

        <div className="flex flex-wrap gap-1.5">
          {(recommendedTags || []).slice(0, 6).map((row) => {
            const followed = followedTags.some((item) => item.tag === row.tag)
            return (
              <button key={`rec-${row.tag}`} onClick={() => void toggleFollow(row.tag)} className="aelin-btn h-7 px-2 text-[11px]">
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
        <TrackingTargetsSection
          activeSourceLabel={activeSourceLabel}
          trackingItemsTotal={trackingListData?.total ?? trackingItems.length}
          trackingStatus={trackingStatus}
          trackingKeyword={trackingKeyword}
          trackingListFetching={trackingListFetching}
          filteredTrackingItems={filteredTrackingItems}
          runTrackingPendingTargetId={runTrackingPendingTargetId}
          onTrackingStatusChange={setTrackingStatus}
          onTrackingKeywordChange={setTrackingKeyword}
          onApplyTrackingContext={applyTrackingContext}
          onRunTrackingNow={(targetId) => runTrackingNow.mutate(targetId)}
        />

        <ChangeStreamSection
          contextTargetId={contextTargetId}
          changeStreamLoading={changeStreamLoading}
          changePreviewRows={changePreviewRows}
          onOpenExternal={openExternal}
          onLinkTarget={(targetId) => {
            const target = trackingItems.find((item) => Number(item.target_id || 0) === Number(targetId || 0))
            if (target) applyTrackingContext(target)
          }}
        />

        <FeedItemsSection
          items={items}
          emptyHint={emptyHint}
          hasMore={hasMore}
          loadingMore={loadingMore}
          onLoadMore={async () => {
            setLoadingMore(true)
            try {
              await loadFeed(false)
            } finally {
              setLoadingMore(false)
            }
          }}
        />
      </div>
    </section>
  )
}
