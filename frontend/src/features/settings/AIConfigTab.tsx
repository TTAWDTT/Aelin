import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical } from 'lucide-react'
import toast from 'react-hot-toast'
import { agentApi } from '@/shared/api/agent'

type AgentFormState = {
  providerChoice: string
  customProviderId: string
  base_url: string
  web_search_proxy_url: string
  model: string
  temperature: string
  api_key: string
}

const RULE_BASED_PROVIDER = 'rule_based'
const CUSTOM_PROVIDER_OPTION = '__custom_provider__'

function normalizeProvider(value: string | undefined | null): string {
  const key = String(value || '').trim().toLowerCase()
  if (!key) return ''
  if (key === 'rule-based' || key === 'builtin' || key === 'local') {
    return RULE_BASED_PROVIDER
  }
  return key
}

export function AIConfigTab() {
  const qc = useQueryClient()

  const { data: config, isLoading } = useQuery({
    queryKey: ['agent-config'],
    queryFn: agentApi.config,
  })

  const { data: catalog } = useQuery({
    queryKey: ['agent-catalog'],
    queryFn: agentApi.catalog,
  })

  const providers = catalog?.providers ?? []

  const providerOptions = useMemo(() => {
    const options: Array<{ id: string; label: string }> = [{ id: RULE_BASED_PROVIDER, label: '内置规则' }]
    const seen = new Set<string>([RULE_BASED_PROVIDER])

    for (const provider of providers) {
      const id = normalizeProvider(provider.id)
      if (!id || seen.has(id)) continue
      seen.add(id)
      options.push({
        id,
        label: `${provider.name} (${provider.model_count} 模型)`,
      })
    }

    options.push({
      id: CUSTOM_PROVIDER_OPTION,
      label: '自定义提供商（手动填写）',
    })

    return options
  }, [providers])

  const [form, setForm] = useState<AgentFormState>({
    providerChoice: '',
    customProviderId: '',
    base_url: '',
    web_search_proxy_url: '',
    model: '',
    temperature: '0.5',
    api_key: '',
  })

  useEffect(() => {
    if (!config) return

    const normalizedConfigProvider = normalizeProvider(config.provider)
    const providerExistsInCatalog = providers.some(
      (provider) => normalizeProvider(provider.id) === normalizedConfigProvider
    )
    const shouldUseCustom =
      !!normalizedConfigProvider &&
      normalizedConfigProvider !== RULE_BASED_PROVIDER &&
      !providerExistsInCatalog

    setForm({
      providerChoice: shouldUseCustom ? CUSTOM_PROVIDER_OPTION : normalizedConfigProvider,
      customProviderId: shouldUseCustom ? normalizedConfigProvider : '',
      base_url: config.base_url || '',
      web_search_proxy_url: config.web_search_proxy_url || '',
      model: config.model || '',
      temperature: String(config.temperature ?? 0.5),
      api_key: '',
    })
  }, [config, providers])

  const resolvedProvider = useMemo(() => {
    if (form.providerChoice === CUSTOM_PROVIDER_OPTION) {
      return normalizeProvider(form.customProviderId)
    }
    return normalizeProvider(form.providerChoice)
  }, [form.providerChoice, form.customProviderId])

  const isCustomProvider = form.providerChoice === CUSTOM_PROVIDER_OPTION
  const isRuleBased = resolvedProvider === RULE_BASED_PROVIDER
  const currentProvider = providers.find(
    (provider) => normalizeProvider(provider.id) === resolvedProvider
  )

  const save = useMutation({
    mutationFn: () => {
      if (!resolvedProvider) throw new Error('请先选择提供商')
      if (isCustomProvider && !form.customProviderId.trim()) {
        throw new Error('请填写自定义 Provider ID')
      }

      const body: Record<string, unknown> = {
        provider: resolvedProvider,
        base_url: form.base_url || undefined,
        web_search_proxy_url: form.web_search_proxy_url.trim() || '',
        model: form.model || undefined,
        temperature: Number(form.temperature),
      }
      if (form.api_key.trim()) body.api_key = form.api_key.trim()
      return agentApi.updateConfig(body as any)
    },
    onSuccess: () => {
      toast.success('已保存')
      setForm((prev) => ({ ...prev, api_key: '' }))
      qc.invalidateQueries({ queryKey: ['agent-config'] })
    },
    onError: (error: unknown) => {
      toast.error(error instanceof Error ? error.message : '保存失败')
    },
  })

  const test = useMutation({
    mutationFn: agentApi.test,
    onSuccess: (res) => {
      if (res.ok) toast.success(`✓ ${res.message}`)
      else toast.error(`✗ ${res.message}`)
    },
    onError: () => toast.error('测试失败'),
  })

  if (isLoading) {
    return <div className="text-sm text-[var(--color-text-muted)]">加载中...</div>
  }

  return (
    <div className="max-w-md space-y-5">
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">服务商</span>
        <select
          value={form.providerChoice}
          onChange={(event) =>
            setForm((prev) => ({
              ...prev,
              providerChoice: event.target.value,
              customProviderId:
                event.target.value === CUSTOM_PROVIDER_OPTION ? prev.customProviderId : '',
              model: '',
            }))
          }
          className="aelin-select"
        >
          <option value="">选择提供商...</option>
          {providerOptions.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.label}
            </option>
          ))}
        </select>
      </label>

      {isCustomProvider && (
        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">自定义 Provider ID</span>
          <input
            value={form.customProviderId}
            onChange={(event) => setForm((prev) => ({ ...prev, customProviderId: event.target.value }))}
            placeholder="例如: doubao"
            className="aelin-input"
          />
        </label>
      )}

      {isCustomProvider ? (
        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">模型</span>
          <input
            value={form.model}
            onChange={(event) => setForm((prev) => ({ ...prev, model: event.target.value }))}
            placeholder={isRuleBased ? '内置规则模式可留空' : '请输入模型 ID'}
            className="aelin-input"
            disabled={isRuleBased}
          />
        </label>
      ) : (
        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">模型</span>
          <select
            value={form.model}
            onChange={(event) => setForm((prev) => ({ ...prev, model: event.target.value }))}
            className="aelin-select"
            disabled={isRuleBased || !currentProvider}
          >
            <option value="">{isRuleBased ? '内置规则模式无需模型' : '选择模型...'}</option>
            {(currentProvider?.models ?? []).map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">接口地址（Base URL）</span>
        <input
          value={form.base_url}
          onChange={(event) => setForm((prev) => ({ ...prev, base_url: event.target.value }))}
          placeholder="留空则使用默认地址"
          className="aelin-input"
          disabled={isRuleBased}
        />
      </label>

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">联网搜索代理（可选）</span>
        <input
          value={form.web_search_proxy_url}
          onChange={(event) => setForm((prev) => ({ ...prev, web_search_proxy_url: event.target.value }))}
          placeholder="例如: http://127.0.0.1:7890 或 socks5://127.0.0.1:1080"
          className="aelin-input"
        />
      </label>

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">随机度（Temperature）</span>
        <input
          type="number"
          min="0"
          max="2"
          step="0.1"
          value={form.temperature}
          onChange={(event) => setForm((prev) => ({ ...prev, temperature: event.target.value }))}
          className="aelin-input"
          disabled={isRuleBased}
        />
      </label>

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">
          API Key
          {config?.has_api_key && <span className="text-[var(--color-green)]">（留空则沿用已保存 Key）</span>}
        </span>
        <input
          type="password"
          value={form.api_key}
          onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))}
          placeholder={config?.has_api_key ? '输入新 Key 覆盖' : '输入 API Key'}
          className="aelin-input"
          disabled={isRuleBased}
        />
      </label>

      <div className="flex gap-3">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="aelin-btn aelin-btn-primary"
        >
          {save.isPending ? '保存中...' : '保存配置'}
        </button>
        <button
          onClick={() => test.mutate()}
          disabled={test.isPending}
          className="aelin-btn flex items-center gap-1.5"
        >
          <FlaskConical size={14} />
          {test.isPending ? '测试中...' : '测试连接'}
        </button>
      </div>

      {currentProvider?.doc && (
        <a
          href={currentProvider.doc}
          target="_blank"
          rel="noreferrer"
          className="block text-[11px] text-[var(--color-accent)] hover:underline"
        >
          查看 {currentProvider.name} 文档 →
        </a>
      )}
    </div>
  )
}
