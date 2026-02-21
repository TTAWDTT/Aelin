import { useEffect } from 'react'
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
  const { notificationsMuted, setNotificationsMuted, setUnreadCount } = useNotifStore()

  const { data: modeState } = useQuery({
    queryKey: ['device-mode'],
    queryFn: aelinApi.deviceMode,
  })

  const { data: notifications } = useQuery({
    queryKey: ['notifications', 'focus-page'],
    queryFn: aelinApi.notifications,
    enabled: !notificationsMuted,
    refetchInterval: notificationsMuted ? false : 20_000,
  })

  useEffect(() => {
    if (notificationsMuted) {
      setUnreadCount(0)
      return
    }
    setUnreadCount(notifications?.total ?? 0)
  }, [notifications?.total, notificationsMuted, setUnreadCount])

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
      if (isFocus) setUnreadCount(0)
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
            {notificationsMuted ? '已静默（0 通知）' : `实时通知开启（${notifications?.total ?? 0} 条）`}
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
