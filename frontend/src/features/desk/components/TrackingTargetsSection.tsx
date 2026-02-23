import { Search } from 'lucide-react'
import type { AelinTrackingItem } from '@/shared/api/types'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { TRACKING_STATUS_OPTIONS } from '../constants'
import { trackingStatusLabel } from '../utils'
import { FilterChip } from './FilterChip'

type TrackingStatus = typeof TRACKING_STATUS_OPTIONS[number]

type Props = {
  activeSourceLabel: string
  trackingItemsTotal: number
  trackingStatus: TrackingStatus
  trackingKeyword: string
  trackingListFetching: boolean
  filteredTrackingItems: AelinTrackingItem[]
  runTrackingPendingTargetId: number | null
  onTrackingStatusChange: (status: TrackingStatus) => void
  onTrackingKeywordChange: (value: string) => void
  onApplyTrackingContext: (item: AelinTrackingItem) => void
  onRunTrackingNow: (targetId: number) => void
}

export function TrackingTargetsSection({
  activeSourceLabel,
  trackingItemsTotal,
  trackingStatus,
  trackingKeyword,
  trackingListFetching,
  filteredTrackingItems,
  runTrackingPendingTargetId,
  onTrackingStatusChange,
  onTrackingKeywordChange,
  onApplyTrackingContext,
  onRunTrackingNow,
}: Props) {
  return (
    <section className="mb-3 rounded-[12px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[12px] font-semibold text-[var(--color-text)]">
            {'全部追踪目标'}
            {` (${filteredTrackingItems.length}/${trackingItemsTotal})`}
          </p>
          <p className="text-[11px] text-[var(--color-text-muted)]">{`和 Tracking 页面同步 · ${activeSourceLabel}`}</p>
        </div>
        <a href="/tracking" className="aelin-btn h-7 px-2 text-[11px]">
          {'打开 Tracking'}
        </a>
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {TRACKING_STATUS_OPTIONS.map((status) => (
          <FilterChip
            key={`tracking-${status}`}
            selected={trackingStatus === status}
            label={status === 'all' ? '全部' : trackingStatusLabel(status)}
            onClick={() => onTrackingStatusChange(status)}
          />
        ))}
      </div>

      <div className="relative mb-2">
        <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input
          value={trackingKeyword}
          onChange={(event) => onTrackingKeywordChange(event.target.value)}
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
              <button onClick={() => onApplyTrackingContext(item)} className="aelin-btn h-7 px-2 text-[11px]">
                {'联动内容'}
              </button>
              {item.target_id ? (
                <button
                  onClick={() => onRunTrackingNow(item.target_id as number)}
                  className="aelin-btn h-7 px-2 text-[11px]"
                  disabled={runTrackingPendingTargetId === Number(item.target_id)}
                >
                  {runTrackingPendingTargetId === Number(item.target_id) ? '运行中…' : '运行'}
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
  )
}
