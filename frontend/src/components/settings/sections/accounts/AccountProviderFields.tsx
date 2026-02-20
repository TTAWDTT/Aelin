import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Grid from "@mui/material/Grid";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type {
  ForwardAccountInfo,
  OAuthProviderConfig,
  XApiConfig,
} from "../../../../api";
import type {
  GithubConnectMode,
  OAuthSourceProvider,
  SourceProvider,
} from "./types";

const GMAIL_OAUTH_CONSOLE_URL =
  "https://console.cloud.google.com/apis/credentials";
const GMAIL_API_ENABLE_URL =
  "https://console.cloud.google.com/apis/library/gmail.googleapis.com";
const GITHUB_OAUTH_APPS_URL = "https://github.com/settings/developers";
const GITHUB_OAUTH_DOCS_URL =
  "https://docs.github.com/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app";
const GITHUB_PAT_URL = "https://github.com/settings/tokens";
const GITHUB_PAT_DOCS_URL =
  "https://docs.github.com/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens";
const OUTLOOK_OAUTH_PORTAL_URL =
  "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade";

const OAUTH_PROVIDER_LABEL: Record<OAuthSourceProvider, string> = {
  gmail: "Gmail",
  outlook: "Outlook",
  github: "GitHub",
};

type AccountProviderFieldsProps = {
  newProvider: SourceProvider;
  githubConnectMode: GithubConnectMode;
  onGithubConnectModeChange: (mode: GithubConnectMode) => void;
  useOAuthConnectFlow: boolean;
  showGithubTokenForm: boolean;
  oauthProviderConfig?: OAuthProviderConfig;
  oauthClientIdInput: string;
  onOauthClientIdInputChange: (value: string) => void;
  oauthClientSecretInput: string;
  onOauthClientSecretInputChange: (value: string) => void;
  savingOAuthConfig: boolean;
  onSaveOAuthConfig: (
    provider: OAuthSourceProvider,
    clientId: string,
    clientSecret: string,
  ) => Promise<void> | void;
  onImportOAuthJson: (
    provider: OAuthSourceProvider,
    event: React.ChangeEvent<HTMLInputElement>,
  ) => Promise<void> | void;
  onOpenExternalPage: (url: string) => void;
  githubIdentifier: string;
  onGithubIdentifierChange: (value: string) => void;
  githubToken: string;
  onGithubTokenChange: (value: string) => void;
  forwardSourceEmail: string;
  onForwardSourceEmailChange: (value: string) => void;
  latestForwardInfo: ForwardAccountInfo | null;
  onCopyText: (text: string) => Promise<void> | void;
  imapPreset: "gmail" | "outlook" | "icloud" | "qq" | "163" | "custom";
  onImapPresetChange: (
    preset: "gmail" | "outlook" | "icloud" | "qq" | "163" | "custom",
  ) => void;
  imapUsername: string;
  onImapUsernameChange: (value: string) => void;
  imapPassword: string;
  onImapPasswordChange: (value: string) => void;
  imapHost: string;
  onImapHostChange: (value: string) => void;
  imapPort: string;
  onImapPortChange: (value: string) => void;
  imapUseSsl: boolean;
  onImapUseSslChange: (value: boolean) => void;
  imapMailbox: string;
  onImapMailboxChange: (value: string) => void;
  showImapAdvanced: boolean;
  onToggleImapAdvanced: () => void;
  rssFeedUrl: string;
  onRssFeedUrlChange: (value: string) => void;
  rssHomepageUrl: string;
  onRssHomepageUrlChange: (value: string) => void;
  rssDisplayName: string;
  onRssDisplayNameChange: (value: string) => void;
  onFillClaudeBlog: () => void;
  bilibiliUid: string;
  onBilibiliUidChange: (value: string) => void;
  xUsername: string;
  onXUsernameChange: (value: string) => void;
  xApiConfig?: XApiConfig;
  xBearerToken: string;
  onXBearerTokenChange: (value: string) => void;
  savingXConfig: boolean;
  onSaveXConfig: () => Promise<void> | void;
  xAuthToken: string;
  onXAuthTokenChange: (value: string) => void;
  xCt0: string;
  onXCt0Change: (value: string) => void;
  savingXCookies: boolean;
  onSaveXCookies: () => Promise<void> | void;
  onDeleteXCookies: () => Promise<void> | void;
  douyinSecUid: string;
  onDouyinSecUidChange: (value: string) => void;
  xiaohongshuUserId: string;
  onXiaohongshuUserIdChange: (value: string) => void;
  weiboUid: string;
  onWeiboUidChange: (value: string) => void;
};

export function AccountProviderFields(props: AccountProviderFieldsProps) {
  const {
    newProvider,
    githubConnectMode,
    onGithubConnectModeChange,
    useOAuthConnectFlow,
    showGithubTokenForm,
    oauthProviderConfig,
    oauthClientIdInput,
    onOauthClientIdInputChange,
    oauthClientSecretInput,
    onOauthClientSecretInputChange,
    savingOAuthConfig,
    onSaveOAuthConfig,
    onImportOAuthJson,
    onOpenExternalPage,
    githubIdentifier,
    onGithubIdentifierChange,
    githubToken,
    onGithubTokenChange,
    forwardSourceEmail,
    onForwardSourceEmailChange,
    latestForwardInfo,
    onCopyText,
    imapPreset,
    onImapPresetChange,
    imapUsername,
    onImapUsernameChange,
    imapPassword,
    onImapPasswordChange,
    imapHost,
    onImapHostChange,
    imapPort,
    onImapPortChange,
    imapUseSsl,
    onImapUseSslChange,
    imapMailbox,
    onImapMailboxChange,
    showImapAdvanced,
    onToggleImapAdvanced,
    rssFeedUrl,
    onRssFeedUrlChange,
    rssHomepageUrl,
    onRssHomepageUrlChange,
    rssDisplayName,
    onRssDisplayNameChange,
    onFillClaudeBlog,
    bilibiliUid,
    onBilibiliUidChange,
    xUsername,
    onXUsernameChange,
    xApiConfig,
    xBearerToken,
    onXBearerTokenChange,
    savingXConfig,
    onSaveXConfig,
    xAuthToken,
    onXAuthTokenChange,
    xCt0,
    onXCt0Change,
    savingXCookies,
    onSaveXCookies,
    onDeleteXCookies,
    douyinSecUid,
    onDouyinSecUidChange,
    xiaohongshuUserId,
    onXiaohongshuUserIdChange,
    weiboUid,
    onWeiboUidChange,
  } = props;

  return (
    <>
      {(newProvider === "gmail" ||
        newProvider === "outlook" ||
        newProvider === "github") && (
        <>
          {newProvider === "github" && (
            <Grid size={{ xs: 12, sm: 5 }}>
              <TextField
                select
                fullWidth
                size="small"
                label="GitHub 接入方式"
                value={githubConnectMode}
                onChange={(event) =>
                  onGithubConnectModeChange(
                    event.target.value as GithubConnectMode,
                  )
                }
                SelectProps={{ native: true }}
              >
                <option value="oauth">OAuth 一键授权（推荐）</option>
                <option value="token">手动 Token（兼容旧方式）</option>
              </TextField>
            </Grid>
          )}

          {useOAuthConnectFlow && (
            <>
              <Grid size={{ xs: 12 }}>
                <Alert severity="success" sx={{ borderRadius: 0 }}>
                  推荐方式：点击下方按钮，跳转到{" "}
                  {newProvider === "gmail"
                    ? "Google"
                    : newProvider === "outlook"
                      ? "Microsoft"
                      : "GitHub"}{" "}
                  官方授权页，完成一次授权即可接入
                  {newProvider === "github" ? "通知" : "邮件"}。
                  {oauthProviderConfig?.configured
                    ? "（当前已配置 OAuth 凭据）"
                    : "（首次请先保存 OAuth 凭据，可在此页完成）"}
                </Alert>
              </Grid>
              <Grid size={{ xs: 12 }}>
                <Alert
                  severity={
                    oauthProviderConfig?.configured ? "info" : "warning"
                  }
                  sx={{ borderRadius: 0 }}
                >
                  {oauthProviderConfig?.configured
                    ? `已保存 ${OAUTH_PROVIDER_LABEL[newProvider as OAuthSourceProvider]} OAuth 配置：${oauthProviderConfig.client_id_hint || "已隐藏"}`
                    : `尚未保存 ${OAUTH_PROVIDER_LABEL[newProvider as OAuthSourceProvider]} OAuth 配置。你可以直接在当前页面保存，无需改 .env。`}
                </Alert>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  fullWidth
                  size="small"
                  label="OAuth Client ID"
                  value={oauthClientIdInput}
                  onChange={(event) =>
                    onOauthClientIdInputChange(event.target.value)
                  }
                  placeholder={
                    newProvider === "gmail"
                      ? "xxx.apps.googleusercontent.com"
                      : newProvider === "github"
                        ? "Iv1.***"
                        : "应用 Client ID"
                  }
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  fullWidth
                  size="small"
                  type="password"
                  label="OAuth Client Secret"
                  value={oauthClientSecretInput}
                  onChange={(event) =>
                    onOauthClientSecretInputChange(event.target.value)
                  }
                  placeholder="输入后仅本次显示"
                />
              </Grid>
              <Grid size={{ xs: 12 }} display="flex" gap={1.2} flexWrap="wrap">
                <Button
                  variant="outlined"
                  disabled={savingOAuthConfig}
                  onClick={() =>
                    onSaveOAuthConfig(
                      newProvider as OAuthSourceProvider,
                      oauthClientIdInput,
                      oauthClientSecretInput,
                    )
                  }
                >
                  {savingOAuthConfig ? "保存中…" : "保存 OAuth 配置"}
                </Button>
                {newProvider !== "github" && (
                  <Button
                    variant="text"
                    component="label"
                    disabled={savingOAuthConfig}
                  >
                    导入 OAuth JSON 并保存
                    <input
                      hidden
                      type="file"
                      accept="application/json,.json"
                      onChange={(event) => {
                        void onImportOAuthJson(
                          newProvider as OAuthSourceProvider,
                          event,
                        );
                      }}
                    />
                  </Button>
                )}
                {newProvider === "gmail" && (
                  <>
                    <Button
                      variant="text"
                      onClick={() =>
                        onOpenExternalPage(GMAIL_OAUTH_CONSOLE_URL)
                      }
                    >
                      跳转查看信息（OAuth 配置页，新窗口）
                    </Button>
                    <Button
                      variant="text"
                      onClick={() => onOpenExternalPage(GMAIL_API_ENABLE_URL)}
                    >
                      跳转启用 Gmail API（新窗口）
                    </Button>
                  </>
                )}
                {newProvider === "outlook" && (
                  <Button
                    variant="text"
                    onClick={() => onOpenExternalPage(OUTLOOK_OAUTH_PORTAL_URL)}
                  >
                    跳转到 Azure 应用注册（新窗口）
                  </Button>
                )}
                {newProvider === "github" && (
                  <>
                    <Button
                      variant="text"
                      onClick={() => onOpenExternalPage(GITHUB_OAUTH_APPS_URL)}
                    >
                      跳转到 GitHub OAuth Apps（新窗口）
                    </Button>
                    <Button
                      variant="text"
                      onClick={() => onOpenExternalPage(GITHUB_OAUTH_DOCS_URL)}
                    >
                      跳转查看 GitHub OAuth 文档（新窗口）
                    </Button>
                  </>
                )}
              </Grid>
            </>
          )}

          {showGithubTokenForm && (
            <>
              <Grid size={{ xs: 12 }}>
                <Alert severity="info" sx={{ borderRadius: 0 }}>
                  兼容旧方式：可直接填写 GitHub Token 接入通知，无需 OAuth
                  应用。建议使用 Classic PAT 并授予 <code>notifications</code>{" "}
                  权限。
                </Alert>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  fullWidth
                  size="small"
                  label="GitHub 用户名（可选）"
                  value={githubIdentifier}
                  onChange={(event) =>
                    onGithubIdentifierChange(event.target.value)
                  }
                  placeholder="如：octocat"
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField
                  fullWidth
                  size="small"
                  type="password"
                  label="GitHub Token"
                  value={githubToken}
                  onChange={(event) => onGithubTokenChange(event.target.value)}
                  placeholder="ghp_xxx"
                />
              </Grid>
              <Grid size={{ xs: 12 }} display="flex" gap={1.2} flexWrap="wrap">
                <Button
                  variant="text"
                  onClick={() => onOpenExternalPage(GITHUB_PAT_URL)}
                >
                  跳转创建 GitHub Token（新窗口）
                </Button>
                <Button
                  variant="text"
                  onClick={() => onOpenExternalPage(GITHUB_PAT_DOCS_URL)}
                >
                  查看 GitHub Token 文档（新窗口）
                </Button>
              </Grid>
            </>
          )}
        </>
      )}

      {newProvider === "forward" && (
        <>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="要接入的邮箱地址"
              value={forwardSourceEmail}
              onChange={(event) =>
                onForwardSourceEmailChange(event.target.value)
              }
              placeholder="you@example.com"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              创建后会生成一个专属转发地址。去你的邮箱设置里添加“自动转发到该地址”即可接入，无需再配置
              Webhook。
            </Alert>
          </Grid>
          {latestForwardInfo && (
            <Grid size={{ xs: 12 }}>
              <Alert severity="success" sx={{ borderRadius: 0 }}>
                <Box
                  display="flex"
                  alignItems="center"
                  justifyContent="space-between"
                  gap={1}
                  flexWrap="wrap"
                >
                  <Typography variant="body2">
                    专属转发地址：{latestForwardInfo.forward_address}
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() =>
                      void onCopyText(latestForwardInfo.forward_address)
                    }
                  >
                    复制地址
                  </Button>
                </Box>
                <Typography variant="caption" display="block" sx={{ mt: 0.8 }}>
                  已绑定邮箱：{latestForwardInfo.source_email}
                  。完成邮箱端自动转发后，新邮件会自动进入 MercuryDesk。
                </Typography>
              </Alert>
            </Grid>
          )}
        </>
      )}

      {newProvider === "imap" && (
        <>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField
              select
              fullWidth
              size="small"
              label="邮箱服务商"
              value={imapPreset}
              onChange={(event) =>
                onImapPresetChange(
                  event.target.value as
                    | "gmail"
                    | "outlook"
                    | "icloud"
                    | "qq"
                    | "163"
                    | "custom",
                )
              }
              SelectProps={{ native: true }}
            >
              <option value="gmail">Gmail</option>
              <option value="outlook">Outlook / Microsoft 365</option>
              <option value="icloud">iCloud</option>
              <option value="qq">QQ 邮箱</option>
              <option value="163">163 邮箱</option>
              <option value="custom">自定义</option>
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField
              fullWidth
              size="small"
              label="邮箱"
              value={imapUsername}
              onChange={(event) => onImapUsernameChange(event.target.value)}
              placeholder="your@email.com"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField
              fullWidth
              size="small"
              label="授权码 / 密码"
              type="password"
              value={imapPassword}
              onChange={(event) => onImapPasswordChange(event.target.value)}
              placeholder="建议使用应用专用密码"
            />
          </Grid>

          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              高级接入（兜底方案）：三步完成 ① 开启 IMAP ② 生成授权码 ③
              填写邮箱+授权码。优先推荐 Gmail/Outlook 一键授权。
            </Alert>
          </Grid>

          <Grid size={{ xs: 12 }}>
            <Box
              display="flex"
              alignItems="center"
              justifyContent="space-between"
            >
              <Typography variant="caption" color="textSecondary">
                当前：{imapHost || "未设置主机"}:{imapPort}（
                {imapUseSsl ? "SSL" : "无 SSL"}）
              </Typography>
              <Button
                size="small"
                variant="text"
                onClick={onToggleImapAdvanced}
              >
                {showImapAdvanced ? "收起高级设置" : "高级设置"}
              </Button>
            </Box>
            <Collapse in={showImapAdvanced}>
              <Grid container spacing={2} sx={{ mt: 0.5 }}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label="IMAP 主机"
                    placeholder="imap.example.com"
                    value={imapHost}
                    onChange={(event) => onImapHostChange(event.target.value)}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 3 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label="端口"
                    value={imapPort}
                    onChange={(event) => onImapPortChange(event.target.value)}
                    inputProps={{ inputMode: "numeric" }}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 3 }}>
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="space-between"
                    height="100%"
                  >
                    <Typography variant="body2" color="textSecondary">
                      使用 SSL
                    </Typography>
                    <Switch
                      checked={imapUseSsl}
                      onChange={(event) =>
                        onImapUseSslChange(event.target.checked)
                      }
                    />
                  </Box>
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label="邮箱文件夹"
                    placeholder="INBOX"
                    value={imapMailbox}
                    onChange={(event) =>
                      onImapMailboxChange(event.target.value)
                    }
                  />
                </Grid>
              </Grid>
            </Collapse>
          </Grid>
        </>
      )}

      {newProvider === "rss" && (
        <>
          <Grid size={{ xs: 12, sm: 8 }}>
            <TextField
              fullWidth
              size="small"
              label="RSS / Atom 地址"
              value={rssFeedUrl}
              onChange={(event) => onRssFeedUrlChange(event.target.value)}
              placeholder="https://example.com/feed.xml"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <Button fullWidth variant="outlined" onClick={onFillClaudeBlog}>
              一键填入 Claude Blog
            </Button>
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="显示名称（可选）"
              value={rssDisplayName}
              onChange={(event) => onRssDisplayNameChange(event.target.value)}
              placeholder="例如：Claude Blog"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="主页链接（可选）"
              value={rssHomepageUrl}
              onChange={(event) => onRssHomepageUrlChange(event.target.value)}
              placeholder="https://example.com"
            />
          </Grid>
        </>
      )}

      {newProvider === "bilibili" && (
        <>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="UP 主 UID"
              value={bilibiliUid}
              onChange={(event) => onBilibiliUidChange(event.target.value)}
              placeholder="如：546195"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              使用 B 站公开页面抓取 UP
              最新视频动态；若抓取失败会自动回退订阅源抓取。
            </Alert>
          </Grid>
        </>
      )}

      {newProvider === "x" && (
        <>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="X 用户名"
              value={xUsername}
              onChange={(event) => onXUsernameChange(event.target.value)}
              placeholder="@openai 或 openai"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              {xApiConfig?.configured
                ? `已配置官方 X API（${xApiConfig.token_hint || "已隐藏"}），将优先使用官方 API 获取推文。`
                : "默认使用公共网页接口抓取；配置官方 API Bearer Token 可获得更稳定的抓取效果。"}
            </Alert>
          </Grid>
          <Grid size={{ xs: 12, sm: 8 }}>
            <TextField
              fullWidth
              size="small"
              type="password"
              label="X API Bearer Token（可选，推荐）"
              value={xBearerToken}
              onChange={(event) => onXBearerTokenChange(event.target.value)}
              placeholder={
                xApiConfig?.configured ? "已配置（不显示）" : "AAAA..."
              }
              helperText="从 developer.x.com 获取，配置后优先使用官方 API"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <Button
              fullWidth
              variant="outlined"
              disabled={!xBearerToken.trim() || savingXConfig}
              onClick={() => void onSaveXConfig()}
              sx={{ height: "40px" }}
            >
              {savingXConfig ? "保存中…" : "保存 Token"}
            </Button>
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Button
              variant="text"
              size="small"
              onClick={() =>
                window.open(
                  "https://developer.x.com/",
                  "_blank",
                  "noopener,noreferrer",
                )
              }
            >
              前往 X 开发者平台获取 Bearer Token（新窗口）
            </Button>
          </Grid>

          <Grid size={{ xs: 12 }}>
            <Alert
              severity={xApiConfig?.cookies_configured ? "success" : "warning"}
              sx={{ borderRadius: 0 }}
            >
              {xApiConfig?.cookies_configured
                ? "已配置浏览器 Cookie 认证，将优先使用认证接口获取最新推文（支持按时间排序）。"
                : "推荐配置浏览器 Cookie：未认证接口只能获取热门推文（按互动量排序），可能遗漏最新推文。"}
            </Alert>
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              type="password"
              label="auth_token Cookie"
              value={xAuthToken}
              onChange={(event) => onXAuthTokenChange(event.target.value)}
              placeholder={
                xApiConfig?.cookies_configured
                  ? "已配置（不显示）"
                  : "粘贴 auth_token 值"
              }
              helperText="从浏览器 DevTools → Application → Cookies → x.com 获取"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              type="password"
              label="ct0 Cookie"
              value={xCt0}
              onChange={(event) => onXCt0Change(event.target.value)}
              placeholder={
                xApiConfig?.cookies_configured
                  ? "已配置（不显示）"
                  : "粘贴 ct0 值"
              }
              helperText="同样从 Cookies 中获取 ct0 的值"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Button
              fullWidth
              variant="outlined"
              disabled={!xAuthToken.trim() || !xCt0.trim() || savingXCookies}
              onClick={() => void onSaveXCookies()}
              sx={{ height: "40px" }}
            >
              {savingXCookies ? "保存中…" : "保存 Cookies"}
            </Button>
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            {xApiConfig?.cookies_configured && (
              <Button
                fullWidth
                variant="outlined"
                color="error"
                onClick={() => void onDeleteXCookies()}
                sx={{ height: "40px" }}
              >
                删除 Cookies
              </Button>
            )}
          </Grid>
        </>
      )}

      {newProvider === "douyin" && (
        <>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="抖音号或 sec_uid"
              value={douyinSecUid}
              onChange={(event) => onDouyinSecUidChange(event.target.value)}
              placeholder="如：douyin123 或 MS4wLjABAAAA..."
              helperText="支持直接输入抖音号，系统会自动解析"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              支持抖音号或 sec_uid，抓取用户最新视频动态。
            </Alert>
          </Grid>
        </>
      )}

      {newProvider === "xiaohongshu" && (
        <>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="小红书用户 UID"
              value={xiaohongshuUserId}
              onChange={(event) =>
                onXiaohongshuUserIdChange(event.target.value)
              }
              placeholder="如：5a1234567890abcdef123456"
              helperText="从用户主页链接 /user/profile/xxx 中获取"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              抓取小红书用户最新笔记动态。
            </Alert>
          </Grid>
        </>
      )}

      {newProvider === "weibo" && (
        <>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              fullWidth
              size="small"
              label="微博用户 UID"
              value={weiboUid}
              onChange={(event) => onWeiboUidChange(event.target.value)}
              placeholder="如：1234567890"
              helperText="从用户主页链接 weibo.com/u/xxx 中获取"
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Alert severity="info" sx={{ borderRadius: 0 }}>
              抓取微博用户最新动态。
            </Alert>
          </Grid>
        </>
      )}

      {newProvider === "mock" && (
        <Grid size={{ xs: 12 }}>
          <Alert severity="success" sx={{ borderRadius: 0 }}>
            连接演示数据用于快速体验界面（不会访问真实邮箱）。
          </Alert>
        </Grid>
      )}
    </>
  );
}
