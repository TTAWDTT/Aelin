import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as Select from '@radix-ui/react-select'
import * as Slider from '@radix-ui/react-slider'
import * as Switch from '@radix-ui/react-switch'
import { Check, ChevronDown, FlaskConical } from 'lucide-react'
import toast from 'react-hot-toast'
import { agentApi } from '@/shared/api/agent'
import type { AgentConfigUpdate } from '@/shared/api/types'
import { useLocaleStore } from '@/shared/stores/localeStore'

type AgentFormState = {
  providerChoice: string
  customProviderId: string
  base_url: string
  web_search_proxy_url: string
  model: string
  temperature: string
  verify_ssl: boolean
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

function parseTemperature(rawValue: string, isZh: boolean): number {
  const trimmed = rawValue.trim()
  if (!trimmed) {
    throw new Error(
      isZh ? '请填写随机度，范围为 0 到 2' : 'Please enter a temperature value between 0 and 2.'
    )
  }
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) {
    throw new Error(
      isZh ? '随机度必须是 0 到 2 之间的数字' : 'Temperature must be a numeric value between 0 and 2.'
    )
  }
  if (parsed < 0 || parsed > 2) {
    throw new Error(isZh ? '随机度必须在 0 到 2 之间' : 'Temperature must be between 0 and 2.')
  }
  return parsed
}

export function AIConfigTab() {
  const qc = useQueryClient()
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'

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
    const options: Array<{ id: string; label: string }> = [
      { id: RULE_BASED_PROVIDER, label: isZh ? '内置规则' : 'Built-in rules' },
    ]
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
      label: isZh ? '自定义提供商（手动填写）' : 'Custom provider (manual)',
    })

    return options
  }, [providers, isZh])

  const [form, setForm] = useState<AgentFormState>({
    providerChoice: '',
    customProviderId: '',
    base_url: '',
    web_search_proxy_url: '',
    model: '',
    temperature: '0.5',
    verify_ssl: true,
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
      verify_ssl: config.verify_ssl ?? true,
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

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!resolvedProvider) throw new Error(isZh ? '请先选择提供商' : 'Please choose a provider first.')
      if (isCustomProvider && !form.customProviderId.trim()) {
        throw new Error(isZh ? '请填写自定义 Provider ID' : 'Please fill in a custom Provider ID.')
      }
      const baseUrl = form.base_url.trim()
      const modelValue = form.model.trim()

      const body: AgentConfigUpdate = {
        provider: resolvedProvider,
        verify_ssl: form.verify_ssl,
        web_search_proxy_url: form.web_search_proxy_url.trim() || '',
      }
      if (!isRuleBased) {
        body.base_url = baseUrl || undefined
        body.model = modelValue || undefined
        body.temperature = parseTemperature(form.temperature, isZh)
      }
      if (form.api_key.trim()) body.api_key = form.api_key.trim()
      return agentApi.updateConfig(body)
    },
    onSuccess: () => {
      toast.success(isZh ? '已保存' : 'Saved')
      setForm((prev) => ({ ...prev, api_key: '' }))
      qc.invalidateQueries({ queryKey: ['agent-config'] })
    },
    onError: (error: unknown) => {
      toast.error(
        error instanceof Error
          ? error.message
          : isZh
            ? '保存失败'
            : 'Save failed'
      )
    },
  })

  const test = useMutation({
    mutationFn: agentApi.test,
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(`✓ ${res.message}`)
      } else {
        toast.error(`✗ ${res.message}`)
      }
    },
    onError: () => toast.error(isZh ? '测试失败' : 'Test failed'),
  })

  if (isLoading) {
    return (
      <div className="text-sm text-[var(--color-text-muted)]">
        {isZh ? '加载中...' : 'Loading...'}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">
            {isZh ? '服务商' : 'Provider'}
          </span>
          <Select.Root
            value={form.providerChoice || undefined}
            onValueChange={(value) =>
              setForm((prev) => ({
                ...prev,
                providerChoice: value,
                customProviderId: value === CUSTOM_PROVIDER_OPTION ? prev.customProviderId : '',
                model: '',
              }))
            }
          >
            <Select.Trigger className="aelin-select flex items-center justify-between px-3 py-[0.4rem] text-xs">
              <Select.Value placeholder={isZh ? '选择提供商...' : 'Choose a provider...'} />
              <Select.Icon>
                <ChevronDown className="h-3 w-3 text-[var(--color-text-muted)]" />
              </Select.Icon>
            </Select.Trigger>
            <Select.Portal>
              <Select.Content
                className="z-50 overflow-hidden rounded-[10px] bg-[var(--color-panel)] shadow-[0_10px_30px_rgba(0,0,0,0.35)] max-h-[260px]"
                position="popper"
                sideOffset={4}
              >
                <Select.Viewport className="py-1 overflow-y-auto">
                  {providerOptions.map((provider) => (
                    <Select.Item
                      key={provider.id}
                      value={provider.id}
                      className="relative flex cursor-pointer select-none items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] data-[highlighted]:bg-[var(--color-panel-alt)] data-[state=checked]:font-medium"
                    >
                      <Select.ItemIndicator className="absolute left-1 flex items-center justify-center">
                        <Check className="h-3 w-3" />
                      </Select.ItemIndicator>
                      <Select.ItemText>{provider.label}</Select.ItemText>
                    </Select.Item>
                  ))}
                </Select.Viewport>
              </Select.Content>
            </Select.Portal>
          </Select.Root>
        </label>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">
            {isZh ? '随机度（Temperature）' : 'Randomness (Temperature)'}
          </span>
          <div className="flex items-center gap-3">
            <Slider.Root
              className="relative flex h-5 w-full touch-none select-none items-center"
              min={0}
              max={2}
              step={0.1}
              value={[
                (() => {
                  const n = Number(form.temperature)
                  return Number.isFinite(n) ? n : 0.5
                })(),
              ]}
              onValueChange={(values) => {
                const v = values[0] ?? 0.5
                setForm((prev) => ({ ...prev, temperature: v.toFixed(1) }))
              }}
              disabled={isRuleBased}
            >
              <Slider.Track className="relative h-[3px] flex-1 rounded-full bg-[color-mix(in_srgb,var(--color-panel-alt)_75%,transparent_25%)]">
                <Slider.Range className="absolute h-full rounded-full bg-[var(--color-accent)]" />
              </Slider.Track>
              <Slider.Thumb className="block h-3.5 w-3.5 rounded-full bg-[var(--color-text)] shadow-[0_0_0_1px_rgba(255,255,255,0.4)] focus:outline-none" />
            </Slider.Root>
            <span className="w-10 text-right text-xs text-[var(--color-text-muted)]">
              {form.temperature || '0.5'}
            </span>
          </div>
        </label>
      </div>

      {isCustomProvider && (
        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">
            {isZh ? '自定义 Provider ID' : 'Custom Provider ID'}
          </span>
          <input
            value={form.customProviderId}
            onChange={(event) => setForm((prev) => ({ ...prev, customProviderId: event.target.value }))}
            placeholder={isZh ? '例如: doubao' : 'e.g. doubao'}
            className="aelin-input"
          />
        </label>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {isCustomProvider ? (
          <label className="block text-xs space-y-1">
            <span className="text-[var(--color-text-muted)]">
              {isZh ? '模型' : 'Model'}
            </span>
            <input
              value={form.model}
              onChange={(event) => setForm((prev) => ({ ...prev, model: event.target.value }))}
              placeholder={
                isRuleBased
                  ? isZh
                    ? '内置规则模式可留空'
                    : 'Built-in mode can leave blank'
                  : isZh
                    ? '请输入模型 ID'
                    : 'Enter model ID'
              }
              className="aelin-input"
              disabled={isRuleBased}
            />
          </label>
        ) : (
          <label className="block text-xs space-y-1">
            <span className="text-[var(--color-text-muted)]">
              {isZh ? '模型' : 'Model'}
            </span>
            <Select.Root
              value={form.model || undefined}
              onValueChange={(value) => setForm((prev) => ({ ...prev, model: value }))}
              disabled={isRuleBased || !currentProvider}
            >
              <Select.Trigger className="aelin-select flex items-center justify-between px-3 py-[0.4rem] text-xs disabled:opacity-50">
                <Select.Value
                  placeholder={
                    isRuleBased
                      ? isZh
                        ? '内置规则模式无需模型'
                        : 'Built-in mode does not require a model'
                      : isZh
                        ? '选择模型...'
                        : 'Choose a model...'
                  }
                />
                <Select.Icon>
                  <ChevronDown className="h-3 w-3 text-[var(--color-text-muted)]" />
                </Select.Icon>
              </Select.Trigger>
              <Select.Portal>
                <Select.Content
                  className="z-50 overflow-hidden rounded-[10px] bg-[var(--color-panel)] shadow-[0_10px_30px_rgba(0,0,0,0.35)] max-h-[260px]"
                  position="popper"
                  sideOffset={4}
                >
                  <Select.Viewport className="py-1 overflow-y-auto">
                    {(currentProvider?.models ?? []).map((model) => (
                      <Select.Item
                        key={model.id}
                        value={model.id}
                        className="relative flex cursor-pointer select-none items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] data-[highlighted]:bg-[var(--color-panel-alt)] data-[state=checked]:font-medium"
                      >
                        <Select.ItemIndicator className="absolute left-1 flex items-center justify-center">
                          <Check className="h-3 w-3" />
                        </Select.ItemIndicator>
                        <Select.ItemText>{model.name}</Select.ItemText>
                      </Select.Item>
                    ))}
                  </Select.Viewport>
                </Select.Content>
              </Select.Portal>
            </Select.Root>
          </label>
        )}

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">
            {isZh ? '接口地址（Base URL）' : 'Base URL'}
          </span>
          <input
            value={form.base_url}
            onChange={(event) => setForm((prev) => ({ ...prev, base_url: event.target.value }))}
            placeholder={isZh ? '留空则使用默认地址' : 'Leave empty to use the default URL'}
            className="aelin-input"
            disabled={isRuleBased}
          />
        </label>
      </div>

      <div className="flex items-start justify-between gap-4 rounded-[18px] border border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-panel-alt)_28%,var(--color-panel)_72%)] px-4 py-3.5">
        <div className="min-w-0 space-y-1 text-xs">
          <div className="text-[var(--color-text)]">
            {isZh ? '校验 SSL 证书' : 'Verify SSL certificates'}
          </div>
          <div className="text-[var(--color-text-muted)] leading-relaxed">
            {isZh
              ? '如果你的 Base URL 使用自签名证书，请关闭此项。关闭后会跳过 TLS 证书校验。'
              : 'Disable this if your Base URL uses a self-signed certificate. When off, TLS certificate verification is skipped.'}
          </div>
        </div>
        <Switch.Root
          checked={form.verify_ssl}
          onCheckedChange={(checked) => setForm((prev) => ({ ...prev, verify_ssl: checked }))}
          disabled={isRuleBased}
          aria-label={isZh ? '校验 SSL 证书' : 'Verify SSL certificates'}
          className="relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full border border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-panel-alt)_70%,var(--color-panel)_30%)] p-1 transition-[background-color,border-color,opacity] duration-200 data-[state=checked]:border-[color-mix(in_srgb,var(--color-accent)_35%,var(--color-border))] data-[state=checked]:bg-[color-mix(in_srgb,var(--color-accent)_24%,var(--color-panel)_76%)] disabled:cursor-not-allowed disabled:opacity-45"
        >
          <Switch.Thumb className="block h-5 w-5 rounded-full bg-[var(--color-text)] shadow-[0_1px_4px_rgba(0,0,0,0.22)] transition-transform duration-200 data-[state=checked]:translate-x-5" />
        </Switch.Root>
      </div>

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">
          {isZh ? '联网搜索代理（可选）' : 'Web search proxy (optional)'}
        </span>
        <input
          value={form.web_search_proxy_url}
          onChange={(event) => setForm((prev) => ({ ...prev, web_search_proxy_url: event.target.value }))}
          placeholder={
            isZh
              ? '例如: http://127.0.0.1:7890 或 socks5://127.0.0.1:1080'
              : 'e.g. http://127.0.0.1:7890 or socks5://127.0.0.1:1080'
          }
          className="aelin-input"
        />
      </label>

      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">
          API Key
          {config?.has_api_key && (
            <span className="text-[var(--color-green)]">
              {isZh ? '（留空则沿用已保存 Key）' : ' (leave empty to reuse saved key)'}
            </span>
          )}
        </span>
        <input
          type="password"
          value={form.api_key}
          onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))}
          placeholder={
            config?.has_api_key
              ? isZh
                ? '输入新 Key 覆盖'
                : 'Enter a new key to overwrite'
              : isZh
                ? '输入 API Key'
                : 'Enter API Key'
          }
          className="aelin-input"
          disabled={isRuleBased}
        />
      </label>

      <div className="flex gap-3">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="aelin-btn aelin-btn-primary min-w-[96px]"
        >
          {saveMutation.isPending ? (isZh ? '保存中...' : 'Saving...') : isZh ? '保存配置' : 'Save config'}
        </button>
        <button
          onClick={() => test.mutate()}
          disabled={test.isPending}
          className="aelin-btn flex min-w-[96px] items-center gap-1.5"
        >
          <FlaskConical size={14} />
          {test.isPending ? (isZh ? '测试中...' : 'Testing...') : isZh ? '测试连接' : 'Test connection'}
        </button>
      </div>

      {currentProvider?.doc && (
        <a
          href={currentProvider.doc}
          target="_blank"
          rel="noreferrer"
          className="block text-[11px] text-[var(--color-accent)] hover:underline"
        >
          {isZh ? '查看 ' : 'View '}
          {currentProvider.name}
          {isZh ? ' 文档 →' : ' docs →'}
        </a>
      )}
    </div>
  )
}
