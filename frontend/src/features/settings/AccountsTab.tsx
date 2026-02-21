import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { accountsApi } from '@/shared/api/accounts'
import type { ConnectedAccountCreate } from '@/shared/api/types'
import { sourceIcon, relativeTime } from '@/shared/utils/format'
import { Plus, Trash2, RefreshCw, ExternalLink, X } from 'lucide-react'
import toast from 'react-hot-toast'

const PROVIDERS = [
  { id: 'imap', label: '邮箱 (IMAP)' },
  { id: 'gmail', label: 'Gmail (OAuth)' },
  { id: 'rss', label: 'RSS 订阅' },
  { id: 'bilibili', label: 'Bilibili' },
  { id: 'x', label: 'X / Twitter' },
  { id: 'weibo', label: '微博' },
  { id: 'douyin', label: '抖音' },
  { id: 'zhihu', label: '知乎' },
  { id: 'xiaohongshu', label: '小红书' },
  { id: 'forward', label: '邮件转发' },
]

export function AccountsTab() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountsApi.list,
  })

  const remove = useMutation({
    mutationFn: accountsApi.remove,
    onSuccess: () => { toast.success('已删除'); qc.invalidateQueries({ queryKey: ['accounts'] }) },
    onError: () => toast.error('删除失败'),
  })

  const syncMut = useMutation({
    mutationFn: accountsApi.sync,
    onSuccess: (res) => toast.success(`同步任务已启动 (${res.job_id})`),
    onError: () => toast.error('同步失败'),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--color-text-muted)]">{accounts.length} 个数据源</span>
        <button onClick={() => setShowAdd(true)} className="aelin-btn aelin-btn-primary">
          <Plus size={13} /> 添加数据源
        </button>
      </div>

      {isLoading && <div className="text-sm text-[var(--color-text-muted)]">加载中…</div>}

      <div className="space-y-2">
        {accounts.map(acc => (
          <div key={acc.id} className="aelin-card flex items-center gap-3 p-3">
            <span className="text-lg">{sourceIcon(acc.provider)}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{acc.identifier || acc.provider}</div>
              <div className="text-[11px] text-[var(--color-text-muted)]">
                {acc.provider}{acc.last_synced_at ? ` · 同步于 ${relativeTime(acc.last_synced_at)}` : ''}
              </div>
            </div>
            <button onClick={() => syncMut.mutate(acc.id)} title="同步" className="aelin-btn h-8 w-8 p-0">
              <RefreshCw size={14} />
            </button>
            <button onClick={() => { if (confirm('确定删除？')) remove.mutate(acc.id) }} title="移除" className="aelin-btn h-8 w-8 p-0">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      {showAdd && <AddAccountSheet onClose={() => setShowAdd(false)} />}
    </div>
  )
}

/* ─── Add Account Sheet ─── */
function AddAccountSheet({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [provider, setProvider] = useState('')
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (k: string, v: string) => setForm(p => ({...p, [k]: v}))

  const createMut = useMutation({
    mutationFn: () => {
      const body: ConnectedAccountCreate = { provider, ...form } as any
      return accountsApi.create(body)
    },
    onSuccess: () => { toast.success('添加成功'); qc.invalidateQueries({ queryKey: ['accounts'] }); onClose() },
    onError: () => toast.error('添加失败'),
  })

  const oauthStart = useMutation({
    mutationFn: (p: string) => accountsApi.oauthStart(p),
    onSuccess: (res) => { window.open(res.auth_url, '_blank'); toast.success('请在新窗口完成授权'); onClose() },
    onError: () => toast.error('OAuth 启动失败'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div onClick={e => e.stopPropagation()}
        className="relative w-full sm:max-w-lg bg-[var(--color-panel)] border border-[var(--color-border)] rounded-t-2xl sm:rounded-2xl p-5 space-y-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold" style={{ fontFamily: 'var(--font-heading)' }}>添加数据源</h2>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-[var(--color-accent-soft)]"><X size={18} /></button>
        </div>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">类型</span>
          <select value={provider} onChange={e => { setProvider(e.target.value); setForm({}) }} className="aelin-select">
            <option value="">选择数据源…</option>
            {PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>

        {/* OAuth providers */}
        {provider === 'gmail' && (
          <button onClick={() => oauthStart.mutate('gmail')} className="aelin-btn w-full justify-center">
            <ExternalLink size={14} /> 通过 Google 授权
          </button>
        )}

        {/* IMAP */}
        {provider === 'imap' && (
          <div className="space-y-3">
            <Field label="IMAP 主机" value={form.imap_host} onChange={v => set('imap_host', v)} placeholder="imap.example.com" />
            <Field label="端口" value={form.imap_port} onChange={v => set('imap_port', v)} placeholder="993" />
            <Field label="用户名" value={form.imap_username} onChange={v => set('imap_username', v)} placeholder="user@example.com" />
            <Field label="密码" value={form.imap_password} onChange={v => set('imap_password', v)} placeholder="应用密码" type="password" />
            <Field label="邮箱文件夹" value={form.imap_mailbox} onChange={v => set('imap_mailbox', v)} placeholder="INBOX" />
          </div>
        )}

        {/* RSS */}
        {provider === 'rss' && (
          <div className="space-y-3">
            <Field label="Feed URL" value={form.feed_url} onChange={v => set('feed_url', v)} placeholder="https://example.com/feed.xml" />
            <Field label="显示名称" value={form.feed_display_name} onChange={v => set('feed_display_name', v)} placeholder="可选" />
          </div>
        )}

        {/* Bilibili */}
        {provider === 'bilibili' && (
          <Field label="Bilibili UID" value={form.bilibili_uid} onChange={v => set('bilibili_uid', v)} placeholder="UP 主 UID" />
        )}

        {/* X / Twitter */}
        {provider === 'x' && (
          <Field label="X 用户名" value={form.x_username} onChange={v => set('x_username', v)} placeholder="不含 @" />
        )}

        {/* Weibo / Douyin / Zhihu / Xiaohongshu — just identifier */}
        {['weibo', 'douyin', 'zhihu', 'xiaohongshu'].includes(provider) && (
          <Field label="用户 ID 或链接" value={form.identifier} onChange={v => set('identifier', v)} placeholder="用户主页 ID" />
        )}

        {/* Forward */}
        {provider === 'forward' && (
          <div className="space-y-3">
            <Field label="显示名称" value={form.forward_display_name} onChange={v => set('forward_display_name', v)} placeholder="转发来源名称" />
            <Field label="来源邮箱" value={form.forward_source_email} onChange={v => set('forward_source_email', v)} placeholder="user@example.com" />
          </div>
        )}

        {provider && provider !== 'gmail' && (
          <button onClick={() => createMut.mutate()} disabled={createMut.isPending} className="aelin-btn aelin-btn-primary w-full justify-center">
            {createMut.isPending ? '添加中…' : '确认添加'}
          </button>
        )}
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text' }: {
  label: string; value?: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <label className="block text-xs space-y-1">
      <span className="text-[var(--color-text-muted)]">{label}</span>
      <input type={type} value={value ?? ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} className="aelin-input" />
    </label>
  )
}
