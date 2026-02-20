import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contactsApi } from '@/shared/api/contacts'
import { agentApi } from '@/shared/api/agent'
import { relativeTime, sourceIcon } from '@/shared/utils/format'
import { ArrowLeft, BookOpen, CheckCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'

export function SignalThreadView() {
  const { contactId } = useParams<{ contactId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const cid = Number(contactId)

  const { data: contacts = [] } = useQuery({ queryKey: ['contacts'], queryFn: () => contactsApi.list() })
  const contact = contacts.find(c => c.id === cid)

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['messages', cid],
    queryFn: () => contactsApi.messages(cid),
    enabled: !!cid,
  })

  const markRead = useMutation({
    mutationFn: () => contactsApi.markRead(cid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['contacts'] }); toast.success('已标记已读') },
  })

  const [summaryMap, setSummaryMap] = useState<Record<number, string>>({})
  const handleSummarize = async (msgId: number, text: string) => {
    try {
      const res = await agentApi.summarize(text)
      setSummaryMap(prev => ({ ...prev, [msgId]: res.summary }))
    } catch { toast.error('摘要失败') }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-panel)] shrink-0 flex items-center gap-3">
        <button onClick={() => navigate('/signals')} className="p-1 rounded-lg hover:bg-[var(--color-accent-soft)]">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold truncate">{contact?.display_name || '联系人'}</h2>
          <div className="text-[11px] text-[var(--color-text-muted)]">{contact?.handle}</div>
        </div>
        <button onClick={() => markRead.mutate()}
          className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-accent-soft)]">
          <CheckCheck size={14} /> 全部已读
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {isLoading && <div className="text-sm text-[var(--color-text-muted)] text-center">加载中…</div>}
        {messages.map(msg => (
          <div key={msg.id} className="border border-[var(--color-border)] rounded-xl p-3 bg-[var(--color-panel)]">
            <div className="flex items-start justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-sm">{sourceIcon(msg.source)}</span>
                <span className="font-medium text-sm truncate">{msg.subject || '(无标题)'}</span>
              </div>
              <span className="text-[11px] text-[var(--color-text-muted)] whitespace-nowrap">{relativeTime(msg.received_at)}</span>
            </div>
            <div className="text-xs text-[var(--color-text-muted)] mb-2">来自 {msg.sender}</div>
            <div className="text-sm leading-relaxed" style={{ fontFamily: 'var(--font-body)' }}>
              {msg.body_preview}
            </div>
            {summaryMap[msg.id] && (
              <div className="mt-2 p-2 rounded-lg bg-[var(--color-bg)] text-xs border border-[var(--color-border)]">
                <div className="font-semibold text-[var(--color-text-muted)] mb-1">AI 摘要</div>
                <ReactMarkdown>{summaryMap[msg.id]}</ReactMarkdown>
              </div>
            )}
            <div className="flex gap-2 mt-2">
              <button onClick={() => handleSummarize(msg.id, msg.body_preview)}
                className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-[var(--color-border)] hover:bg-[var(--color-accent-soft)]">
                <BookOpen size={12} /> 总结
              </button>
            </div>
          </div>
        ))}
        {!isLoading && messages.length === 0 && (
          <div className="text-center text-sm text-[var(--color-text-muted)] py-8">暂无消息</div>
        )}
      </div>
    </div>
  )
}
