import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime, severityColor } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { ArrowLeft, Play } from 'lucide-react'
import toast from 'react-hot-toast'

import type {
  AelinTrackingChangeItem,
  AelinTrackingSnapshotItem,
  AelinTrackingTargetUpdateRequest,
} from '@/shared/api/types'
import { PageScaffold } from '@/shared/components/PageScaffold'

type Tab = 'changes' | 'snapshots' | 'settings'

function formatDiff(diff?: Record<string, unknown>): string {
  if (!diff || typeof diff !== 'object' || Array.isArray(diff) || Object.keys(diff).length === 0) {
    return ''
  }
  try {
    return JSON.stringify(diff, null, 2)
  } catch {
    return ''
  }
}

function snapshotSummary(item: AelinTrackingSnapshotItem): string {
  const payload = item.normalized_payload_json
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const records = Array.isArray(payload.items) ? payload.items : []
    const first = records.length > 0 && records[0] && typeof records[0] === 'object'
      ? (records[0] as Record<string, unknown>)
      : null
    const firstTitle = first ? String(first.title || first.url || first.key || '').trim() : ''
    if (firstTitle) {
      return firstTitle
    }
    if (records.length > 0) {
      return `共 ${records.length} 条标准化结果`
    }
  }
  if (item.fetch_error) return `抓取错误: ${item.fetch_error}`
  return `版本 v${item.version_no} · ${item.fetch_status}`
}

export function TrackingDetailView() {
  const { targetId } = useParams<{ targetId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const id = Number(targetId)
  const [tab, setTab] = useState<Tab>('changes')

  /* ---------- queries ---------- */
  const { data: tracking } = useQuery({
    queryKey: ['tracking'],
    queryFn: () => aelinApi.trackingList(),
  })
  const item = tracking?.items?.find(i => i.target_id === id)

  const { data: changes, isLoading: changesLoading } = useQuery({
    queryKey: ['tracking-changes', id],
    queryFn: () => aelinApi.trackingChanges(id),
    enabled: tab === 'changes',
  })

  const { data: snapshots, isLoading: snapshotsLoading } = useQuery({
    queryKey: ['tracking-snapshots', id],
    queryFn: () => aelinApi.trackingSnapshots(id),
    enabled: tab === 'snapshots',
  })

  /* ---------- mutations ---------- */
  const ack = useMutation({
    mutationFn: (changeIds: number[]) => aelinApi.trackingAck(id, changeIds),
    onSuccess: (res) => {
      toast.success(res.message || '已标记已读')
      qc.invalidateQueries({ queryKey: ['tracking-changes', id] })
      qc.invalidateQueries({ queryKey: ['tracking'] })
    },
  })

  const run = useMutation({
    mutationFn: () => aelinApi.trackingRun(id),
    onSuccess: (res) => { toast.success(res.message); qc.invalidateQueries({ queryKey: ['tracking'] }) },
  })

  const update = useMutation({
    mutationFn: (data: AelinTrackingTargetUpdateRequest) => aelinApi.trackingUpdate(id, data),
    onSuccess: () => { toast.success('已更新'); qc.invalidateQueries({ queryKey: ['tracking'] }) },
  })

  const tabs: { key: Tab; label: string }[] = [
    { key: 'changes', label: '变化' },
    { key: 'snapshots', label: '快照' },
    { key: 'settings', label: '设置' },
  ]

  return (
    <PageScaffold
      title={item?.target ?? `#${id}`}
      subtitle={`${item?.source ?? 'web'} · ${item?.status ?? 'unknown'}`}
      headerActions={
        <div className="flex w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end">
          <button onClick={() => navigate('/tracking')} className="aelin-btn">
            <ArrowLeft size={14} />
            返回
          </button>
          <button onClick={() => run.mutate()} className="aelin-btn">
            <Play size={11} />
            立即运行
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        <div className="aelin-segment">
          {tabs.map((t) => (
            <button key={t.key} data-active={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'changes' && <ChangesTab changes={changes?.items ?? []} loading={changesLoading} onAck={(ids) => ack.mutate(ids)} />}
        {tab === 'snapshots' && <SnapshotsTab snapshots={snapshots?.items ?? []} loading={snapshotsLoading} />}
        {tab === 'settings' && <SettingsTab item={item} onUpdate={(d) => update.mutate(d)} isPending={update.isPending} />}
      </div>
    </PageScaffold>
  )
}

/* ---------- sub-components ---------- */

function ChangesTab({
  changes,
  loading,
  onAck,
}: {
  changes: AelinTrackingChangeItem[]
  loading: boolean
  onAck: (ids: number[]) => void
}) {
  if (loading) return <div className="text-sm text-[var(--color-text-muted)] text-center py-8">加载中…</div>
  if (!changes.length) return <div className="text-sm text-[var(--color-text-muted)] text-center py-8">暂无变化记录</div>

  const unreadIds = changes.filter(c => !c.acked).map(c => c.id).filter(Boolean)

  return (
    <div className="space-y-3">
      {unreadIds.length > 0 && (
        <button onClick={() => onAck(unreadIds)}
          className="text-[11px] text-[var(--color-accent)] hover:underline">全部标记已读 ({unreadIds.length})</button>
      )}
      {changes.map((c, i: number) => (
        <div key={c.id ?? i} className={cn('aelin-card p-3 text-sm',
          c.acked ? 'bg-transparent' : 'border-[var(--color-border-strong)]')}>
          <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)] mb-1">
            <span className={c.severity ? severityColor(c.severity) : ''}>{c.change_type ?? '变化'}</span>
            {c.created_at && <span>{relativeTime(c.created_at)}</span>}
          </div>
          <div className="text-[13px]">{c.summary ?? c.title ?? JSON.stringify(c)}</div>
          {formatDiff(c.diff_json) && (
            <pre className="mt-2 text-[11px] bg-[var(--color-bg-elevated)] rounded p-2 overflow-x-auto whitespace-pre-wrap">
              {formatDiff(c.diff_json)}
            </pre>
          )}
        </div>
      ))}
    </div>
  )
}

function SnapshotsTab({ snapshots, loading }: { snapshots: AelinTrackingSnapshotItem[]; loading: boolean }) {
  if (loading) return <div className="text-sm text-[var(--color-text-muted)] text-center py-8">加载中…</div>
  if (!snapshots.length) return <div className="text-sm text-[var(--color-text-muted)] text-center py-8">暂无快照</div>

  return (
    <div className="space-y-3">
      {snapshots.map((s, i: number) => (
        <div key={s.id ?? i} className="aelin-card p-3">
          <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)] mb-1">
            <span>{`v${s.version_no} · ${s.fetch_status ?? 'ok'}`}</span>
            {s.fetched_at && <span>{relativeTime(s.fetched_at)}</span>}
          </div>
          <div className="text-[13px]">{snapshotSummary(s)}</div>
        </div>
      ))}
    </div>
  )
}

function SettingsTab({ item, onUpdate, isPending }: { item: any; onUpdate: (d: AelinTrackingTargetUpdateRequest) => void; isPending: boolean }) {
  const [interval, setInterval_] = useState(String(item?.interval_seconds ?? 3600))
  const [status, setStatus] = useState(item?.status ?? 'active')

  return (
    <div className="max-w-md space-y-5">
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">状态</span>
        <select value={status} onChange={e => setStatus(e.target.value)} className="aelin-select">
          <option value="active">活跃</option>
          <option value="paused">暂停</option>
        </select>
      </label>

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">检查间隔</span>
        <select value={interval} onChange={e => setInterval_(e.target.value)} className="aelin-select">
          <option value="600">每 10 分钟</option>
          <option value="1800">每 30 分钟</option>
          <option value="3600">每 1 小时</option>
          <option value="21600">每 6 小时</option>
          <option value="86400">每天</option>
        </select>
      </label>

      <button onClick={() => onUpdate({ status, interval_seconds: Number(interval) })} disabled={isPending} className="aelin-btn aelin-btn-primary">
        {isPending ? '保存中…' : '保存'}
      </button>
    </div>
  )
}
