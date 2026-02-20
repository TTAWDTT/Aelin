import { useQuery, useMutation } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
import { Cpu, Zap, Shield } from 'lucide-react'
import toast from 'react-hot-toast'

export function DeviceTab() {
  const { data: caps, isLoading: capsLoading } = useQuery({
    queryKey: ['device-caps'],
    queryFn: aelinApi.deviceCapabilities,
  })

  const { data: procs, refetch } = useQuery({
    queryKey: ['device-procs'],
    queryFn: () => aelinApi.deviceProcesses('cpu'),
  })

  const optimize = useMutation({
    mutationFn: () => aelinApi.deviceOptimize(),
    onSuccess: (res) => { toast.success(`优化了 ${res.optimized_count} 个进程`); refetch() },
    onError: () => toast.error('优化失败'),
  })

  const killProc = useMutation({
    mutationFn: (pid: number) => aelinApi.deviceProcessAction(pid, 'terminate'),
    onSuccess: () => { toast.success('已终止'); refetch() },
    onError: () => toast.error('终止失败'),
  })

  const applyMode = useMutation({
    mutationFn: (mode: string) => aelinApi.deviceModeApply(mode),
    onSuccess: (res) => toast.success(res.summary),
    onError: () => toast.error('应用失败'),
  })

  return (
    <div className="space-y-6">
      {/* Capabilities */}
      <div>
        <div className="text-xs text-[var(--color-text-muted)] mb-2 flex items-center gap-1"><Shield size={13} /> 设备信息</div>
        {capsLoading ? <div className="text-xs text-[var(--color-text-muted)]">加载中…</div> : (
          <div className="text-xs space-y-1">
            <div>平台: {caps?.platform ?? '—'}</div>
            {caps?.notes?.map((n, i) => <div key={i} className="text-[var(--color-text-muted)]">{n}</div>)}
          </div>
        )}
      </div>

      {/* Quick Modes */}
      <div>
        <div className="text-xs text-[var(--color-text-muted)] mb-2">快捷模式</div>
        <div className="flex gap-2 flex-wrap">
          {['focus', 'performance', 'battery'].map(mode => (
            <button key={mode} onClick={() => applyMode.mutate(mode)}
              className="px-3 py-1.5 text-xs rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-accent-soft)]">
              {mode === 'focus' ? '🎯 专注' : mode === 'performance' ? '⚡ 性能' : '🔋 省电'}
            </button>
          ))}
        </div>
      </div>

      {/* Optimize */}
      <div className="flex items-center gap-3">
        <button onClick={() => optimize.mutate()} disabled={optimize.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90 disabled:opacity-50">
          <Zap size={13} /> {optimize.isPending ? '优化中…' : '一键优化'}
        </button>
      </div>

      {/* Process List */}
      <div>
        <div className="text-xs text-[var(--color-text-muted)] mb-2 flex items-center gap-1"><Cpu size={13} /> 进程 (Top {procs?.items?.length ?? 0})</div>
        <div className="space-y-1.5">
          {(procs?.items ?? []).slice(0, 15).map(p => (
            <div key={p.pid} className="flex items-center gap-2 text-xs py-1 px-2 rounded-lg border border-[var(--color-border)]">
              <span className="flex-1 truncate font-mono">{p.name}</span>
              <span className="text-[var(--color-text-muted)] w-14 text-right">{p.cpu_percent.toFixed(1)}%</span>
              <span className="text-[var(--color-text-muted)] w-14 text-right">{p.memory_mb.toFixed(0)} MB</span>
              {p.anomaly_score > 0.5 && <span className="text-[var(--color-orange)]" title={p.anomaly_reasons.join(', ')}>⚠️</span>}
              {p.safe_to_terminate && (
                <button onClick={() => killProc.mutate(p.pid)} className="text-[var(--color-danger)] hover:underline ml-1">终止</button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
