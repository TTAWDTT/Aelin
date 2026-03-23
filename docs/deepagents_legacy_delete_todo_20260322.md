## DeepAgents Legacy Delete TODO (2026-03-22)

- [x] 删除 `backend/app/schemas.py` 中类型 `AelinPinRecommendationItem`。
- [x] 删除 `backend/app/schemas.py` 中类型 `AelinDailyBriefAction` 与 `AelinDailyBrief`。
- [x] 删除 `backend/app/schemas.py` 中类型 `AelinLayoutCard`。
- [x] 删除 `backend/app/schemas.py` 中类型 `AelinNotificationItem`、`AelinNotificationResponse`、`AelinProactivePollResponse`。
- [x] 删除 `backend/app/schemas.py` 中类型 `AgentCardLayoutItem`、`AgentCardLayoutUpdate`。
- [x] 删除 `backend/app/schemas.py` 中类型 `AgentPinRecommendationItem`、`AgentPinRecommendationResponse`。
- [x] 删除 `backend/app/schemas.py` 中类型 `AgentDailyBriefAction`、`AgentDailyBriefResponse`。

- [x] 删除 backend 中所有 plane / PinchTab 相关代码注释与字符串（例如 `_try_agent_loop_chat` 内关于 plane task 的注释）。
- [x] 删除 `backend/app/settings.py` 中所有 plane / pinchtab 相关配置项和常量。
- [x] 删除 backend 仓库根目录下与 PinchTab 相关的辅助目录和文件（例如 `.pinchtab/` 及内部内容）。

- [x] 删除 backend 中所有 `/api/v1/aelin/notifications` 与 `/api/v1/aelin/proactive/poll` 相关的 router、service 与调度逻辑。
- [x] 删除 backend 中所有 Agent inbox / layout / pin 推荐相关的 router 与 service（如卡片布局、pin 推荐、daily brief 等接口及其 glue 代码）。

- [x] 从 `frontend/src/shared/api/types.ts` 中 `AelinContextResponse` 删除字段 `focus_items`。
- [x] 从 `frontend/src/shared/api/types.ts` 中 `AelinContextResponse` 删除字段 `pin_recommendations`。
- [x] 从 `frontend/src/shared/api/types.ts` 中 `AelinContextResponse` 删除字段 `layout_cards`。
- [x] 从 `frontend/src/shared/api/types.ts` 中 `AelinContextResponse` 删除字段 `notifications` 与 `daily_brief`。
- [x] 删除 `frontend/src/shared/api/types.ts` 中接口 `AgentFocusItemOut`、`AelinPinRecommendationItem`、`AelinDailyBrief`、`AelinNotificationItem`、`AelinNotificationResponse`、`AelinProactivePollResponse`。

- [x] 从 `frontend/src/features/chat/chatI18n.ts` 删除所有 `trace.plane.*` 的多语言 key 与文案。
- [x] 从 `frontend/src/features/chat/chatI18n.ts` 删除所有 `plane.chip.*` 的多语言 key 与文案。

- [x] 从 `frontend/src/features/chat/traceUtils.ts` 的 `looksLikeWriteCall` 中删除对 `plane` / `plane_*` / `pinchtab` 的写入判定分支。
- [x] 从 `frontend/src/features/chat/traceUtils.ts` 中删除 `extractPlaneTaskMeta` 函数及其导出声明。
- [x] 从 `frontend/src/features/chat/traceUtils.ts` 中删除与 plane 相关的类型定义（如 `PlaneTaskState`、`PlaneTaskMeta` 及相关内部辅助类型`）。

- [x] 从 `frontend/src/features/chat/components/ProviderIcon.tsx` 中删除 `ProviderKind` 的 `'plane'` 分支和所有 plane 图标样式映射。

- [x] 从 `frontend/src/features/chat/ChatView.tsx` 中删除关于 “工具/plane trace” 的注释与任何 plane 相关描述。
