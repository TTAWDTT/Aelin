# OpenViking Integration Report (Aelin)

## 1. 报告目标

本文档说明 Aelin 中“OpenViking 风格文件记忆系统”的实现原理、运行机制、在产品中的职责与价值，以及一套可执行的测试方案。

你可以把它理解成：

- 对外：Aelin 的长期追踪记忆能力说明书
- 对内：研发和验收用的技术落地与测试手册

---

## 2. 设计目标与定位

Aelin 的目标不是做一次性检索，而是做“可持续追踪 + 可沉淀 + 可复用”的长期上下文系统。

本次实现把追踪记忆从“只在数据库里可读”升级为：

1. 追踪状态仍由数据库保证稳定性（调度、去重、状态机）
2. 追踪内容投影到文件系统（用户可读、可查、可迁移）
3. 检索优先走 OpenViking SDK（若可用），不可用时自动回退本地检索
4. Chat Agent 会直接利用该记忆参与回答
5. Agent 可自主决定把回答沉淀为 insight（长期洞察）并写回记忆

这使 Aelin 具备“Agent 时代的可写 RAG”能力。

---

## 3. 核心模块与文件

### 3.1 文件记忆桥接层

- 文件：`backend/app/services/openviking_bridge.py`
- 类：`TrackingFileMemoryBridge`

职责：

- 把追踪目标与抓取结果投影为 markdown 文件
- 提供检索接口 `search(...)`
- 提供写入洞察接口 `append_insight(...)`
- 自动尝试加载 OpenViking SDK，失败时回退本地检索

### 3.2 追踪调度层接入

- 文件：`backend/app/services/tracking_autonomy.py`

职责：

- 在追踪目标创建/更新时写 `profile.md`
- 在每次抓取后写 `snapshots/*.md`
- 在变化检测后写 `timeline/*.md`
- 在抓取失败时写失败快照

### 3.3 Aelin 路由与 Planner 接入

- 文件：`backend/app/routers/aelin.py`

职责：

- `_build_planner_tracking_snapshot(...)` 读取真实 tracking targets + 文件记忆命中
- 在聊天生成阶段把文件记忆注入模型上下文
- 新增 `insight_write` 子流程：由模型决策是否写长期洞察
- 新增 API：`GET /api/v1/aelin/tracking/file-memory/search`

### 3.4 前端展示接入

- 文件：`frontend/src/api.ts`
- 文件：`frontend/src/components/Aelin.tsx`

职责：

- 调用 `tracking/file-memory/search` 接口
- 在 Tracking 详情面板展示“文件记忆命中”卡片

---

## 4. 存储结构与数据形态

默认根目录：

- `../data/aelin_memory`（可通过环境变量覆盖）

目录结构：

- `users/{user_id}/workspaces/{workspace}/tracking/{source}/{target_hash}/`

该目录下包含：

1. `profile.md`
- 目标基本信息（canonical_id/source/workspace/config/tags/status）

2. `snapshots/*.md`
- 每次抓取的 normalized payload
- 包含抓取状态、时间、版本

3. `timeline/*.md`
- 变化事件（new/update/remove/error/recovered）
- 包含 summary 和 diff

4. `insights/*.md`
- Agent 自主沉淀的长期洞察
- 包含标题、内容、原因、置信度、来源 query

---

## 5. 检索机制（OpenViking 优先 + 本地回退）

入口：`TrackingFileMemoryBridge.search(...)`

流程：

1. 如果可加载 OpenViking SDK：
- 调用 `_search_with_openviking(...)`
- 返回结构化命中（path/title/preview/score 等）

2. 如果 SDK 不可用或执行失败：
- 自动回退 `_search_local(...)`
- 对 markdown 做轻量 lexical scoring（query 命中 + token 命中 + kind 权重）
- 返回同构结果，保证上层调用无需感知差异

这个设计保证了：

- 有 SDK 时：更强检索能力
- 无 SDK 时：功能不断档

---

## 6. Chat Agent 如何使用该能力

### 6.1 Planner 阶段

`_build_planner_tracking_snapshot(...)` 会输出：

- `active_items`：真实 tracking targets（workspace scoped）
- `matched_items`：与当前 query 相关的追踪项
- `matched_file_items`：文件记忆命中

### 6.2 回答阶段

在 `_aelin_chat_impl(...)` 中：

1. 合并 local/web/file-memory 三类上下文
2. 将 `file_memory_lines` 注入用户消息上下文
3. 模型在回答中可直接引用这些长期线索

### 6.3 Insight 写入阶段（关键）

`_maybe_write_tracking_insight(...)` 由模型自主决策：

- 输入：query、answer、tracking snapshot、file memory hits
- 模型输出 JSON：
  - `should_write`
  - `confidence`
  - `title`
  - `markdown`
  - `reason`
- 若通过：调用 `append_insight(...)` 写入 `insights/*.md`
- 并向前端返回 action（可回到 tracking 查看）

这一步就是“从回答到长期记忆沉淀”的闭环。

---

## 7. 该功能在产品中的角色

它在 Aelin 中承担 3 个核心角色：

1. 长期记忆底座
- 把追踪结果变成可持久、可解释、可检索的知识层

2. 对话增强器
- 让 Chat 不再只依赖即时搜索，而能复用历史追踪脉络

3. 自主沉淀引擎
- 让 Agent 把“有价值结论”变成可复用洞察，而不是回答后即丢失

最终效果：Aelin 会“越用越懂你追踪的世界”。

---

## 8. 配置项说明

文件：`backend/app/settings.py`

- `openviking_enabled` (bool, default `True`)
- `openviking_data_dir` (str, default `../data/aelin_memory`)
- `openviking_query_limit` (int, default `8`)

环境变量前缀为 `MERCURYDESK_`，例如：

- `MERCURYDESK_OPENVIKING_ENABLED=true`
- `MERCURYDESK_OPENVIKING_DATA_DIR=../data/aelin_memory`
- `MERCURYDESK_OPENVIKING_QUERY_LIMIT=12`

---

## 9. 详细测试方案

以下方案分为 4 层：编译/单测、API 集成、端到端行为、异常与回退。

## 9.1 测试准备

1. 依赖安装

```powershell
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

2. 确认配置

- 后端 `.env` 中至少保证数据库与基础配置可启动
- 可选安装 OpenViking SDK（若你要验证 SDK 路径）

3. 启动服务

```powershell
# backend
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# frontend (new terminal)
cd frontend
npm run dev
```

---

## 9.2 自动化回归（必须先过）

1. 后端测试

```powershell
cd backend
pytest -q
```

预期：全部通过。

2. 前端类型检查

```powershell
cd frontend
npx tsc --noEmit
```

预期：0 error。

3. 前端单测

```powershell
cd frontend
npm test
```

预期：vitest 全通过。

---

## 9.3 API 集成测试（文件记忆链路）

### 用例 A：追踪写入是否落地到文件

步骤：

1. 在 Aelin 对话中触发一个 tracking target（或调用 `track/confirm`）
2. 执行一次目标 run（或等待 scheduler）
3. 检查目录：`../data/aelin_memory/users/{uid}/workspaces/{ws}/tracking/...`

预期：

- 有 `profile.md`
- 有 `snapshots/*.md`
- 有 `timeline/*.md`（出现变化时）

### 用例 B：文件记忆检索接口

请求：`GET /api/v1/aelin/tracking/file-memory/search?workspace=default&query=你的关键词&limit=12`

预期：

- 返回 `workspace/total/items/generated_at`
- `items` 内字段完整：`path/title/preview/score/canonical_id/target/source/kind`

### 用例 C：Planner 快照含文件命中

步骤：

- 发起一次 Aelin chat（`/api/v1/aelin/chat`）
- 观察后端 trace 与行为

预期：

- planner 能读到 `matched_file_items`
- message_hub trace 中包含 file memory 合并信息

---

## 9.4 端到端行为测试（用户视角）

### 用例 D：Chat 利用历史追踪记忆回答

步骤：

1. 先让系统追踪一个主题几轮（保证已有快照）
2. 在 chat 提问同主题问题

预期：

- 回答不是只给“请手动检索”，而是能直接引用长期记忆线索
- Tracking 详情“文件记忆命中”能看到对应条目

### 用例 E：自主洞察写入

步骤：

1. 提问一个有明确追踪上下文的问题
2. 观察本轮 chat 结束后 action 与文件系统

预期：

- trace 出现 `insight_write`（completed 或 skipped）
- 若 completed：`insights/*.md` 新增文件
- 响应 action 中出现“已沉淀长期洞察”（open_tracking）

### 用例 F：前端展示一致性

步骤：

1. 打开 Tracking 详情
2. 查看“变化流/快照/文件记忆命中”

预期：

- 文件记忆区块不报错
- 卡片显示路径、分数、来源、预览
- 点击“复制路径”可复制成功

---

## 9.5 回退与异常测试

### 用例 G：无 OpenViking SDK 回退

步骤：

- 卸载或禁用 OpenViking 包（或在无包环境）
- 重复检索流程

预期：

- 系统不报错
- 自动走本地检索，接口可正常返回结果

### 用例 H：关闭文件记忆

步骤：

- `MERCURYDESK_OPENVIKING_ENABLED=false`
- 重启后端

预期：

- 文件写入与检索停用
- 核心 chat 与 tracking 主流程仍正常运行

### 用例 I：路径不可写

步骤：

- 指向无权限目录作为 `openviking_data_dir`

预期：

- 后端记录 warning
- 主业务不中断（DB 路径仍可工作）

---

## 9.6 验收标准（建议）

满足以下 8 项即可认为上线可用：

1. pytest / tsc / vitest 全绿
2. profile/snapshot/timeline 文件均可产出
3. file-memory search API 稳定返回
4. planner 能利用 matched_file_items
5. chat 能基于文件记忆给出可用答案
6. insight_write 流程可触发并落盘 insights
7. 前端 tracking 详情可视化正常
8. 无 SDK 时自动回退不影响可用性

---

## 10. 当前边界与下一步建议

当前边界：

- OpenViking SDK 采用“可选接入 + 回退”模式，不强依赖
- insight 写入为每轮后置决策，不做跨轮批处理

建议下一步：

1. 增加 insight 写入去重策略（避免同义重复洞察）
2. 增加按 target 的 insight 聚合视图
3. 将 file-memory 命中纳入引用卡片（可直接跳本地/远端预览）
4. 若你后续接入 RAG 索引器，可将 `insights/*.md` 作为高权重语料层

---

## 11. 一句话总结

Aelin 现在的 OpenViking 风格能力，已经从“追踪数据记录”升级为“可检索、可解释、可写入、可持续进化的长期记忆系统”，并且已经进入 chat 主闭环。
