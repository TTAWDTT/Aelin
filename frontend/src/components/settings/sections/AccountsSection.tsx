import React, { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import GitHubIcon from "@mui/icons-material/GitHub";
import EmailIcon from "@mui/icons-material/Email";
import SyncIcon from "@mui/icons-material/Sync";
import RssFeedIcon from "@mui/icons-material/RssFeed";
import AlternateEmailIcon from "@mui/icons-material/AlternateEmail";
import PersonIcon from "@mui/icons-material/Person";
import useSWR from "swr";

import {
  ConnectedAccount,
  ForwardAccountInfo,
  OAuthProviderConfig,
  XApiConfig,
  createAccount,
  deleteAccount,
  deleteXAuthCookies,
  getForwardAccountInfo,
  getOAuthProviderConfig,
  getXApiConfig,
  listAccounts,
  startAccountOAuth,
  syncAccount,
  updateOAuthProviderConfig,
  updateXApiConfig,
  updateXAuthCookies,
} from "../../../api";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirmDialog } from "../../../hooks/useConfirmDialog";
import {
  extractRedirectOriginFromAuthUrl,
  openOAuthPopup,
  waitForOAuthPopupMessage,
} from "../../../utils/oauthPopup";
import { ConnectedAccountsList } from "./accounts/ConnectedAccountsList";
import { AccountProviderFields } from "./accounts/AccountProviderFields";
import type {
  GithubConnectMode,
  OAuthSourceProvider,
  SourceProvider,
} from "./accounts/types";

const OAUTH_PROVIDER_LABEL: Record<OAuthSourceProvider, string> = {
  gmail: "Gmail",
  outlook: "Outlook",
  github: "GitHub",
};

function accountIcon(provider: string) {
  const normalized = provider.toLowerCase();
  if (normalized === "github") return <GitHubIcon />;
  if (normalized === "rss") return <RssFeedIcon />;
  if (normalized === "bilibili") return <PersonIcon />;
  if (normalized === "x") return <AlternateEmailIcon />;
  if (normalized === "douyin") return <PersonIcon />;
  if (normalized === "xiaohongshu") return <PersonIcon />;
  if (normalized === "weibo") return <PersonIcon />;
  if (normalized === "forward") return <SyncIcon />;
  return <EmailIcon />;
}

export function AccountsSection() {
  const { showToast } = useToast();
  const { confirm, ConfirmDialog } = useConfirmDialog();
  const { data: accounts, mutate: mutateAccounts } =
    useSWR<ConnectedAccount[]>("/api/v1/accounts");

  const [syncing, setSyncing] = useState<number | null>(null);
  // Account State
  const [newProvider, setNewProvider] = useState<SourceProvider>("gmail");
  const [imapPreset, setImapPreset] = useState<
    "gmail" | "outlook" | "icloud" | "qq" | "163" | "custom"
  >("gmail");
  const [showImapAdvanced, setShowImapAdvanced] = useState(false);
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState("993");
  const [imapUseSsl, setImapUseSsl] = useState(true);
  const [imapUsername, setImapUsername] = useState("");
  const [imapPassword, setImapPassword] = useState("");
  const [imapMailbox, setImapMailbox] = useState("INBOX");
  const [rssFeedUrl, setRssFeedUrl] = useState("");
  const [rssHomepageUrl, setRssHomepageUrl] = useState("");
  const [rssDisplayName, setRssDisplayName] = useState("");
  const [bilibiliUid, setBilibiliUid] = useState("");
  const [xUsername, setXUsername] = useState("");
  const [xBearerToken, setXBearerToken] = useState("");
  const [xAuthToken, setXAuthToken] = useState("");
  const [xCt0, setXCt0] = useState("");
  const [savingXConfig, setSavingXConfig] = useState(false);
  const [savingXCookies, setSavingXCookies] = useState(false);
  const { data: xApiConfig, mutate: mutateXApiConfig } = useSWR<XApiConfig>(
    newProvider === "x" ? "x-api-config" : null,
    () => getXApiConfig(),
  );
  const [douyinSecUid, setDouyinSecUid] = useState("");
  const [xiaohongshuUserId, setXiaohongshuUserId] = useState("");
  const [weiboUid, setWeiboUid] = useState("");
  const [forwardSourceEmail, setForwardSourceEmail] = useState("");
  const [githubConnectMode, setGithubConnectMode] =
    useState<GithubConnectMode>("oauth");
  const [githubIdentifier, setGithubIdentifier] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [addingAccount, setAddingAccount] = useState(false);
  const [oauthConnecting, setOauthConnecting] =
    useState<null | OAuthSourceProvider>(null);
  const [oauthClientIdInput, setOauthClientIdInput] = useState("");
  const [oauthClientSecretInput, setOauthClientSecretInput] = useState("");
  const [savingOAuthConfig, setSavingOAuthConfig] = useState(false);
  const [latestForwardInfo, setLatestForwardInfo] =
    useState<ForwardAccountInfo | null>(null);
  const isOAuthProvider =
    newProvider === "gmail" ||
    newProvider === "outlook" ||
    (newProvider === "github" && githubConnectMode === "oauth");
  const { data: oauthProviderConfig, mutate: mutateOAuthProviderConfig } =
    useSWR<OAuthProviderConfig>(
      isOAuthProvider ? `oauth-config-${newProvider}` : null,
      () => getOAuthProviderConfig(newProvider as OAuthSourceProvider),
    );

  useEffect(() => {
    if (newProvider !== "imap") return;
    const presets = {
      gmail: { host: "imap.gmail.com", port: 993, ssl: true },
      outlook: { host: "outlook.office365.com", port: 993, ssl: true },
      icloud: { host: "imap.mail.me.com", port: 993, ssl: true },
      qq: { host: "imap.qq.com", port: 993, ssl: true },
      "163": { host: "imap.163.com", port: 993, ssl: true },
      custom: { host: "", port: 993, ssl: true },
    } as const;

    if (imapPreset === "custom") {
      setShowImapAdvanced(true);
      setImapHost("");
      setImapPort("993");
      setImapUseSsl(true);
      return;
    }

    const preset = presets[imapPreset];
    setImapHost(preset.host);
    setImapPort(String(preset.port));
    setImapUseSsl(preset.ssl);
  }, [newProvider, imapPreset]);

  useEffect(() => {
    if (newProvider !== "forward") {
      setLatestForwardInfo(null);
    }
  }, [newProvider]);

  useEffect(() => {
    if (!isOAuthProvider) {
      setOauthClientIdInput("");
      setOauthClientSecretInput("");
      return;
    }
    setOauthClientSecretInput("");
  }, [isOAuthProvider, newProvider]);

  const postConnectSync = async (accountId: number, connectedLabel: string) => {
    try {
      const res = await syncAccount(accountId);
      showToast(`${connectedLabel}已连接并同步：+${res.inserted}`, "success");
    } catch (e) {
      showToast(
        e instanceof Error
          ? `${connectedLabel}已连接，首次同步失败（${e.message}）。可稍后手动点“同步”重试。`
          : `${connectedLabel}已连接，首次同步失败。可稍后手动点“同步”重试。`,
        "warning",
      );
    }
  };

  const connectAndSync = async (
    payload: Parameters<typeof createAccount>[0],
    connectedLabel: string,
  ) => {
    const account = await createAccount(payload);
    await postConnectSync(account.id, connectedLabel);
    return account;
  };

  const findNewOAuthAccount = async (
    provider: OAuthSourceProvider,
    knownAccountIds: Set<number>,
  ): Promise<ConnectedAccount | null> => {
    try {
      const latest = await listAccounts();
      mutateAccounts(latest, { revalidate: false });
      return (
        latest
          .filter(
            (item) =>
              item.provider.toLowerCase() === provider &&
              !knownAccountIds.has(item.id),
          )
          .sort((a, b) => b.id - a.id)[0] ?? null
      );
    } catch {
      return null;
    }
  };

  const showOAuthSetupGuide = (
    popup: Window,
    provider: OAuthSourceProvider,
    message: string,
  ): boolean => {
    if (!message.includes("未配置 client_id/client_secret")) return false;
    const envHint =
      provider === "gmail"
        ? "MERCURYDESK_GMAIL_CLIENT_ID / MERCURYDESK_GMAIL_CLIENT_SECRET"
        : provider === "outlook"
          ? "MERCURYDESK_OUTLOOK_CLIENT_ID / MERCURYDESK_OUTLOOK_CLIENT_SECRET"
          : "MERCURYDESK_GITHUB_CLIENT_ID / MERCURYDESK_GITHUB_CLIENT_SECRET";
    const callbackUrl = `http://127.0.0.1:8000/api/v1/accounts/oauth/${provider}/callback`;
    popup.document.title = "OAuth 未配置";
    popup.document.body.innerHTML = `
          <div style="font-family:system-ui;padding:20px;line-height:1.65">
            <h3 style="margin:0 0 8px">未完成 ${OAUTH_PROVIDER_LABEL[provider]} OAuth 配置</h3>
            <p style="margin:0 0 12px">${message}</p>
            <ol style="margin:0 0 12px;padding-left:20px">
              <li>在后端环境变量设置：<code>${envHint}</code></li>
              <li>OAuth 回调地址填：<code>${callbackUrl}</code></li>
              <li>重启后端后再次点击授权</li>
            </ol>
            <p style="margin:0;color:#6b7280">提示：建议在 <code>backend</code> 目录启动后端。</p>
          </div>
        `;
    return true;
  };

  const connectOAuth = async (provider: OAuthSourceProvider) => {
    setOauthConnecting(provider);
    const knownAccountIds = new Set<number>();
    let allowFallback = false;
    let popup: Window | null = null;
    try {
      if (
        newProvider === provider &&
        oauthClientIdInput.trim() &&
        oauthClientSecretInput.trim()
      ) {
        await saveOAuthConfig(
          provider,
          oauthClientIdInput,
          oauthClientSecretInput,
          { silent: true },
        );
      }
      popup = openOAuthPopup(`oauth-${provider}`, "正在跳转到授权页面…");

      const baselineAccounts = await listAccounts().catch(() => accounts ?? []);
      baselineAccounts
        .filter((item) => item.provider.toLowerCase() === provider)
        .forEach((item) => knownAccountIds.add(item.id));

      const started = await startAccountOAuth(provider);
      const allowedOrigin = extractRedirectOriginFromAuthUrl(started.auth_url);
      popup.location.href = started.auth_url;
      allowFallback = true;

      const result = await waitForOAuthPopupMessage(popup, { allowedOrigin });

      if (!result.ok || !result.account_id) {
        throw new Error(result.error || "授权失败");
      }
      await postConnectSync(result.account_id, OAUTH_PROVIDER_LABEL[provider]);
      mutateAccounts();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (
        popup &&
        !popup.closed &&
        !showOAuthSetupGuide(popup, provider, message)
      )
        popup.close();
      if (allowFallback) {
        const fallbackAccount = await findNewOAuthAccount(
          provider,
          knownAccountIds,
        );
        if (fallbackAccount) {
          await postConnectSync(
            fallbackAccount.id,
            OAUTH_PROVIDER_LABEL[provider],
          );
          return;
        }
      }
      throw new Error(message);
    } finally {
      setOauthConnecting(null);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast("已复制到剪贴板", "success");
    } catch {
      showToast("复制失败，请手动复制", "error");
    }
  };

  const openExternalPage = (url: string) => {
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const saveOAuthConfig = async (
    provider: OAuthSourceProvider,
    clientId: string,
    clientSecret: string,
    options?: { silent?: boolean },
  ) => {
    const clientIdTrimmed = clientId.trim();
    const clientSecretTrimmed = clientSecret.trim();
    if (!clientIdTrimmed || !clientSecretTrimmed) {
      throw new Error("请填写 client_id 和 client_secret，或导入 OAuth JSON");
    }
    setSavingOAuthConfig(true);
    try {
      const updated = await updateOAuthProviderConfig(provider, {
        client_id: clientIdTrimmed,
        client_secret: clientSecretTrimmed,
      });
      mutateOAuthProviderConfig(updated, { revalidate: false });
      setOauthClientIdInput(clientIdTrimmed);
      setOauthClientSecretInput("");
      if (!options?.silent) {
        showToast(
          `${OAUTH_PROVIDER_LABEL[provider]} OAuth 凭据已保存`,
          "success",
        );
      }
    } finally {
      setSavingOAuthConfig(false);
    }
  };

  const handleImportOAuthJson = async (
    provider: OAuthSourceProvider,
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as any;
      const candidate = parsed?.web || parsed?.installed || parsed;
      const clientId = String(candidate?.client_id || "").trim();
      const clientSecret = String(candidate?.client_secret || "").trim();
      if (!clientId || !clientSecret) {
        throw new Error("文件中未找到 client_id/client_secret");
      }
      setOauthClientIdInput(clientId);
      setOauthClientSecretInput(clientSecret);
      await saveOAuthConfig(provider, clientId, clientSecret);
    } catch (e) {
      showToast(
        e instanceof Error ? `导入失败：${e.message}` : "导入失败",
        "error",
      );
    }
  };

  const handleAddAccount = async () => {
    setAddingAccount(true);
    try {
      if (newProvider === "gmail" || newProvider === "outlook") {
        await connectOAuth(newProvider);
      } else if (newProvider === "github") {
        if (githubConnectMode === "oauth") {
          await connectOAuth("github");
        } else {
          const token = githubToken.trim();
          if (!token) throw new Error("请填写 GitHub Token");
          await connectAndSync(
            {
              provider: "github",
              identifier: githubIdentifier.trim() || "github",
              access_token: token,
            },
            "GitHub",
          );
        }
      } else if (newProvider === "forward") {
        const sourceEmail = forwardSourceEmail.trim().toLowerCase();
        if (!sourceEmail) throw new Error("请填写要接入的邮箱地址");
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(sourceEmail)) {
          throw new Error("请输入有效的邮箱地址");
        }
        const created = await createAccount({
          provider: "forward",
          identifier: sourceEmail,
          forward_source_email: sourceEmail,
        });
        const info = await getForwardAccountInfo(created.id);
        setLatestForwardInfo(info);
        showToast("转发地址已生成，请在邮箱里设置自动转发", "success");
      } else if (newProvider === "imap") {
        const email = imapUsername.trim();
        const host = imapHost.trim();
        const mailbox = (imapMailbox || "INBOX").trim();
        if (!email || !imapPassword) throw new Error("请填写邮箱与授权码/密码");
        if (!host)
          throw new Error("请先选择邮箱服务商，或在高级设置中填写 IMAP 主机");

        const port = Number(imapPort || 993);
        await connectAndSync(
          {
            provider: "imap",
            identifier: email,
            imap_host: host,
            imap_port: Number.isFinite(port) ? port : 993,
            imap_use_ssl: imapUseSsl,
            imap_username: email,
            imap_password: imapPassword,
            imap_mailbox: mailbox,
          },
          "邮箱",
        );
      } else if (newProvider === "rss") {
        const feedUrl = rssFeedUrl.trim();
        if (!feedUrl) throw new Error("请填写 RSS / Atom 订阅链接");
        const displayName = rssDisplayName.trim();
        const homepage = rssHomepageUrl.trim();
        await connectAndSync(
          {
            provider: "rss",
            identifier: displayName || homepage || feedUrl,
            feed_url: feedUrl,
            feed_homepage_url: homepage || undefined,
            feed_display_name: displayName || undefined,
          },
          "RSS/Blog",
        );
      } else if (newProvider === "bilibili") {
        const uid = bilibiliUid.trim();
        if (!uid) throw new Error("请填写 Bilibili UP 主 UID");
        await connectAndSync(
          {
            provider: "bilibili",
            identifier: uid,
            bilibili_uid: uid,
            feed_display_name: `B站 UP ${uid}`,
          },
          "Bilibili",
        );
      } else if (newProvider === "x") {
        const username = xUsername.trim().replace(/^@/, "");
        if (!username) throw new Error("请填写 X 用户名");
        await connectAndSync(
          {
            provider: "x",
            identifier: username,
            x_username: username,
            feed_display_name: `X @${username}`,
          },
          "X",
        );
      } else if (newProvider === "douyin") {
        const secUid = douyinSecUid.trim();
        if (!secUid) throw new Error("请填写抖音号或 sec_uid");
        await connectAndSync(
          {
            provider: "douyin",
            identifier: secUid,
            feed_url: "",
            feed_homepage_url: secUid,
            feed_display_name: "抖音用户",
          },
          "抖音",
        );
      } else if (newProvider === "xiaohongshu") {
        const userId = xiaohongshuUserId.trim();
        if (!userId) throw new Error("请填写小红书用户 UID");
        await connectAndSync(
          {
            provider: "xiaohongshu",
            identifier: userId,
            feed_url: "",
            feed_homepage_url: userId,
            feed_display_name: "小红书用户",
          },
          "小红书",
        );
      } else if (newProvider === "weibo") {
        const uid = weiboUid.trim();
        if (!uid) throw new Error("请填写微博用户 UID");
        await connectAndSync(
          {
            provider: "weibo",
            identifier: uid,
            feed_url: "",
            feed_homepage_url: uid,
            feed_display_name: "微博用户",
          },
          "微博",
        );
      } else {
        await connectAndSync(
          {
            provider: "mock",
            identifier: "demo",
            access_token: "x",
          },
          "演示数据",
        );
      }

      mutateAccounts();
      setImapPassword("");
      setForwardSourceEmail("");
      setRssFeedUrl("");
      setRssHomepageUrl("");
      setRssDisplayName("");
      setBilibiliUid("");
      setXUsername("");
      setGithubToken("");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "连接失败", "error");
    } finally {
      setAddingAccount(false);
    }
  };

  const handleDeleteAccount = async (id: number) => {
    const ok = await confirm({
      title: "断开账户",
      message: "确定要断开该账户吗？",
      severity: "error",
    });
    if (!ok) return;
    try {
      await deleteAccount(id);
      showToast("已断开连接", "success");
      mutateAccounts();
    } catch (e) {
      showToast("断开失败", "error");
    }
  };

  const handleSync = async (id: number, forceFull = false) => {
    setSyncing(id);
    try {
      const res = await syncAccount(id, forceFull);
      showToast(`同步完成：+${res.inserted}`, "success");
      mutateAccounts(); // Update last synced time
    } catch (e) {
      showToast(e instanceof Error ? e.message : "同步失败", "error");
    } finally {
      setSyncing(null);
    }
  };

  const handleForceSync = async (id: number) => {
    const ok = await confirm({
      title: "全量同步",
      message: "全量重新同步？这会清除旧数据并重新拉取。",
      severity: "warning",
    });
    if (!ok) return;
    handleSync(id, true);
  };

  const handleSaveXConfig = async () => {
    const token = xBearerToken.trim();
    if (!token) {
      showToast("请填写 X API Bearer Token", "error");
      return;
    }
    setSavingXConfig(true);
    try {
      await updateXApiConfig(token);
      mutateXApiConfig();
      setXBearerToken("");
      showToast("X API Token 已保存", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSavingXConfig(false);
    }
  };

  const handleSaveXCookies = async () => {
    const authToken = xAuthToken.trim();
    const ct0 = xCt0.trim();
    if (!authToken || !ct0) {
      showToast("请填写 auth_token 与 ct0", "error");
      return;
    }
    setSavingXCookies(true);
    try {
      await updateXAuthCookies(authToken, ct0);
      mutateXApiConfig();
      setXAuthToken("");
      setXCt0("");
      showToast("X Cookie 认证已保存", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "保存失败", "error");
    } finally {
      setSavingXCookies(false);
    }
  };

  const handleDeleteXCookies = async () => {
    try {
      await deleteXAuthCookies();
      mutateXApiConfig();
      showToast("X Cookie 已删除", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "删除失败", "error");
    }
  };

  const useOAuthConnectFlow =
    newProvider === "gmail" ||
    newProvider === "outlook" ||
    (newProvider === "github" && githubConnectMode === "oauth");
  const showGithubTokenForm =
    newProvider === "github" && githubConnectMode === "token";
  const addAccountButtonLabel = addingAccount
    ? "连接中…"
    : oauthConnecting
      ? "授权中…"
      : useOAuthConnectFlow
        ? "开始授权连接"
        : newProvider === "forward"
          ? "生成转发地址"
          : "连接并同步";

  return (
    <>
      {/* Connected Accounts */}
      <Grid size={{ xs: 12 }}>
        <Paper sx={{ p: 4 }}>
          <Typography variant="h6" gutterBottom>
            已连接账户
          </Typography>
          <Typography variant="body2" color="textSecondary" mb={3}>
            管理你的消息来源。推荐先用 Gmail/Outlook/GitHub
            一键授权；也支持转发接入、IMAP 高级接入、RSS、Bilibili、X。
          </Typography>

          <ConnectedAccountsList
            accounts={accounts ?? []}
            syncingAccountId={syncing}
            accountIcon={accountIcon}
            onSyncIncremental={handleSync}
            onSyncFull={async (id) => {
              const ok = await confirm({
                title: "全量同步",
                message: "全量重新同步？这会清除旧数据并重新拉取。",
                severity: "warning",
              });
              if (!ok) return;
              await handleSync(id, true);
            }}
            onDelete={handleDeleteAccount}
          />

          <Box
            mt={4}
            p={3}
            bgcolor="action.hover"
            borderRadius={0}
            border={1}
            borderColor="divider"
          >
            <Typography variant="subtitle2" fontWeight="bold" mb={0.5}>
              连接新来源（简化版）
            </Typography>
            <Typography variant="caption" color="textSecondary">
              只填必要字段，连接后自动同步一次验证。
            </Typography>

            <Box mt={2.5}>
              <Grid container spacing={2} alignItems="center">
                <Grid size={{ xs: 12, sm: 4 }}>
                  <TextField
                    select
                    fullWidth
                    size="small"
                    label="来源类型"
                    value={newProvider}
                    onChange={(e) =>
                      setNewProvider(e.target.value as SourceProvider)
                    }
                    SelectProps={{ native: true }}
                  >
                    <option value="gmail">Gmail（一键授权，推荐）</option>
                    <option value="outlook">Outlook（一键授权，推荐）</option>
                    <option value="github">GitHub（OAuth / Token）</option>
                    <option value="forward">邮箱转发接入（更简）</option>
                    <option value="imap">邮箱（IMAP）</option>
                    <option value="rss">RSS / Blog</option>
                    <option value="bilibili">Bilibili UP 动态</option>
                    <option value="x">X 用户更新</option>
                    <option value="douyin">抖音用户动态</option>
                    <option value="xiaohongshu">小红书用户笔记</option>
                    <option value="weibo">微博用户动态</option>
                    <option value="mock">演示数据</option>
                  </TextField>
                </Grid>
                <AccountProviderFields
                  newProvider={newProvider}
                  githubConnectMode={githubConnectMode}
                  onGithubConnectModeChange={setGithubConnectMode}
                  useOAuthConnectFlow={useOAuthConnectFlow}
                  showGithubTokenForm={showGithubTokenForm}
                  oauthProviderConfig={oauthProviderConfig}
                  oauthClientIdInput={oauthClientIdInput}
                  onOauthClientIdInputChange={setOauthClientIdInput}
                  oauthClientSecretInput={oauthClientSecretInput}
                  onOauthClientSecretInputChange={setOauthClientSecretInput}
                  savingOAuthConfig={savingOAuthConfig}
                  onSaveOAuthConfig={async (
                    provider,
                    clientId,
                    clientSecret,
                  ) => {
                    try {
                      await saveOAuthConfig(provider, clientId, clientSecret);
                    } catch (error) {
                      showToast(
                        error instanceof Error
                          ? error.message
                          : "保存 OAuth 配置失败",
                        "error",
                      );
                    }
                  }}
                  onImportOAuthJson={handleImportOAuthJson}
                  onOpenExternalPage={openExternalPage}
                  githubIdentifier={githubIdentifier}
                  onGithubIdentifierChange={setGithubIdentifier}
                  githubToken={githubToken}
                  onGithubTokenChange={setGithubToken}
                  forwardSourceEmail={forwardSourceEmail}
                  onForwardSourceEmailChange={setForwardSourceEmail}
                  latestForwardInfo={latestForwardInfo}
                  onCopyText={copyText}
                  imapPreset={imapPreset}
                  onImapPresetChange={setImapPreset}
                  imapUsername={imapUsername}
                  onImapUsernameChange={setImapUsername}
                  imapPassword={imapPassword}
                  onImapPasswordChange={setImapPassword}
                  imapHost={imapHost}
                  onImapHostChange={setImapHost}
                  imapPort={imapPort}
                  onImapPortChange={setImapPort}
                  imapUseSsl={imapUseSsl}
                  onImapUseSslChange={setImapUseSsl}
                  imapMailbox={imapMailbox}
                  onImapMailboxChange={setImapMailbox}
                  showImapAdvanced={showImapAdvanced}
                  onToggleImapAdvanced={() =>
                    setShowImapAdvanced((value) => !value)
                  }
                  rssFeedUrl={rssFeedUrl}
                  onRssFeedUrlChange={setRssFeedUrl}
                  rssHomepageUrl={rssHomepageUrl}
                  onRssHomepageUrlChange={setRssHomepageUrl}
                  rssDisplayName={rssDisplayName}
                  onRssDisplayNameChange={setRssDisplayName}
                  onFillClaudeBlog={() => {
                    setRssFeedUrl("https://claude.com/blog/");
                    setRssHomepageUrl("https://claude.com/blog/");
                    setRssDisplayName("Claude Blog");
                  }}
                  bilibiliUid={bilibiliUid}
                  onBilibiliUidChange={setBilibiliUid}
                  xUsername={xUsername}
                  onXUsernameChange={setXUsername}
                  xApiConfig={xApiConfig}
                  xBearerToken={xBearerToken}
                  onXBearerTokenChange={setXBearerToken}
                  savingXConfig={savingXConfig}
                  onSaveXConfig={handleSaveXConfig}
                  xAuthToken={xAuthToken}
                  onXAuthTokenChange={setXAuthToken}
                  xCt0={xCt0}
                  onXCt0Change={setXCt0}
                  savingXCookies={savingXCookies}
                  onSaveXCookies={handleSaveXCookies}
                  onDeleteXCookies={handleDeleteXCookies}
                  douyinSecUid={douyinSecUid}
                  onDouyinSecUidChange={setDouyinSecUid}
                  xiaohongshuUserId={xiaohongshuUserId}
                  onXiaohongshuUserIdChange={setXiaohongshuUserId}
                  weiboUid={weiboUid}
                  onWeiboUidChange={setWeiboUid}
                />{" "}
                <Grid size={{ xs: 12 }}>
                  <Button
                    fullWidth
                    variant="contained"
                    onClick={handleAddAccount}
                    disabled={
                      addingAccount ||
                      oauthConnecting !== null ||
                      (useOAuthConnectFlow && savingOAuthConfig)
                    }
                  >
                    {addAccountButtonLabel}
                  </Button>
                </Grid>
              </Grid>
            </Box>
          </Box>
        </Paper>
      </Grid>

      {ConfirmDialog}
    </>
  );
}
