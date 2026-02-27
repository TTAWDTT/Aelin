import { useEffect, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BellOff, CirclePower, Focus } from 'lucide-react'
import toast from 'react-hot-toast'
import { aelinApi } from '@/shared/api/aelin'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { useLayoutStore } from '@/shared/stores/layoutStore'
import { useNotifStore } from '@/shared/stores/notifStore'

export function FocusView() {
  const queryClient = useQueryClient()
  const { focusModeEnabled, setFocusModeEnabled } = useLayoutStore()
  const { notificationsMuted, setNotificationsMuted } = useNotifStore()

  const { data: modeState } = useQuery({
    queryKey: ['device-mode'],
    queryFn: aelinApi.deviceMode,
  })

  const { data: notifications } = useQuery({
    queryKey: ['notifications', 'global', 'default'],
    queryFn: aelinApi.notifications,
    enabled: !notificationsMuted,
    refetchInterval: notificationsMuted ? false : 20_000,
  })

  const { data: proactive } = useQuery({
    queryKey: ['proactive', 'global', 'default'],
    queryFn: () => aelinApi.proactivePoll('default'),
    enabled: !notificationsMuted,
    refetchInterval: notificationsMuted ? false : 12_000,
  })

  const liveTotal = useMemo(() => {
    if (notificationsMuted) return 0
    const ids = new Set<string>()
    for (const row of notifications?.items || []) {
      const id = String(row.id || '').trim()
      if (id) ids.add(id)
    }
    for (const row of proactive?.items || []) {
      const id = [String(row.id || '').trim(), String(row.ts || '').trim()].join('|')
      if (id) ids.add(id)
    }
    return ids.size
  }, [notificationsMuted, notifications?.items, proactive?.items])

  useEffect(() => {
    if (!modeState?.mode) return
    setFocusModeEnabled(modeState.mode === 'focus')
  }, [modeState?.mode, setFocusModeEnabled])

  const applyMode = useMutation({
    mutationFn: (mode: 'focus' | 'normal') => aelinApi.deviceModeApply(mode),
    onSuccess: (result, mode) => {
      const isFocus = mode === 'focus'
      setFocusModeEnabled(isFocus)
      setNotificationsMuted(isFocus)
      toast.success(result.summary)
      queryClient.invalidateQueries({ queryKey: ['device-mode'] })
    },
    onError: () => toast.error('模式切换失败'),
  })

  const activeMode = focusModeEnabled ? 'focus' : (modeState?.mode ?? 'normal')

  return (
    <PageScaffold title="专注模式" subtitle="一键进入静默状态，暂停通知打扰">
      <div className="space-y-4">
        <div className="aelin-card p-4">
          <div className="mb-3 flex items-center gap-2 text-sm">
            <Focus size={15} />
            当前状态：{activeMode === 'focus' ? '专注中' : '正常模式'}
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            {modeState?.summary || '开启后将关闭通知并切换设备到专注配置。'}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="aelin-btn aelin-btn-primary"
              onClick={() => applyMode.mutate('focus')}
              disabled={applyMode.isPending || activeMode === 'focus'}
            >
              <BellOff size={14} />
              开启专注
            </button>
            <button
              className="aelin-btn"
              onClick={() => applyMode.mutate('normal')}
              disabled={applyMode.isPending || activeMode !== 'focus'}
            >
              <CirclePower size={14} />
              恢复正常
            </button>
          </div>
        </div>

        <div className="aelin-card p-4">
          <p className="text-xs text-[var(--color-text-muted)]">通知状态</p>
          <div className="mt-2 text-sm">
            {notificationsMuted ? '已静默（0 通知）' : `实时通知开启（${liveTotal} 条）`}
          </div>
          <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
            常规通知 {notifications?.total ?? 0} · 主动提醒 {proactive?.total ?? 0}
          </p>
          {!notificationsMuted && (proactive?.items?.length || 0) > 0 ? (
            <div className="mt-3 space-y-1.5">
              {(proactive?.items || []).slice(0, 4).map((row) => (
                <div key={`${row.id}-${row.ts || ''}`} className="rounded-lg border border-[var(--color-border)] px-2 py-1.5">
                  <div className="text-xs font-medium">{row.title}</div>
                  {row.detail ? <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)] line-clamp-2">{row.detail}</div> : null}
                </div>
              ))}
            </div>
          ) : null}
          {!notificationsMuted && (proactive?.items?.length || 0) <= 0 ? (
            <div className="mt-3 text-[11px] text-[var(--color-text-muted)]">当前暂无主动提醒</div>
          ) : null}
          {notificationsMuted ? (
            <div className="mt-3 text-[11px] text-[var(--color-text-muted)]">专注模式下已暂停主动提醒轮询</div>
          ) : null}
          <div className="mt-3">
            <button
              className="aelin-btn h-8 px-3 text-xs"
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: ['notifications', 'global', 'default'] })
                queryClient.invalidateQueries({ queryKey: ['proactive', 'global', 'default'] })
              }}
            >
              立即刷新提醒
            </button>
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
