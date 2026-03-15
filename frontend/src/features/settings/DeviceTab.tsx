import { useQuery } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
import { Shield } from 'lucide-react'

export function DeviceTab() {
  const { data: caps, isLoading: capsLoading } = useQuery({
    queryKey: ['device-caps'],
    queryFn: aelinApi.deviceCapabilities,
  })

  return (
    <div className="space-y-6">
      {/* Capabilities */}
      <div className="aelin-card p-3">
        <div className="text-xs text-[var(--color-text-muted)] mb-2 flex items-center gap-1"><Shield size={13} /> 设备信息</div>
        {capsLoading ? <div className="text-xs text-[var(--color-text-muted)]">加载中…</div> : (
          <div className="text-xs space-y-1">
            <div>平台: {caps?.platform ?? '—'}</div>
            {caps?.notes?.map((n, i) => <div key={i} className="text-[var(--color-text-muted)]">{n}</div>)}
          </div>
        )}
      </div>
    </div>
  )
}
