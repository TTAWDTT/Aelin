import React from "react";
import useSWR from "swr";
import { getAgentCatalog, getAgentConfig, testAgent, updateAgentConfig } from "../api/endpoints";
import type { AgentConfig, ModelCatalogProvider } from "../api/types";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { useToast } from "../app/providers/ToastProvider";

const CUSTOM_PROVIDER = "__custom__";

function normalizeProviderId(value: string) {
  return String(value || "").trim().toLowerCase();
}

export function SettingsPage() {
  const { showToast } = useToast();
  const { data: config, mutate: mutateConfig, isLoading: configLoading } = useSWR<AgentConfig>(
    "agent-config",
    () => getAgentConfig(),
  );
  const { data: catalog, mutate: mutateCatalog } = useSWR("agent-catalog", () => getAgentCatalog(false));

  const [providerSelect, setProviderSelect] = React.useState("rule_based");
  const [customProvider, setCustomProvider] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("https://api.openai.com/v1");
  const [model, setModel] = React.useState("gpt-4o-mini");
  const [temperature, setTemperature] = React.useState(0.2);
  const [apiKey, setApiKey] = React.useState("");
  const [busySave, setBusySave] = React.useState(false);
  const [busyTest, setBusyTest] = React.useState(false);

  const providers = (catalog?.providers ?? []) as ModelCatalogProvider[];
  const providerIds = new Set(providers.map((p) => normalizeProviderId(p.id)));

  const selectedProviderId =
    providerSelect === CUSTOM_PROVIDER
      ? normalizeProviderId(customProvider)
      : normalizeProviderId(providerSelect);
  const selectedProvider = providers.find((p) => normalizeProviderId(p.id) === selectedProviderId) ?? null;

  React.useEffect(() => {
    if (!config) return;
    const p = normalizeProviderId(config.provider || "rule_based") || "rule_based";
    if (p === "rule_based") {
      setProviderSelect("rule_based");
      setCustomProvider("");
    } else if (providerIds.has(p)) {
      setProviderSelect(p);
      setCustomProvider("");
    } else {
      setProviderSelect(CUSTOM_PROVIDER);
      setCustomProvider(p);
    }
    setBaseUrl(config.base_url || "https://api.openai.com/v1");
    setModel(config.model || "gpt-4o-mini");
    setTemperature(Number.isFinite(config.temperature) ? config.temperature : 0.2);
  }, [config, providerIds]);

  const refreshCatalog = async () => {
    try {
      const fresh = await getAgentCatalog(true);
      mutateCatalog(fresh, { revalidate: false });
      showToast(`已刷新模型目录（${fresh.providers.length} 个服务商）`, "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "刷新失败", "error");
    }
  };

  const save = async () => {
    const provider = selectedProviderId || "rule_based";
    setBusySave(true);
    try {
      const payload: any = { provider, temperature: Number(temperature) };
      if (provider !== "rule_based") {
        payload.base_url = String(baseUrl || "").trim();
        payload.model = String(model || "").trim();
      }
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const updated = await updateAgentConfig(payload);
      mutateConfig(updated, { revalidate: false });
      setApiKey("");
      showToast("已保存 Agent 配置", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setBusySave(false);
    }
  };

  const test = async () => {
    setBusyTest(true);
    try {
      const res = await testAgent();
      showToast(`测试通过：${res.message || "OK"}`, "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "测试失败", "error");
    } finally {
      setBusyTest(false);
    }
  };

  const providerOptions = [
    { id: "rule_based", label: "rule_based（内置）" },
    ...providers.map((p) => ({ id: normalizeProviderId(p.id), label: p.label || p.id })),
    { id: CUSTOM_PROVIDER, label: "自定义…" },
  ];

  const models = selectedProvider?.models ?? [];

  return (
    <div className="rounded-[var(--radius)] border border-mist/70 bg-paper/70 shadow-paper overflow-hidden">
      <header className="border-b border-mist/60 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-heading text-sm">Settings</div>
            <div className="text-xs text-stone">先把 Agent 配好，Chat 的能力才会完全释放。</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => void refreshCatalog()}>
              刷新目录
            </Button>
            <Button variant="subtle" onClick={() => void mutateConfig()}>
              刷新配置
            </Button>
          </div>
        </div>
      </header>

      <div className="p-4">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-mist/70 bg-paper/70 p-4">
            <div className="font-heading text-sm">Agent / LLM</div>
            <div className="mt-1 text-xs text-stone">OpenAI-Compatible 请求格式。</div>

            <div className="mt-4 space-y-3">
              <div>
                <div className="text-xs font-heading text-stone tracking-wide">Provider</div>
                <div className="mt-2">
                  <Select value={providerSelect} onChange={(e) => setProviderSelect(e.target.value)}>
                    {providerOptions.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </Select>
                </div>
                {providerSelect === CUSTOM_PROVIDER ? (
                  <div className="mt-2">
                    <Input
                      value={customProvider}
                      onChange={(e) => setCustomProvider(e.target.value)}
                      placeholder="输入 provider id（例如 deepseek）"
                    />
                  </div>
                ) : null}
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <div className="text-xs font-heading text-stone tracking-wide">Base URL</div>
                  <div className="mt-2">
                    <Input
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      disabled={selectedProviderId === "rule_based"}
                    />
                  </div>
                </div>
                <div>
                  <div className="text-xs font-heading text-stone tracking-wide">Temperature</div>
                  <div className="mt-2">
                    <Input
                      value={String(temperature)}
                      onChange={(e) => setTemperature(Number(e.target.value))}
                      inputMode="decimal"
                    />
                  </div>
                </div>
              </div>

              <div>
                <div className="text-xs font-heading text-stone tracking-wide">Model</div>
                <div className="mt-2">
                  {selectedProviderId !== "rule_based" && models.length ? (
                    <Select value={model} onChange={(e) => setModel(e.target.value)}>
                      {models.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label || m.id}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <Input
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={selectedProviderId === "rule_based"}
                    />
                  )}
                </div>
              </div>

              <div>
                <div className="text-xs font-heading text-stone tracking-wide">API Key</div>
                <div className="mt-2">
                  <Input value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="只在本次保存时提交" />
                </div>
                <div className="mt-2 text-[11px] text-stone">
                  当前配置：{configLoading ? "读取中…" : config?.has_api_key ? "已保存 key" : "未保存 key"}
                </div>
              </div>

              <div className="flex flex-wrap gap-2 pt-2">
                <Button tone="orange" disabled={busySave || configLoading} onClick={() => void save()}>
                  {busySave ? "保存中…" : "保存"}
                </Button>
                <Button variant="subtle" disabled={busyTest} onClick={() => void test()}>
                  {busyTest ? "测试中…" : "测试连接"}
                </Button>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-mist/70 bg-paper/60 p-4">
            <div className="font-heading text-sm">Accounts（下一步）</div>
            <div className="mt-2 text-sm text-stone leading-relaxed">
              这一版先把 Chat / Signals / Tracking 的主链路跑通。下一步会在这里做数据源连接健康面板（OAuth/IMAP/RSS/平台抓取/转发地址），并提供“一键同步”与错误自愈提示。
            </div>
            <div className="mt-4 rounded-xl border border-mist/70 bg-paper/70 p-3 text-xs text-stone">
              Tip：如果你已经在后端配置了 OAuth，Chat 更容易产生可引用证据；否则会更多依赖 web search 与 rule_based fallback。
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

