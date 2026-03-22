# Remove MercuryDesk Inbox Stack

## Goal

只保留 DeepAgents 真正需要的能力，彻底删除 MercuryDesk 时代遗留的 inbox / account aggregation / OAuth 接入体系。

## Todo

- [x] 删除 `backend/app/services/oauth_clients.py`，连同 Gmail / Outlook / GitHub OAuth 发起、回调、refresh token 全链路一起移除。
- [x] 删除 `backend/app/routers/accounts.py` 中 OAuth 相关接口与配置接口。
- [x] 删除 `OAuthCredentialConfig` 相关模型、CRUD、schema 与测试。
- [x] 删除 `ConnectedAccount` 中仅服务 OAuth 邮箱/通知接入的逻辑分支。
- [x] 删除 `backend/app/sync.py` 以及 `backend/app/services/sync_jobs.py`，移除账号同步能力。
- [x] 删除 `/accounts/{id}/sync`、`/accounts/sync-jobs/*` 等同步接口。
- [x] 删除 Gmail / Outlook / GitHub / IMAP / Feed / X / Bilibili / Douyin / Xiaohongshu / Weibo / Mock connectors。
- [x] 删除 `/accounts`、`/contacts`、`/messages` 这整套 inbox 聚合路由。
- [x] 删除 `Contact`、`Message`、`ConnectedAccount`、`ForwardAccountConfig`、`XApiConfig`、`OAuthCredentialConfig` 这些只服务聚合收件箱的模型及其关联逻辑。
- [x] 删除 `backend/app/crud.py` 中只服务 accounts / contacts / messages / oauth / sync 的函数。
- [x] 删除 `backend/app/routers/inbound.py` 和邮件转发接入链路。
- [x] 删除 `backend/app/services/forwarding.py` 与 forward address / signature 相关逻辑。
- [x] 删除 `backend/app/services/avatar.py`、gravatar 兜底头像、联系人头像刷新逻辑。
- [x] 清理 `remote_control` 中若仍引用旧 inbox/message 语义的部分，只保留纯 DeepAgents 控制能力。
- [x] 删除所有与聚合内容搜索、消息预览、未读数、联系人列表相关的 schema。
- [x] 删除所有对应前端 API 和页面状态，如果前端还展示 accounts / contacts / messages / oauth config。
- [x] 删除只为这些能力存在的测试：`test_api.py` 中相关段落，以及 accounts / sync / inbound / oauth / contact / message 相关测试。
- [x] 删除 docs 中所有关于 MercuryDesk inbox、邮件转发、OAuth 账号接入、聚合收件箱的文档。
- [x] 删除源码和桌面壳中剩余的 `MercuryDesk` 命名、数据库文件名、文案、描述和构建残留。

## End State

- [x] Aelin 只保留 DeepAgents runtime、file memory、skills、自定义工具、device / web / gws / attachments 等 agent-centric 能力。
- [x] 仓库中不再存在 MercuryDesk inbox/account aggregation 产品壳。
