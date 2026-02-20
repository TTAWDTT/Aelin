import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime, severityColor } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { Play, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import { TrackConfirmSheet } from './components/TrackConfirmSheet'

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
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-panel)] shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-lg font-semibold" style={{ fontFamily: 'var(--font-heading)' }}>追踪中心</h1>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90">
            <Plus size={14} /> 新建追踪
          </button>
        </div>
        <div className="flex gap-1 text-xs">
          {filters.map(f => (
            <button key={f} onClick={() => setStatusFilter(f)}
              className={cn('px-2.5 py-1 rounded-lg transition-colors',
                statusFilter === f ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              )}>
              {f === 'all' ? '全部' : f === 'active' ? '活跃' : f === 'paused' ? '暂停' : '异常'}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isLoading && <div className="text-sm text-[var(--color-text-muted)] text-center py-8">加载中…</div>}
        {!isLoading && items.length === 0 && (
          <div className="text-center py-12 text-sm text-[var(--color-text-muted)]">
            暂无追踪目标。可以在对话中让 Aelin 帮你创建，或点击"新建追踪"。
          </div>
        )}
        {items.map(item => (
          <div key={item.target_id ?? item.target} onClick={() => item.target_id && navigate(`/tracking/${item.target_id}`)}
            className="border border-[var(--color-border)] rounded-xl p-4 bg-[var(--color-panel)] hover:border-[var(--color-border-strong)] transition-colors cursor-pointer">
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
              <button onClick={(e) => { e.stopPropagation(); item.target_id && runTarget.mutate(item.target_id) }}
                className="flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md border border-[var(--color-border)] hover:bg-[var(--color-accent-soft)]">
                <Play size={11} /> 立即运行
              </button>
            </div>
          </div>
        ))}
      </div>

      {showCreate && <TrackConfirmSheet onClose={() => setShowCreate(false)} />}
    </div>
  )
}
