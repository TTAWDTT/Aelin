# Aelin 全量审查与策略报告

更新时间：2026-02-20
审查范围：`backend/`、`frontend/`、`desktop/`、`docs/`、`Aelin_Page/` 以及当前可见组件/路由/服务

## 0. 本轮已落实变更（先执行）

### 0.1 已去除登录系统（可直接使用）
- 后端：`backend/app/routers/auth.py`
  - `get_current_user` 改为本地单用户模式（无 token 自动可用）。
  - 保留原 token 路径兼容，不再把无 token 视为阻断。
- 前端：`frontend/src/App.tsx`
  - 移除登录门禁，主路由直接进入 `Aelin`。
  - `/login` 自动重定向到 `/`。
- 前端：`frontend/src/components/TopBar.tsx`
  - 移除“退出登录”入口。
- 前端：移除旧登录模块
  - 删除 `frontend/src/components/Login.tsx`
  - 删除 `frontend/src/components/login/LoginPanel.tsx`
  - 删除 `frontend/src/contexts/AuthContext.tsx`
  - 删除 `frontend/src/App.test.tsx`（原测试仅验证登录门禁）

### 0.2 已完成校验
- `backend`: `pytest -q` -> `43 passed`
- `frontend`: `npx tsc --noEmit` -> 通过

## 1. 现状总览（结构健康度）

### 1.1 体量热点（高风险文件）
- 后端
  - `backend/app/routers/aelin.py`：6124 行
  - `backend/app/services/agent_memory.py`：1156 行
  - `backend/app/connectors/x.py`：1041 行
- 前端
  - `frontend/src/components/Aelin.tsx`：4911 行
  - `frontend/src/components/Dashboard.tsx`：1479 行
  - `frontend/src/api.ts`：1345 行

结论：核心能力完整，但“超大文件”已经成为维护、回归和协作的第一风险源。

### 1.2 功能面覆盖（已具备）
- 多源抓取：微博/小红书/抖音/B站/X/RSS/IMAP/Gmail/Outlook/GitHub
- Agent 对话：本地检索 + Web 检索 + 追踪建议 + 工具轨迹
- 记忆：DB + tracking + OpenViking bridge（文件化检索能力已接入）
- 多端：Web + Desktop（Electron）+ Mobile（Capacitor）

## 2. 应保留（Keep）

### 2.1 产品核心（必须保留）
- `Aelin` 主对话入口 + 工具调度（这是产品灵魂）
- 长期追踪系统（tracking targets + 自动同步 + 回报）
- Web 搜索能力（尤其时效性问题）
- 证据卡片引用（可追溯性）
- 记忆分层（事实/偏好/进行中）
- 桌面端一体化后端打包链路

### 2.2 工程核心（必须保留）
- 后端 connectors 分层
- `sync_jobs` 与并发同步框架
- `openviking_bridge`（后续 RAG/检索升级的战略资产）
- 自动化测试基线（当前 43 条）

## 3. 没必要（Can Remove / Freeze）

### 3.1 当前阶段没必要继续投入的方向
- 账号注册/登录流程（已切本地单用户）
- 面向“多人 SaaS 租户隔离”的复杂化改造
- 过重的前端多面板并行展示（会稀释 Aelin 主交互）
- 非关键平台的“全功能 UI 配置入口”堆砌

### 3.2 建议冻结而非立刻删掉
- `/api/v1/auth/*` 端点：保留兼容，但标记 deprecated
- OAuth 完整配置页：保留入口，减少默认暴露层级

## 4. 冗余项（Redundant / Debt）

### 4.1 代码冗余
- 超大单文件职责混杂
  - `frontend/src/components/Aelin.tsx`
  - `backend/app/routers/aelin.py`
- `frontend/src/api.ts` 集中式超大 API 客户端，缺乏按域拆分
- `Dashboard` 与 `Aelin` 职责边界仍有历史耦合痕迹

### 4.2 文档/目录冗余
- `docs/` 内存在大量阶段性测试文档与历史草稿混杂（可归档）
- 顶层 `tests/` 目录为空（建议删除）
- 产品文档主线应统一到 `docs/aelin-docs-foundation/`，其余转 archive

## 5. 需要调整（Adjust）

### 5.1 架构调整（最高优先）
- 后端：把 `aelin.py` 拆为 6 层
  - `chat_orchestrator`
  - `intent_planner`
  - `tool_dispatcher`
  - `citation_builder`
  - `tracking_suggestion`
  - `stream_adapter`
- 前端：把 `Aelin.tsx` 拆为 5 域
  - `conversation`（消息流）
  - `composer`（输入区/图片）
  - `tracking-layer`（追踪悬浮窗）
  - `evidence`（证据卡片）
  - `memory-view`（记忆可视化）

### 5.2 产品调整（体验）
- 默认只保留“一个主窗口”：Aelin
- Desk 能力以“工具层/面板层”嵌入，不再作为平级主界面
- 追踪信息统一由“Tracking Layer”对外展示（用户可见、可控、可回溯）

### 5.3 数据与记忆调整
- tracking 数据文件化（已在 OpenViking 方向）继续强化：
  - 用户可读
  - Agent 可写
  - 可检索
  - 可审计
- 对话短期记忆与长期追踪记忆明确分层，避免混写

### 5.4 稳定性与可运维
- 增加统一观测面：
  - sync 成功率
  - 平均抓取耗时
  - Web 命中率
  - 回答含证据率
- 给每个平台 connector 增加健康状态灯与最近错误摘要

## 6. 详细策略（分阶段）

## Phase P0（立即执行，1-2 周）
- 完成超大文件拆分（先“路由/状态/视图”切层，不做行为重写）
- 统一追踪悬浮窗模型：创建/暂停/恢复/软删除/手动执行
- 证据卡片统一跳转（外链打开 + 内部预览可切）
- 文档收敛：`docs/aelin-docs-foundation/` 作为唯一主入口

## Phase P1（增强阶段，2-4 周）
- 完成 OpenViking 文件化记忆闭环（读/写/检索/版本）
- 引入“回答优先 + 工具后置补证”策略模板
- 建立追踪策略策略集（阈值由 agent 决策，规则只做安全兜底）
- 桌面端增加“后台主动提醒中心”（可开关）

## Phase P2（产品化阶段，4-8 周）
- 统一多端派发策略（Windows 主发行，Android 为 companion）
- 对接最小 telemetry（本地优先，可匿名）
- 指标驱动迭代：以留存、日活问答、追踪复访率为核心

## 7. 组件级审查结论（简表）

| 模块 | 结论 | 说明 |
|---|---|---|
| `frontend/src/components/Aelin.tsx` | 需要调整 | 功能过强但体量过大，必须拆域 |
| `frontend/src/components/Dashboard.tsx` | 部分保留 | 作为能力层吸收进 Aelin，不做主界面 |
| `frontend/src/components/Settings.tsx` | 保留+瘦身 | 保留配置入口，减少非关键项默认展示 |
| `frontend/src/components/TopBar.tsx` | 保留 | 已去登录化，继续轻量化 |
| `backend/app/routers/aelin.py` | 需要调整 | 逻辑核心但严重耦合，优先拆分 |
| `backend/app/routers/auth.py` | 冻结/兼容 | 去登录化后仅做兼容层 |
| `backend/app/connectors/*` | 保留 | 属于产品护城河能力 |
| `backend/app/services/openviking_bridge.py` | 强化 | 未来记忆检索主轴 |
| `desktop/src/main.cjs` | 保留+加固 | 已做 Python 运行时容错，继续完善可观测性 |
| `docs/aelin-docs-foundation/*` | 保留 | 作为唯一产品文档主干 |

## 8. 建议清理清单（低风险）

- 删除空目录：`tests/`
- 将 `docs/` 中历史测试文档归档到 `docs/archive/`
- 为 `docs/` 建立 `INDEX.md`，统一入口与状态标签（draft/stable/deprecated）

## 9. 结论

Aelin 当前不是“功能不够”，而是“核心价值已成立，但结构层还在历史包袱里”。

你现在最应该做的不是继续加新功能，而是：
- 收敛主交互（Aelin first）
- 拆解巨石文件
- 统一追踪与记忆层
- 把文档和工程结构打磨成长期可迭代形态

做到以上，Aelin 会从“强 demo”跨到“可持续产品”。
