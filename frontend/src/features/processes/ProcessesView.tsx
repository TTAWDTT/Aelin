import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cpu, RefreshCw, Search, Shield, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { aelinApi } from '@/shared/api/aelin'
import { cn } from '@/shared/utils/cn'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { useMediaQuery } from '@/shared/hooks/useMediaQuery'

type SortBy = 'cpu' | 'memory'

export function ProcessesView() {
  const queryClient = useQueryClient()
  const { setFocusModeEnabled } = useLayoutStore()
  const compact = useMediaQuery('(max-width: 1080px)')
  const [sortBy, setSortBy] = useState<SortBy>('cpu')
  const [query, setQuery] = useState('')

  const { data: capabilities } = useQuery({
    queryKey: ['device-capabilities'],
    queryFn: aelinApi.deviceCapabilities,
  })

  const { data: processData, isFetching, refetch } = useQuery({
    queryKey: ['device-processes', sortBy],
    queryFn: () => aelinApi.deviceProcesses(sortBy),
    refetchInterval: 30_000,
  })

  const optimize = useMutation({
    mutationFn: aelinApi.deviceOptimize,
    onSuccess: (result) => {
      toast.success(`已优化 ${result.optimized_count} 个进程`)
      queryClient.invalidateQueries({ queryKey: ['device-processes'] })
    },
    onError: () => toast.error('优化失败'),
  })

  const terminate = useMutation({
    mutationFn: (pid: number) => aelinApi.deviceProcessAction(pid, 'terminate'),
    onSuccess: () => {
      toast.success('进程已终止')
      queryClient.invalidateQueries({ queryKey: ['device-processes'] })
    },
    onError: () => toast.error('终止失败'),
  })

  const applyMode = useMutation({
    mutationFn: (mode: string) => aelinApi.deviceModeApply(mode),
    onSuccess: (result, mode) => {
      setFocusModeEnabled(mode === 'focus')
      toast.success(result.summary)
      queryClient.invalidateQueries({ queryKey: ['device-processes'] })
    },
    onError: () => toast.error('模式切换失败'),
  })

  const rows = processData?.items ?? []
  const filteredRows = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return rows
    return rows.filter((item) => item.name.toLowerCase().includes(keyword) || String(item.pid).includes(keyword))
  }, [rows, query])
  const normalizeCpuPercent = (value: number) => Math.max(0, Math.min(100, Number(value || 0)))
  const maxCpu = 100
  const maxMem = Math.max(1, ...filteredRows.map((item) => item.memory_mb))

  return (
    <PageScaffold
      title="进程管理"
      subtitle="mac 风格任务管理器 · Activity Monitor"
      headerActions={
        <div className="flex w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end">
          <div className="aelin-segment">
            <button data-active={sortBy === 'cpu'} onClick={() => setSortBy('cpu')}>CPU</button>
            <button data-active={sortBy === 'memory'} onClick={() => setSortBy('memory')}>内存</button>
          </div>
          <button className="aelin-btn" onClick={() => refetch()}>
            <RefreshCw size={14} className={cn(isFetching && 'animate-spin')} />
            刷新
          </button>
        </div>
      }
    >
      <div className="mx-auto w-full max-w-[1360px] space-y-4">
        <div className="aelin-card p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
              <span className="inline-flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
              </span>
              <Shield size={14} />
              <span className="truncate">平台：{capabilities?.platform ?? 'unknown'}</span>
            </div>
            <div className="flex h-8 w-full items-center rounded-[10px] border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 sm:w-[220px] md:w-[240px]">
              <Search size={12} className="shrink-0 text-[var(--color-text-muted)]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="过滤进程"
                className="ml-1.5 min-w-0 flex-1 border-0 bg-transparent p-0 text-xs text-[var(--color-text)] outline-none placeholder:text-[var(--color-text-muted)]"
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="aelin-btn" onClick={() => applyMode.mutate('focus')}>🎯 专注</button>
            <button className="aelin-btn" onClick={() => applyMode.mutate('performance')}>⚡ 性能</button>
            <button className="aelin-btn" onClick={() => applyMode.mutate('battery')}>🔋 省电</button>
            <button className="aelin-btn aelin-btn-primary" onClick={() => optimize.mutate()} disabled={optimize.isPending}>
              <Zap size={14} />
              {optimize.isPending ? '优化中' : '一键优化'}
            </button>
          </div>
          {capabilities?.notes && capabilities.notes.length > 0 && (
            <div className="mt-3 space-y-1 text-xs text-[var(--color-text-muted)]">
              {capabilities.notes.map((note) => (
                <p key={note}>{note}</p>
              ))}
            </div>
          )}
        </div>

        <div className="aelin-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-text-muted)]">
            <Cpu size={14} />
            活跃进程（{filteredRows.length}）
          </div>
          {!compact && (
            <div className="overflow-x-auto">
              <div className="min-w-[700px]">
                <div className="grid grid-cols-[minmax(0,2fr)_1fr_1fr_0.75fr_0.7fr] border-b border-[var(--color-border)] bg-[var(--color-panel-alt)] px-3 py-2 text-[11px] text-[var(--color-text-muted)]">
                  <span>进程名称</span>
                  <span className="text-right">CPU</span>
                  <span className="text-right">内存</span>
                  <span className="text-right">异常</span>
                  <span className="text-right">操作</span>
                </div>
                <div className="max-h-[72vh] overflow-y-auto">
                  {filteredRows.map((process, index) => {
                    const displayCpu = normalizeCpuPercent(process.cpu_percent)
                    return (
                      <div
                        key={process.pid}
                        className={cn(
                          'grid grid-cols-[minmax(0,2fr)_1fr_1fr_0.75fr_0.7fr] items-center gap-2 px-3 py-2 text-xs',
                          index % 2 === 0 ? 'bg-[var(--color-panel)]' : 'bg-[var(--color-panel-alt)]',
                        )}
                      >
                        <div className="min-w-0">
                          <p className="truncate font-mono text-[12px]">{process.name}</p>
                          <p className="text-[11px] text-[var(--color-text-muted)]">PID {process.pid}</p>
                        </div>
                        <div className="ml-auto w-[90px] text-right">
                          <p>{displayCpu.toFixed(1)}%</p>
                          <div className="mt-1 h-1.5 rounded-full bg-[var(--color-border)]">
                            <div
                              className="h-full rounded-full bg-[var(--color-accent)]"
                              style={{ width: `${Math.min(100, (displayCpu / maxCpu) * 100)}%` }}
                            />
                          </div>
                        </div>
                        <div className="ml-auto w-[96px] text-right">
                          <p>{process.memory_mb.toFixed(0)} MB</p>
                          <div className="mt-1 h-1.5 rounded-full bg-[var(--color-border)]">
                            <div
                              className="h-full rounded-full bg-[var(--color-accent)]"
                              style={{ width: `${Math.min(100, (process.memory_mb / maxMem) * 100)}%` }}
                            />
                          </div>
                        </div>
                        <div className="text-right text-[11px]">
                          {process.anomaly_score > 0.5 ? <span>⚠ {process.anomaly_score.toFixed(1)}</span> : <span>—</span>}
                        </div>
                        <div className="text-right">
                          {process.safe_to_terminate ? (
                            <button className="aelin-btn h-7 px-2 text-[11px]" onClick={() => terminate.mutate(process.pid)}>
                              终止
                            </button>
                          ) : (
                            <span className="text-[11px] text-[var(--color-text-muted)]">—</span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                  {filteredRows.length === 0 && (
                    <div className="px-3 py-8 text-center text-xs text-[var(--color-text-muted)]">暂无进程数据</div>
                  )}
                </div>
              </div>
            </div>
          )}
          {compact && (
            <div className="max-h-[68vh] space-y-2 overflow-y-auto p-2.5">
              {filteredRows.map((process) => {
                const displayCpu = normalizeCpuPercent(process.cpu_percent)
                return (
                  <div key={process.pid} className="rounded-[12px] border border-[var(--color-border)] bg-[var(--color-panel)] p-2.5 text-xs">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-[12px]">{process.name}</p>
                        <p className="text-[11px] text-[var(--color-text-muted)]">PID {process.pid}</p>
                      </div>
                      {process.safe_to_terminate ? (
                        <button className="aelin-btn h-7 px-2 text-[11px]" onClick={() => terminate.mutate(process.pid)}>
                          终止
                        </button>
                      ) : (
                        <span className="text-[11px] text-[var(--color-text-muted)]">—</span>
                      )}
                    </div>
                    <div className="mt-2.5 space-y-2">
                      <div>
                        <div className="mb-0.5 flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                          <span>CPU</span>
                          <span>{displayCpu.toFixed(1)}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-[var(--color-border)]">
                          <div
                            className="h-full rounded-full bg-[var(--color-accent)]"
                            style={{ width: `${Math.min(100, (displayCpu / maxCpu) * 100)}%` }}
                          />
                        </div>
                      </div>
                      <div>
                        <div className="mb-0.5 flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                          <span>内存</span>
                          <span>{process.memory_mb.toFixed(0)} MB</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-[var(--color-border)]">
                          <div
                            className="h-full rounded-full bg-[var(--color-accent)]"
                            style={{ width: `${Math.min(100, (process.memory_mb / maxMem) * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                      异常：{process.anomaly_score > 0.5 ? `⚠ ${process.anomaly_score.toFixed(1)}` : '—'}
                    </div>
                  </div>
                )
              })}
              {filteredRows.length === 0 && (
                <div className="px-3 py-8 text-center text-xs text-[var(--color-text-muted)]">暂无进程数据</div>
              )}
            </div>
          )}
        </div>
      </div>
    </PageScaffold>
  )
}
