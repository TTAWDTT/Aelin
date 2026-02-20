import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { aelinApi } from '@/shared/api/aelin'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'

interface Props { onClose: () => void }

export function TrackConfirmSheet({ onClose }: Props) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ target: '', source: 'web', description: '', interval: '3600' })

  const confirm = useMutation({
    mutationFn: () => aelinApi.trackConfirm({
      target: form.target,
      source: form.source,
      description: form.description || undefined,
      interval_seconds: Number(form.interval),
    }),
    onSuccess: () => {
      toast.success('追踪目标已创建')
      qc.invalidateQueries({ queryKey: ['tracking'] })
      onClose()
    },
    onError: () => toast.error('创建失败'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div onClick={e => e.stopPropagation()}
        className="relative w-full sm:max-w-md bg-[var(--color-panel)] border border-[var(--color-border)] rounded-t-2xl sm:rounded-2xl p-5 space-y-4 animate-[slideUp_0.2s_ease-out]">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold" style={{ fontFamily: 'var(--font-heading)' }}>新建追踪</h2>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-[var(--color-accent-soft)]"><X size={18} /></button>
        </div>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">追踪目标</span>
          <input value={form.target} onChange={e => setForm(p => ({...p, target: e.target.value}))} placeholder="例：某个人、某个关键词、某个网站URL…"
            className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]" />
        </label>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">数据来源</span>
          <select value={form.source} onChange={e => setForm(p => ({...p, source: e.target.value}))}
            className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]">
            <option value="web">网页</option>
            <option value="x">X / Twitter</option>
            <option value="weibo">微博</option>
            <option value="bilibili">Bilibili</option>
            <option value="douyin">抖音</option>
            <option value="email">邮箱</option>
          </select>
        </label>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">检查间隔</span>
          <select value={form.interval} onChange={e => setForm(p => ({...p, interval: e.target.value}))}
            className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]">
            <option value="600">每 10 分钟</option>
            <option value="1800">每 30 分钟</option>
            <option value="3600">每 1 小时</option>
            <option value="21600">每 6 小时</option>
            <option value="86400">每天</option>
          </select>
        </label>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">备注（可选）</span>
          <input value={form.description} onChange={e => setForm(p => ({...p, description: e.target.value}))} placeholder="补充说明"
            className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]" />
        </label>

        <button onClick={() => confirm.mutate()} disabled={!form.target.trim() || confirm.isPending}
          className="w-full py-2.5 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90 disabled:opacity-50">
          {confirm.isPending ? '创建中…' : '确认创建'}
        </button>
      </div>
    </div>
  )
}
