import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { contactsApi } from '@/shared/api/contacts'
import { sourceIcon, relativeTime } from '@/shared/utils/format'
import { Search } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export function SignalsView() {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const navigate = useNavigate()

  const { data: contacts = [], isLoading } = useQuery({
    queryKey: ['contacts', search],
    queryFn: () => contactsApi.list(search ? { q: search } : undefined),
  })

  const filtered = filter === 'unread' ? contacts.filter(c => c.unread_count > 0) : contacts

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-panel)] shrink-0">
        <h1 className="text-lg font-semibold mb-2" style={{ fontFamily: 'var(--font-heading)' }}>Signals</h1>
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索联系人…"
              className="w-full pl-8 pr-3 py-1.5 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg text-sm focus:outline-none focus:border-[var(--color-border-strong)]" />
          </div>
          <div className="flex rounded-lg border border-[var(--color-border)] overflow-hidden text-xs">
            {(['all', 'unread'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={cn('px-3 py-1.5', filter === f ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]')}>
                {f === 'all' ? '全部' : '未读'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">加载中…</div>
        )}
        {!isLoading && filtered.length === 0 && (
          <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">
            {search ? '未找到匹配联系人' : '暂无数据源，请在设置中添加'}
          </div>
        )}
        {filtered.map(c => (
          <button key={c.id} onClick={() => navigate(`/signals/${c.id}`)}
            className="w-full flex items-start gap-3 px-4 py-3 border-b border-[var(--color-border)] hover:bg-[var(--color-accent-soft)] transition-colors text-left">
            <div className="shrink-0 w-9 h-9 rounded-full bg-[var(--color-accent-soft)] flex items-center justify-center text-sm overflow-hidden">
              {c.avatar_url
                ? <img src={c.avatar_url} className="w-full h-full object-cover" />
                : <span>{sourceIcon(c.latest_source)}</span>}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm truncate">{c.display_name}</span>
                <span className="text-[11px] text-[var(--color-text-muted)] shrink-0 ml-2">{relativeTime(c.latest_received_at)}</span>
              </div>
              <div className="text-xs text-[var(--color-text-muted)] truncate">{c.latest_subject || c.handle}</div>
              {c.latest_preview && <div className="text-xs text-[var(--color-text-muted)] truncate opacity-60 mt-0.5">{c.latest_preview}</div>}
            </div>
            {c.unread_count > 0 && (
              <span className="shrink-0 min-w-[20px] h-5 rounded-full bg-[var(--color-orange)] text-white text-[10px] font-bold flex items-center justify-center px-1.5">
                {c.unread_count}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
