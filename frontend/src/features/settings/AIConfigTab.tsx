import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentApi } from '@/shared/api/agent'
import toast from 'react-hot-toast'
import { FlaskConical } from 'lucide-react'

export function AIConfigTab() {
  const qc = useQueryClient()

  const { data: config, isLoading } = useQuery({ queryKey: ['agent-config'], queryFn: agentApi.config })
  const { data: catalog } = useQuery({ queryKey: ['agent-catalog'], queryFn: agentApi.catalog })

  const [form, setForm] = useState({ provider: '', base_url: '', model: '', temperature: '0.5', api_key: '' })

  useEffect(() => {
    if (config) {
      setForm({
        provider: config.provider || '',
        base_url: config.base_url || '',
        model: config.model || '',
        temperature: String(config.temperature ?? 0.5),
        api_key: '',
      })
    }
  }, [config])

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        provider: form.provider || undefined,
        base_url: form.base_url || undefined,
        model: form.model || undefined,
        temperature: Number(form.temperature),
      }
      if (form.api_key.trim()) body.api_key = form.api_key
      return agentApi.updateConfig(body as any)
    },
    onSuccess: () => { toast.success('已保存'); setForm(p => ({...p, api_key: ''})); qc.invalidateQueries({ queryKey: ['agent-config'] }) },
    onError: () => toast.error('保存失败'),
  })

  const test = useMutation({
    mutationFn: agentApi.test,
    onSuccess: (res) => {
      if (res.ok) toast.success(`✅ ${res.message}`)
      else toast.error(`❌ ${res.message}`)
    },
    onError: () => toast.error('测试失败'),
  })

  const providers = catalog?.providers ?? []
  const currentProvider = providers.find(p => p.id === form.provider)

  if (isLoading) return <div className="text-sm text-[var(--color-text-muted)]">加载中…</div>

  return (
    <div className="max-w-md space-y-5">
      {/* Provider */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">AI 提供商</span>
        <select value={form.provider} onChange={e => setForm(p => ({...p, provider: e.target.value, model: ''}))} className="aelin-select">
          <option value="">选择提供商…</option>
          {providers.map(p => <option key={p.id} value={p.id}>{p.name} ({p.model_count} 模型)</option>)}
        </select>
      </label>

      {/* Model */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">模型</span>
        <select value={form.model} onChange={e => setForm(p => ({...p, model: e.target.value}))} className="aelin-select">
          <option value="">选择模型…</option>
          {(currentProvider?.models ?? []).map(m => (
            <option key={m.id} value={m.id}>
              {m.name}{m.reasoning ? ' 🧠' : ''}{m.tool_call ? ' 🔧' : ''}
            </option>
          ))}
        </select>
      </label>

      {/* Base URL */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">API 地址（可选）</span>
        <input value={form.base_url} onChange={e => setForm(p => ({...p, base_url: e.target.value}))} placeholder="留空则使用默认" className="aelin-input" />
      </label>

      {/* API Key */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">API Key {config?.has_api_key && <span className="text-[var(--color-green)]">（已配置）</span>}</span>
        <input type="password" value={form.api_key} onChange={e => setForm(p => ({...p, api_key: e.target.value}))} placeholder={config?.has_api_key ? '输入新 Key 覆盖' : '输入 API Key'} className="aelin-input" />
      </label>

      {/* Temperature */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">Temperature: {form.temperature}</span>
        <input type="range" min="0" max="2" step="0.1" value={form.temperature} onChange={e => setForm(p => ({...p, temperature: e.target.value}))}
          className="w-full accent-[var(--color-accent)]" />
      </label>

      <div className="flex gap-3">
        <button onClick={() => save.mutate()} disabled={save.isPending} className="aelin-btn aelin-btn-primary">
          {save.isPending ? '保存中…' : '保存配置'}
        </button>
        <button onClick={() => test.mutate()} disabled={test.isPending} className="aelin-btn flex items-center gap-1.5">
          <FlaskConical size={14} /> {test.isPending ? '测试中…' : '测试连接'}
        </button>
      </div>

      {currentProvider?.doc && (
        <a href={currentProvider.doc} target="_blank" rel="noreferrer" className="block text-[11px] text-[var(--color-accent)] hover:underline">
          查看 {currentProvider.name} 文档 →
        </a>
      )}
    </div>
  )
}
