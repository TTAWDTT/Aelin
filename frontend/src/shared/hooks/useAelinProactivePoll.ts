import { useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { aelinApi } from '@/shared/api/aelin'
import { useNotifStore } from '@/shared/stores/notifStore'

function _makeKey(parts: string[]): string {
  return parts.map((it) => String(it || '').trim()).join('|')
}

export function useAelinProactivePoll(workspace = 'default') {
  const { notificationsMuted, setUnreadCount } = useNotifStore()
  const seenRef = useRef<Set<string>>(new Set())

  const notificationsQuery = useQuery({
    queryKey: ['notifications', 'global', workspace],
    queryFn: aelinApi.notifications,
    enabled: !notificationsMuted,
    refetchInterval: notificationsMuted ? false : 20_000,
  })

  const proactiveQuery = useQuery({
    queryKey: ['proactive', 'global', workspace],
    queryFn: () => aelinApi.proactivePoll(workspace),
    enabled: !notificationsMuted,
    refetchInterval: notificationsMuted ? false : 12_000,
  })

  const mergedTotal = useMemo(() => {
    if (notificationsMuted) return 0
    const ids = new Set<string>()
    for (const row of notificationsQuery.data?.items || []) {
      const id = String(row.id || '').trim()
      if (id) ids.add(id)
    }
    for (const row of proactiveQuery.data?.items || []) {
      const id = _makeKey([row.id, row.title, row.ts || ''])
      if (id) ids.add(id)
    }
    return ids.size
  }, [notificationsMuted, notificationsQuery.data?.items, proactiveQuery.data?.items])

  useEffect(() => {
    setUnreadCount(mergedTotal)
  }, [mergedTotal, setUnreadCount])

  useEffect(() => {
    if (notificationsMuted) return
    const rows = proactiveQuery.data?.items || []
    if (!rows.length) return

    const fresh = rows.filter((row) => {
      const key = _makeKey([row.id, row.title, row.ts || ''])
      if (!key || seenRef.current.has(key)) return false
      seenRef.current.add(key)
      return true
    })
    if (!fresh.length) return

    for (const row of fresh.slice(0, 2)) {
      const title = String(row.title || '').trim() || '新动态'
      const detail = String(row.detail || '').trim()
      toast(title + (detail ? `\n${detail}` : ''), {
        duration: 3500,
        id: `proactive:${row.id}`,
      })
    }
  }, [notificationsMuted, proactiveQuery.data?.items])

  return {
    notifications: notificationsQuery.data,
    proactive: proactiveQuery.data,
    unread: mergedTotal,
  }
}
