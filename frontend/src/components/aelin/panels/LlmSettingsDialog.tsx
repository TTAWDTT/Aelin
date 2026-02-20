import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import RefreshIcon from "@mui/icons-material/Refresh";
import { alpha, useTheme } from "@mui/material/styles";

import type { ModelCatalogResponse, ModelProviderInfo } from "../../../api";

type AelinLlmSettingsDialogProps = {
  open: boolean;
  loading: boolean;
  refreshing: boolean;
  saving: boolean;
  testing: boolean;
  catalog: ModelCatalogResponse | null;
  provider: string;
  providerSelectValue: string;
  customProviderId: string;
  baseUrl: string;
  model: string;
  temperature: number;
  apiKey: string;
  hasApiKey: boolean;
  isCustomProvider: boolean;
  selectedProvider: ModelProviderInfo | null;
  customProviderOption: string;
  providerDisplay: string;
  onClose: () => void;
  onRefreshCatalog: () => void;
  onProviderSelect: (value: string) => void;
  onCustomProviderIdChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onBaseUrlChange: (value: string) => void;
  onTemperatureChange: (value: number) => void;
  onApiKeyChange: (value: string) => void;
  onOpenSettings: () => void;
  onTest: () => void;
  onSave: () => void;
};

export function AelinLlmSettingsDialog(props: AelinLlmSettingsDialogProps) {
  const {
    open,
    loading,
    refreshing,
    saving,
    testing,
    catalog,
    provider,
    providerSelectValue,
    customProviderId,
    baseUrl,
    model,
    temperature,
    apiKey,
    hasApiKey,
    isCustomProvider,
    selectedProvider,
    customProviderOption,
    providerDisplay,
    onClose,
    onRefreshCatalog,
    onProviderSelect,
    onCustomProviderIdChange,
    onModelChange,
    onBaseUrlChange,
    onTemperatureChange,
    onApiKeyChange,
    onOpenSettings,
    onTest,
    onSave,
  } = props;

  const theme = useTheme();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      PaperProps={{
        sx: {
          borderRadius: 2,
          overflow: "hidden",
          bgcolor: alpha(theme.palette.background.paper, 0.98),
          backdropFilter: "blur(10px)",
        },
      }}
    >
      <Box sx={{ px: 1.2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
            Aelin 模型设置
          </Typography>
          <Stack direction="row" spacing={0.4}>
            <Tooltip title="刷新模型目录">
              <span>
                <IconButton size="small" onClick={onRefreshCatalog} disabled={refreshing || loading}>
                  {refreshing ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>
            <IconButton size="small" onClick={onClose}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
      </Box>

      <Box sx={{ px: 1.2, py: 1.1 }}>
        {loading ? (
          <Stack direction="row" spacing={0.8} alignItems="center" sx={{ py: 2.6 }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              正在加载模型配置...
            </Typography>
          </Stack>
        ) : (
          <Stack spacing={1.1}>
            <TextField
              select
              fullWidth
              size="small"
              label="服务商"
              value={providerSelectValue}
              onChange={(event) => onProviderSelect(String(event.target.value || ""))}
              SelectProps={{ native: true }}
            >
              <option value="rule_based">内置规则（免费）</option>
              {(catalog?.providers ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.id})
                </option>
              ))}
              <option value={customProviderOption}>自定义提供商（手动填写）</option>
            </TextField>

            {isCustomProvider ? (
              <TextField
                fullWidth
                size="small"
                label="自定义 Provider ID"
                value={customProviderId}
                onChange={(event) => onCustomProviderIdChange(String(event.target.value || ""))}
                placeholder="例如：deepseek / groq / my-private-llm"
              />
            ) : null}

            {provider !== "rule_based" ? (
              <>
                {selectedProvider?.models?.length && !isCustomProvider ? (
                  <TextField
                    select
                    fullWidth
                    size="small"
                    label="模型"
                    value={model}
                    onChange={(event) => onModelChange(String(event.target.value || ""))}
                    SelectProps={{ native: true }}
                  >
                    {selectedProvider.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.id})
                      </option>
                    ))}
                  </TextField>
                ) : (
                  <TextField
                    fullWidth
                    size="small"
                    label="模型"
                    value={model}
                    onChange={(event) => onModelChange(String(event.target.value || ""))}
                    placeholder="输入模型 ID"
                  />
                )}

                <TextField
                  fullWidth
                  size="small"
                  label="接口地址（Base URL）"
                  value={baseUrl}
                  onChange={(event) => onBaseUrlChange(String(event.target.value || ""))}
                  placeholder={selectedProvider?.api || "https://api.openai.com/v1"}
                />
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="随机度（Temperature）"
                  value={temperature}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    onTemperatureChange(Number.isFinite(value) ? value : 0.2);
                  }}
                  inputProps={{ min: 0, max: 2, step: 0.1 }}
                />
                <TextField
                  fullWidth
                  size="small"
                  type="password"
                  label="API Key（留空则沿用已保存 Key）"
                  value={apiKey}
                  onChange={(event) => onApiKeyChange(String(event.target.value || ""))}
                  placeholder={hasApiKey ? "已保存（不显示）" : "sk-..."}
                />
                <Alert severity="info" sx={{ borderRadius: 1.2, py: 0.35 }}>
                  当前使用 OpenAI-Compatible 接口。请确保 Base URL 与模型 ID 对应同一服务商。
                </Alert>
              </>
            ) : (
              <Alert severity="info" sx={{ borderRadius: 1.2, py: 0.35 }}>
                已使用内置规则模式，可直接聊天；若需高质量模型回答，请切换到任意 API 提供商。
              </Alert>
            )}

            <Typography variant="caption" color="text.secondary">
              当前：{providerDisplay || "rule_based"} · Key：{hasApiKey ? "已配置" : "未配置"}
            </Typography>
          </Stack>
        )}
      </Box>

      <Box sx={{ px: 1.2, pb: 1.1, pt: 0.2, display: "flex", gap: 0.8, justifyContent: "flex-end", flexWrap: "wrap" }}>
        <Button size="small" variant="text" onClick={onOpenSettings}>
          完整设置
        </Button>
        <Button size="small" variant="outlined" onClick={onTest} disabled={loading || saving || testing}>
          {testing ? "测试中..." : "测试连接"}
        </Button>
        <Button size="small" variant="contained" onClick={onSave} disabled={loading || saving}>
          {saving ? "保存中..." : "保存配置"}
        </Button>
      </Box>
    </Dialog>
  );
}
