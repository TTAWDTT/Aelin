import { useQuery } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
export function DeviceTab() {
  const { data: caps, isLoading: capsLoading } = useQuery({
    queryKey: ['device-caps'],
    queryFn: aelinApi.deviceCapabilities,
  })

  return (
    <div className="space-y-1 text-right">
      <div className="text-[11px] tracking-[0.12em] text-[var(--color-text-muted)]">系统平台</div>
      {capsLoading ? (
        <div className="text-xs text-[var(--color-text-muted)]">加载中…</div>
      ) : (
        <div className="text-sm font-medium text-[var(--color-text)]">{caps?.platform ?? '—'}</div>
      )}
    </div>
  )
}
