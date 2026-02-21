import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { Play, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import { TrackConfirmSheet } from './components/TrackConfirmSheet'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'
import { DeskPanel, type DeskPanelContext } from '@/features/desk/DeskPanel'

export function TrackingView() {
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()
  const isDesktopDeskRail = useMediaQuery('(min-width: 1280px)')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [showCreate, setShowCreate] = useState(false)
  const [deskContext, setDeskContext] = useState<DeskPanelContext | null>(null)
  const [deskOpen, setDeskOpen] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return (new URLSearchParams(window.location.search).get('panel') || '').trim() === 'desk'
  })

  const { data, isLoading } = useQuery({
    queryKey: ['tracking', statusFilter],
    queryFn: () => aelinApi.trackingList(statusFilter !== 'all' ? { status: statusFilter } : undefined),
    refetchInterval: 30_000,
  })

  const runTarget = useMutation({
    mutationFn: (id: number) => aelinApi.trackingRun(id),
    onSuccess: (res) => {
      toast.success(res.message)
      qc.invalidateQueries({ queryKey: ['tracking'] })
    },
    onError: () => toast.error('运行失败'),
  })

  useEffect(() => {
    const panel = (new URLSearchParams(location.search).get('panel') || '').trim()
    if (panel === 'desk') setDeskOpen(true)
  }, [location.search])

  const items = data?.items ?? []
  const filters = ['all', 'active', 'paused', 'error'] as const

  const toDeskSource = (raw: string) => {
    const source = String(raw || '').trim().toLowerCase()
    if (['x', 'weibo', 'xiaohongshu', 'douyin', 'bilibili', 'rss', 'web'].includes(source)) return source
    if (source === 'xhs') return 'xiaohongshu'
    return ''
  }

  const linkDeskWithTracking = (item: { target_id?: number | null; source?: string; target?: string; query?: string | null }) => {
    const source = toDeskSource(item.source || '')
    const keyword = String(item.query || item.target || '').trim()
    setDeskContext({
      targetId: typeof item.target_id === 'number' ? item.target_id : undefined,
      source: source || undefined,
      keyword: keyword || undefined,
      title: String(item.target || '').trim() || '追踪联动',
    })
    setDeskOpen(true)
    if (!source) {
      toast('当前来源暂不支持精准过滤，已按关键词联动 Desk。')
    }
  }

  return (
    <div className="relative flex min-h-0 flex-1">
      <div
        className={cn(
          'flex min-h-0 min-w-0 flex-1 transition-[padding] duration-420 ease-[cubic-bezier(0.22,1,0.36,1)]',
          isDesktopDeskRail && deskOpen ? 'pr-[492px]' : 'pr-0'
        )}
      >
        <PageScaffold
          title="Tracking"
          subtitle="查看被追踪的 Web / 帖子变化"
          headerActions={
            <div className="flex items-center gap-2">
              {deskContext ? (
                <button onClick={() => setDeskContext(null)} className="aelin-btn h-8 px-2.5 text-[11px]">
                  {'清除联动'}
                </button>
              ) : null}
              <button onClick={() => setDeskOpen((v) => !v)} className="aelin-btn h-8 px-3 text-[11px]">
                {deskOpen ? '收起 Desk' : '打开 Desk'}
              </button>
              <button onClick={() => setShowCreate(true)} className="aelin-btn aelin-btn-primary">
                <Plus size={14} />
                {'新建追踪'}
              </button>
            </div>
          }
        >
          <div className="mx-auto w-full max-w-[980px] space-y-3">
            <div className="aelin-segment">
              {filters.map((f) => (
                <button key={f} data-active={statusFilter === f} onClick={() => setStatusFilter(f)}>
                  {f === 'all' ? '全部' : f === 'active' ? '活跃' : f === 'paused' ? '暂停' : '异常'}
                </button>
              ))}
            </div>

            {isLoading && <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">{'加载中…'}</div>}
            {!isLoading && items.length === 0 && (
              <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">
                {'暂无追踪目标。可以在对话中让 Aelin 帮你创建，或点击"新建追踪"。'}
              </div>
            )}

            {items.map((item) => (
              <div
                key={item.target_id ?? item.target}
                onClick={() => item.target_id && navigate(`/tracking/${item.target_id}`)}
                className="aelin-card cursor-pointer p-4 transition-colors"
              >
                <div className="mb-1.5 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="font-medium text-sm truncate">{item.target}</span>
                  </div>
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[11px] font-medium',
                      item.status === 'active'
                        ? 'bg-[color-mix(in_srgb,var(--color-green)_15%,transparent)] text-[var(--color-green)]'
                        : item.status === 'paused'
                          ? 'bg-[var(--color-accent-soft)] text-[var(--color-text-muted)]'
                          : 'bg-[color-mix(in_srgb,var(--color-danger)_15%,transparent)] text-[var(--color-danger)]'
                    )}
                  >
                    {item.status}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
                  <span>{item.source}</span>
                  <span>{'·'}</span>
                  <span>{`每 ${item.interval_seconds}s`}</span>
                  {item.last_checked_at && (
                    <>
                      <span>{'·'}</span>
                      <span>{`最后检查 ${relativeTime(item.last_checked_at)}`}</span>
                    </>
                  )}
                </div>

                {item.unread_changes > 0 && (
                  <div className="mt-2 text-xs font-medium text-[var(--color-orange)]">
                    {`未读变化 ${item.unread_changes} 条`}
                  </div>
                )}

                {item.description && <div className="mt-1.5 text-xs text-[var(--color-text-muted)]">{item.description}</div>}

                <div className="mt-3 flex gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      linkDeskWithTracking(item)
                    }}
                    className="aelin-btn h-7 px-2 text-[11px]"
                  >
                    {'联动 Desk'}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      item.target_id && runTarget.mutate(item.target_id)
                    }}
                    className="aelin-btn h-7 px-2 text-[11px]"
                  >
                    <Play size={11} />
                    {'立即运行'}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {showCreate && <TrackConfirmSheet onClose={() => setShowCreate(false)} />}
        </PageScaffold>
      </div>

      {isDesktopDeskRail ? (
        <aside
          className={cn(
            'absolute inset-y-0 right-0 w-[446px] border-l border-[var(--color-border)] bg-[var(--color-bg)] p-2.5 transition-opacity duration-360 ease-[cubic-bezier(0.22,1,0.36,1)]',
            deskOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
          )}
        >
          <div
            className={cn(
              'h-full w-[430px] rounded-[20px] border border-[var(--color-border)] bg-[var(--color-panel)] shadow-[16px_18px_42px_rgba(0,0,0,0.2)] will-change-transform transition-transform duration-420 ease-[cubic-bezier(0.175,0.885,0.32,1.12)]',
              deskOpen ? 'translate-x-0 scale-100' : 'translate-x-[calc(100%+18px)] scale-[0.985]'
            )}
          >
            <DeskPanel
              onClose={() => setDeskOpen(false)}
              context={deskContext}
              onClearContext={() => setDeskContext(null)}
              onSelectContext={(nextContext) => {
                setDeskContext(nextContext)
                setDeskOpen(true)
              }}
            />
          </div>
        </aside>
      ) : null}

      {!isDesktopDeskRail ? (
        <div
          className={cn(
            'fixed inset-0 z-50 transition-colors duration-320 ease-[cubic-bezier(0.22,1,0.36,1)]',
            deskOpen ? 'pointer-events-auto bg-black/25' : 'pointer-events-none bg-black/0'
          )}
          onClick={() => setDeskOpen(false)}
        >
          <div
            className={cn(
              'absolute inset-y-0 right-0 w-full max-w-[430px] border-l border-[var(--color-border)] bg-[var(--color-panel)] shadow-[0_18px_42px_rgba(0,0,0,0.22)] will-change-transform transition-transform duration-420 ease-[cubic-bezier(0.175,0.885,0.32,1.12)]',
              deskOpen ? 'translate-x-0 scale-100' : 'translate-x-full scale-[0.985]'
            )}
            onClick={(e) => e.stopPropagation()}
          >
            <DeskPanel
              onClose={() => setDeskOpen(false)}
              context={deskContext}
              onClearContext={() => setDeskContext(null)}
              onSelectContext={(nextContext) => {
                setDeskContext(nextContext)
                setDeskOpen(true)
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

