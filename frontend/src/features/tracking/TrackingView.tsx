import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { Play, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import { TrackConfirmSheet } from './components/TrackConfirmSheet'
import { PageScaffold } from '@/shared/components/PageScaffold'

export function TrackingView() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [showCreate, setShowCreate] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['tracking', statusFilter],
    queryFn: () => aelinApi.trackingList(statusFilter !== 'all' ? { status: statusFilter } : undefined),
    refetchInterval: 30_000,
  })

  const runTarget = useMutation({
    mutationFn: (id: number) => aelinApi.trackingRun(id),
    onSuccess: (res) => { toast.success(res.message); qc.invalidateQueries({ queryKey: ['tracking'] }) },
    onError: () => toast.error('运行失败'),
  })

  const items = data?.items ?? []
  const filters = ['all', 'active', 'paused', 'error'] as const

  return (
    <PageScaffold
      title="Tracking"
      subtitle="查看被追踪的 Web / 帖子变化"
      headerActions={
        <button onClick={() => setShowCreate(true)} className="aelin-btn aelin-btn-primary">
          <Plus size={14} />
          新建追踪
        </button>
      }
    >
      <div className="space-y-3">
        <div className="aelin-segment">
          {filters.map((f) => (
            <button key={f} data-active={statusFilter === f} onClick={() => setStatusFilter(f)}>
              {f === 'all' ? '全部' : f === 'active' ? '活跃' : f === 'paused' ? '暂停' : '异常'}
            </button>
          ))}
        </div>

        {isLoading && <div className="text-sm text-[var(--color-text-muted)] text-center py-8">加载中…</div>}
        {!isLoading && items.length === 0 && (
          <div className="text-center py-12 text-sm text-[var(--color-text-muted)]">
            暂无追踪目标。可以在对话中让 Aelin 帮你创建，或点击"新建追踪"。
          </div>
        )}
        {items.map((item) => (
          <div
            key={item.target_id ?? item.target}
            onClick={() => item.target_id && navigate(`/tracking/${item.target_id}`)}
            className="aelin-card cursor-pointer p-4 transition-colors hover:border-[var(--color-border-strong)]"
          >
            <div className="flex items-start justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm">📡</span>
                <span className="font-medium text-sm truncate">{item.target}</span>
              </div>
              <span className={cn('text-[11px] px-2 py-0.5 rounded-full font-medium',
                item.status === 'active' ? 'bg-[color-mix(in_srgb,var(--color-green)_15%,transparent)] text-[var(--color-green)]'
                : item.status === 'paused' ? 'bg-[var(--color-accent-soft)] text-[var(--color-text-muted)]'
                : 'bg-[color-mix(in_srgb,var(--color-danger)_15%,transparent)] text-[var(--color-danger)]'
              )}>
                {item.status}
              </span>
            </div>
            <div className="text-[11px] text-[var(--color-text-muted)] flex items-center gap-2 flex-wrap">
              <span>{item.source}</span>
              <span>·</span>
              <span>每 {item.interval_seconds}s</span>
              {item.last_checked_at && <><span>·</span><span>最后检查 {relativeTime(item.last_checked_at)}</span></>}
            </div>
            {item.unread_changes > 0 && (
              <div className="mt-2 text-xs font-medium text-[var(--color-orange)]">
                🔴 {item.unread_changes} 个未读变化
              </div>
            )}
            {item.description && <div className="mt-1.5 text-xs text-[var(--color-text-muted)]">{item.description}</div>}
            <div className="flex gap-2 mt-3">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  item.target_id && runTarget.mutate(item.target_id)
                }}
                className="aelin-btn h-7 px-2 text-[11px]"
              >
                <Play size={11} /> 立即运行
              </button>
            </div>
          </div>
        ))}
      </div>

      {showCreate && <TrackConfirmSheet onClose={() => setShowCreate(false)} />}
    </PageScaffold>
  )
}
