import React from "react";

import {
  type AgentConfig,
  getAgentCatalog,
  getAgentConfig,
  type ModelCatalogResponse,
  type ModelProviderInfo,
  testAgent,
  updateAgentConfig,
} from "../../../api";
import { CUSTOM_PROVIDER_OPTION } from "../constants";
import { normalizeProviderId } from "../helpers";

type ToastLevel = "success" | "error" | "warning" | "info";

type UseAelinLlmConfigArgs = {
  showToast: (message: string, level?: ToastLevel) => void;
};

export type UseAelinLlmConfigResult = {
  llmDialogOpen: boolean;
  setLlmDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  llmLoading: boolean;
  llmRefreshing: boolean;
  llmSaving: boolean;
  llmTesting: boolean;
  llmCatalog: ModelCatalogResponse | null;
  llmProvider: string;
  llmProviderSelectValue: string;
  llmCustomProviderId: string;
  llmBaseUrl: string;
  llmModel: string;
  llmTemperature: number;
  llmApiKey: string;
  llmHasApiKey: boolean;
  llmIsCustomProvider: boolean;
  llmSelectedProvider: ModelProviderInfo | null;
  getDefaultLlmBaseUrl: (
    providerId: string,
    catalog?: ModelCatalogResponse | null,
  ) => string;
  openLlmDialog: () => void;
  handleLlmCatalogRefresh: () => Promise<void>;
  handleLlmSave: () => Promise<void>;
  handleLlmTest: () => Promise<void>;
  handleLlmProviderSelect: (value: string) => void;
  handleLlmCustomProviderIdChange: (value: string) => void;
  setLlmModel: React.Dispatch<React.SetStateAction<string>>;
  setLlmBaseUrl: React.Dispatch<React.SetStateAction<string>>;
  setLlmTemperature: React.Dispatch<React.SetStateAction<number>>;
  setLlmApiKey: React.Dispatch<React.SetStateAction<string>>;
};

export function useAelinLlmConfig({
  showToast,
}: UseAelinLlmConfigArgs): UseAelinLlmConfigResult {
  const [llmDialogOpen, setLlmDialogOpen] = React.useState(false);
  const [llmLoading, setLlmLoading] = React.useState(false);
  const [llmRefreshing, setLlmRefreshing] = React.useState(false);
  const [llmSaving, setLlmSaving] = React.useState(false);
  const [llmTesting, setLlmTesting] = React.useState(false);
  const [llmCatalog, setLlmCatalog] =
    React.useState<ModelCatalogResponse | null>(null);
  const [llmProvider, setLlmProvider] = React.useState("rule_based");
  const [llmProviderSelectValue, setLlmProviderSelectValue] =
    React.useState<string>("rule_based");
  const [llmCustomProviderId, setLlmCustomProviderId] = React.useState("");
  const [llmBaseUrl, setLlmBaseUrl] = React.useState(
    "https://api.openai.com/v1",
  );
  const [llmModel, setLlmModel] = React.useState("gpt-4o-mini");
  const [llmTemperature, setLlmTemperature] = React.useState(0.2);
  const [llmApiKey, setLlmApiKey] = React.useState("");
  const [llmHasApiKey, setLlmHasApiKey] = React.useState(false);

  const llmIsCustomProvider = llmProviderSelectValue === CUSTOM_PROVIDER_OPTION;
  const llmSelectedProvider = React.useMemo<ModelProviderInfo | null>(() => {
    const providerId = normalizeProviderId(llmProvider);
    return (
      llmCatalog?.providers.find((provider) => provider.id === providerId) ??
      null
    );
  }, [llmCatalog, llmProvider]);

  const getDefaultLlmBaseUrl = React.useCallback(
    (providerId: string, catalog: ModelCatalogResponse | null = llmCatalog) => {
      const normalizedProviderId =
        normalizeProviderId(providerId) || "rule_based";
      if (normalizedProviderId === "rule_based")
        return "https://api.openai.com/v1";
      const matched = (catalog?.providers ?? []).find(
        (provider) => provider.id === normalizedProviderId,
      );
      return (matched?.api || "").trim() || "https://api.openai.com/v1";
    },
    [llmCatalog],
  );

  const hydrateLlmDialogState = React.useCallback(
    (config: AgentConfig, catalog: ModelCatalogResponse | null) => {
      const provider =
        normalizeProviderId(config.provider || "rule_based") || "rule_based";
      const catalogIds = new Set(
        (catalog?.providers ?? []).map((item) => item.id),
      );
      setLlmProvider(provider);
      if (provider === "rule_based") {
        setLlmProviderSelectValue("rule_based");
        setLlmCustomProviderId("");
      } else if (catalogIds.has(provider)) {
        setLlmProviderSelectValue(provider);
      } else {
        setLlmProviderSelectValue(CUSTOM_PROVIDER_OPTION);
        setLlmCustomProviderId(provider);
      }
      setLlmBaseUrl(config.base_url || getDefaultLlmBaseUrl(provider, catalog));
      setLlmModel(config.model || "gpt-4o-mini");
      setLlmTemperature(
        Number.isFinite(config.temperature) ? config.temperature : 0.2,
      );
      setLlmHasApiKey(Boolean(config.has_api_key));
      setLlmApiKey("");
    },
    [getDefaultLlmBaseUrl],
  );

  const loadLlmDialogData = React.useCallback(async () => {
    setLlmLoading(true);
    try {
      const [config, catalog] = await Promise.all([
        getAgentConfig(),
        getAgentCatalog(false),
      ]);
      setLlmCatalog(catalog);
      hydrateLlmDialogState(config, catalog);
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : "加载模型配置失败",
        "error",
      );
    } finally {
      setLlmLoading(false);
    }
  }, [hydrateLlmDialogState, showToast]);

  const openLlmDialog = React.useCallback(() => {
    setLlmDialogOpen(true);
    void loadLlmDialogData();
  }, [loadLlmDialogData]);

  const handleLlmCatalogRefresh = React.useCallback(async () => {
    setLlmRefreshing(true);
    try {
      const fresh = await getAgentCatalog(true);
      setLlmCatalog(fresh);
      showToast(
        `模型目录已刷新（${fresh.providers.length} 个服务商）`,
        "success",
      );
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : "刷新模型目录失败",
        "error",
      );
    } finally {
      setLlmRefreshing(false);
    }
  }, [showToast]);

  const handleLlmSave = React.useCallback(async () => {
    const provider = normalizeProviderId(llmProvider);
    if (!provider) {
      showToast("请填写服务商 ID", "error");
      return;
    }
    if (provider !== "rule_based") {
      if (!llmBaseUrl.trim()) {
        showToast("请填写 Base URL", "error");
        return;
      }
      if (!llmModel.trim()) {
        showToast("请填写模型 ID", "error");
        return;
      }
    }

    setLlmSaving(true);
    try {
      const payload: {
        provider: string;
        base_url?: string;
        model?: string;
        temperature: number;
        api_key?: string;
      } = {
        provider,
        temperature: Number.isFinite(llmTemperature) ? llmTemperature : 0.2,
      };
      if (provider !== "rule_based") {
        payload.base_url = llmBaseUrl.trim();
        payload.model = llmModel.trim();
      }
      if (llmApiKey.trim()) {
        payload.api_key = llmApiKey.trim();
      }
      const updated = await updateAgentConfig(payload);
      hydrateLlmDialogState(updated, llmCatalog);
      showToast("Aelin 模型配置已保存", "success");
    } catch (error) {
      showToast(
        error instanceof Error ? error.message : "保存模型配置失败",
        "error",
      );
    } finally {
      setLlmSaving(false);
    }
  }, [
    hydrateLlmDialogState,
    llmApiKey,
    llmBaseUrl,
    llmCatalog,
    llmModel,
    llmProvider,
    llmTemperature,
    showToast,
  ]);

  const handleLlmTest = React.useCallback(async () => {
    setLlmTesting(true);
    try {
      const ret = await testAgent();
      showToast(`测试通过：${ret.message || "OK"}`, "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "测试失败", "error");
    } finally {
      setLlmTesting(false);
    }
  }, [showToast]);

  const handleLlmProviderSelect = React.useCallback(
    (value: string) => {
      if (value === CUSTOM_PROVIDER_OPTION) {
        setLlmProviderSelectValue(CUSTOM_PROVIDER_OPTION);
        setLlmProvider(normalizeProviderId(llmCustomProviderId));
        if (!llmBaseUrl.trim()) {
          setLlmBaseUrl("https://api.openai.com/v1");
        }
        return;
      }
      const normalized = normalizeProviderId(value) || "rule_based";
      setLlmProviderSelectValue(normalized);
      setLlmProvider(normalized);
      if (normalized === "rule_based") {
        setLlmCustomProviderId("");
      }
      setLlmBaseUrl(getDefaultLlmBaseUrl(normalized));
    },
    [getDefaultLlmBaseUrl, llmBaseUrl, llmCustomProviderId],
  );

  const handleLlmCustomProviderIdChange = React.useCallback((value: string) => {
    setLlmCustomProviderId(value);
    setLlmProvider(normalizeProviderId(value));
  }, []);

  React.useEffect(() => {
    if (
      llmProvider === "rule_based" ||
      llmIsCustomProvider ||
      !llmSelectedProvider
    )
      return;
    if (
      llmSelectedProvider.models.length > 0 &&
      !llmSelectedProvider.models.some((model) => model.id === llmModel)
    ) {
      setLlmModel(llmSelectedProvider.models[0].id);
    }
  }, [llmIsCustomProvider, llmModel, llmProvider, llmSelectedProvider]);

  return {
    llmDialogOpen,
    setLlmDialogOpen,
    llmLoading,
    llmRefreshing,
    llmSaving,
    llmTesting,
    llmCatalog,
    llmProvider,
    llmProviderSelectValue,
    llmCustomProviderId,
    llmBaseUrl,
    llmModel,
    llmTemperature,
    llmApiKey,
    llmHasApiKey,
    llmIsCustomProvider,
    llmSelectedProvider,
    getDefaultLlmBaseUrl,
    openLlmDialog,
    handleLlmCatalogRefresh,
    handleLlmSave,
    handleLlmTest,
    handleLlmProviderSelect,
    handleLlmCustomProviderIdChange,
    setLlmModel,
    setLlmBaseUrl,
    setLlmTemperature,
    setLlmApiKey,
  };
}
