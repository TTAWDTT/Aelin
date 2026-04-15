# DeepAgents-Native Structure Refactor Phase 1 Plan

**Goal:** 在不改变 Aelin 当前 DeepAgents-native 主链行为的前提下，完成第一轮“结构瘦身”，把最厚的组装层、投影层、桌面运行时拆成更清晰的模块边界，为后续继续贴近 DeepAgents / LangChain 的组织方式打基础。

**Scope:** 只做 Phase 1。重点是“薄入口化”和“稳定边界拆分”，不做功能扩展，不改主 API 协议，不重写产品交互。

**Architecture target:** 保持当前官方主链不变：

- frontend `useStream(...)`
- LangGraph Agent Server `/assistants` `/threads` `/runs/stream`
- `backend/agent_server/graph.py`
- DeepAgents graph assembly

但是把当前过厚的文件拆成更清晰的组装模块、投影模块和适配模块。

**Non-goals:**

- 不引入新的聊天协议
- 不恢复旧 Aelin loop / SSE 兼容层
- 不修改 `sessionId == threadId`
- 不把额外隐藏上下文重新塞回主链
- 不把仓库改造成 LangChain 那种多包 monorepo

---

## 1. Phase 1 原则

### 1.1 允许做的事

- 拆文件
- 搬函数
- 调整 import 边界
- 增加更清楚的模块命名
- 增加针对新模块边界的测试
- 补结构文档

### 1.2 这一阶段不要做的事

- 不重写主要算法
- 不重写 tool policy 语义
- 不改前后端协议字段
- 不改 DeepAgents 的能力集合
- 不改 desktop plugin API path
- 不改用户可见行为文案，除非拆分中顺手修正明显错误

### 1.3 Phase 1 完成标准

完成后应该达到：

1. 主入口文件显著变薄
2. 至少 4 个超大热点文件被拆成边界清晰的子模块
3. 测试仍然覆盖关键主链
4. 主聊天链行为与桌面主能力不发生回归

---

## 2. 这次要拆的重点热点

当前热点：

- `backend/app/services/deepagents/deepagents_graph.py`
- `backend/app/services/deepagents/tool_runtime.py`
- `frontend/src/features/chat/executionStreamUtils.ts`
- `frontend/src/features/chat/hooks/useChatStream.ts`
- `desktop/src/aelin_desktop_runtime.cjs`

这些文件的问题不是“写错了”，而是职责已经叠到一个文件里，后续继续演进会越来越难维护。

---

## 3. 实施顺序总览

建议按这个顺序推进：

1. 后端 DeepAgents 装配层拆分
2. 后端 tool runtime 拆分
3. 前端 runtime projection 拆分
4. 前端 stream orchestration 收缩
5. Desktop runtime 拆分
6. 补测试与结构文档

原因：

- 后端装配层是全链核心，最先决定后面命名和边界
- 前端应跟着“runtime contract”拆，而不是先自己改
- Desktop 可以最后拆，因为它对主聊天链是外围系统

---

## 4. Task 1: 拆分后端 DeepAgents 装配层

**目标：** 让 `build_chat_agent()` 回到“装配函数”角色，而不是一个巨型综合模块。

**当前文件：**

- `backend/app/services/deepagents/deepagents_graph.py`

**目标文件结构：**

```text
backend/app/services/deepagents/
  assembly/
    __init__.py
    graph.py
    prompt.py
    tool_registry.py
    backend_factory.py
    skill_mounts.py
    output_mapping.py
```

### Step 1: 抽出 prompt 构造

把这些逻辑移到 `assembly/prompt.py`：

- `_current_date_context`
- `_tool_description`
- `_build_system_prompt`

**要求：**

- prompt 文本内容不变
- 对 `workspace`、`/workspace`、`/outputs` 的约束不变

### Step 2: 抽出 skill mount 逻辑

把这些逻辑移到 `assembly/skill_mounts.py`：

- `SkillMountSnapshot`
- `_build_skill_mount_snapshot`
- `_get_skill_mount_snapshot`

**要求：**

- `backend/deepagents_skills/*/SKILL.md` 的挂载语义完全不变
- `AELIN_DEEPAGENTS_EXTRA_SKILLS_DIR` 语义不变

### Step 3: 抽出 backend factory 逻辑

把这些逻辑移到 `assembly/backend_factory.py`：

- `_backend_root`
- `_build_agent_backend_factory`
- `/workspace`、`/outputs`、`/skills/*` 挂载逻辑

**要求：**

- `ManagedCompositeBackend` 使用方式不变
- write_file 限制和 delivery path 映射不变

### Step 4: 抽出 tool registry 逻辑

把这些逻辑移到 `assembly/tool_registry.py`：

- 所有 `*ToolInput` schema
- `build_chat_tools`
- `_invoke_tool`
- `_map_tool_runs`

如果 `_invoke_tool` 与 policy / executor 耦合太深，可先只迁移到 `tool_registry.py`，下一任务再继续拆。

**要求：**

- 已注册工具集合完全不变
- `execute` 是否暴露仍由 `desktop_plugin_execute_enabled` 控制
- tool run summary、status、latency 语义不变

### Step 5: 抽出 output mapping

把这些逻辑移到 `assembly/output_mapping.py`：

- `_parse_capabilities_file`
- `_loop_result`
- `DeepAgentsToolRun`
- `DeepAgentsLoopResult`

**要求：**

- `run_deepagents_loop()` 对外返回结构不变

### Step 6: 收缩主装配文件

最终 `deepagents_graph.py` 应只保留：

- `build_chat_agent`
- `run_deepagents_loop`
- 少量必要的 glue code

如果拆完后 `deepagents_graph.py` 仍超过约 350-450 行，说明拆分还不够彻底。

### Step 7: 验证

运行最小相关测试：

```bash
cd backend
pytest -q backend/tests/test_agent_server_graph.py
pytest -q backend/tests/test_deepagents_prompt.py
pytest -q backend/tests/test_deepagents_run_constraints.py
```

如果这些测试名与当前 pytest root 解析不兼容，就用仓库里现有可运行路径形式执行。

**完成标准：**

- `deepagents_graph.py` 明显缩小
- 新模块命名与职责清晰
- 原有测试通过

---

## 5. Task 2: 拆分后端 tool runtime

**目标：** 把“上下文定义”“工具执行器”“策略限制器”拆开。

**当前文件：**

- `backend/app/services/deepagents/tool_runtime.py`

**目标文件结构：**

```text
backend/app/services/deepagents/tools/
  __init__.py
  runtime_context.py
  executor.py
  policy.py
```

### Step 1: 抽出 runtime context

迁移到 `tools/runtime_context.py`：

- `ToolRuntimeContext`
- `normalize_workspace`
- `build_tool_runtime_context`

**要求：**

- `resolve_deepagents_runtime()` 调用方式保持稳定

### Step 2: 抽出 executor

迁移到 `tools/executor.py`：

- `_ensure_tool_executor`
- `_acquire_tool_executor_slot`
- `_submit_tool_future`
- `_reset_tool_executor_for_tests`

**要求：**

- 线程池数量、semaphore、超时控制行为不变

### Step 3: 抽出 policy

迁移到 `tools/policy.py`：

- `ToolPolicyDecision`
- `ToolPolicyUsage`
- `ToolCallLimiter`
- `build_tool_signature`
- `result_has_progress`
- `classify_tool_call`
- `_invalid_reason`

**要求：**

- duplicate call / no progress / stalled / write tool 限制语义不变

### Step 4: 统一导出兼容入口

在 `deepagents/tool_runtime.py` 临时保留兼容 re-export，避免第一轮拆分时到处大改 import。

Phase 1 的重点是降耦合，不是一次性清空旧路径。

### Step 5: 验证

运行最小相关测试：

```bash
cd backend
pytest -q backend/tests/test_aelin_tool_policy.py
pytest -q backend/tests/test_deepagents_run_constraints.py
pytest -q backend/tests/test_aelin_tools.py
```

**完成标准：**

- context / executor / policy 三层已独立
- 主链 import 不混乱
- tool policy 行为无变化

---

## 6. Task 3: 拆分前端 execution projection

**目标：** `executionStreamUtils.ts` 不再承担所有 runtime 投影职责。

**当前文件：**

- `frontend/src/features/chat/executionStreamUtils.ts`

**目标文件结构：**

```text
frontend/src/features/chat/runtime/
  streamTypes.ts
  messageRuntime.ts
  toolProjection.ts
  subagentProjection.ts
  graphProjection.ts
  todoProjection.ts
  executionRuntime.ts
```

### Step 1: 抽出共享类型

迁移到 `runtime/streamTypes.ts`：

- `ChatStreamState`
- `ChatRuntimeStream`
- `Execution*` 相关类型

### Step 2: 抽出消息级 runtime 行

迁移到 `runtime/messageRuntime.ts`：

- `getMessageRuntimeRows`
- 元数据读取
- messageId 解析

### Step 3: 抽出 tool / artifact 投影

迁移到 `runtime/toolProjection.ts`：

- tool call 去重
- tool result preview
- artifact 抽取

### Step 4: 抽出 subagent / todo / graph 逻辑

分别迁移：

- `subagentProjection.ts`
- `todoProjection.ts`
- `graphProjection.ts`

### Step 5: 建一个薄组合入口

`runtime/executionRuntime.ts` 只保留：

- `getExecutionRuntime`
- `getMessageToolCallMap`
- `summarizeExecutionStatus`

它应该像 orchestrator，而不是大一统 util。

### Step 6: 验证

运行：

```bash
cd frontend
npm run test:unit
```

至少重点关注：

- `executionStreamUtils.test.ts`
- `artifactUtils.test.ts`

如果有必要，同步微调测试 import。

**完成标准：**

- 原 700+ 行 util 被拆成多个纯函数模块
- `getExecutionRuntime()` 的对外行为不变

---

## 7. Task 4: 收缩前端 `useChatStream`

**目标：** 让 `useChatStream.ts` 回到 orchestration hook 的职责。

**当前文件：**

- `frontend/src/features/chat/hooks/useChatStream.ts`

**目标文件结构：**

```text
frontend/src/features/chat/runtime/
  sessionProjection.ts
  assistantRuntime.ts
frontend/src/features/chat/hooks/
  useChatStream.ts
  useChatThread.ts
  useProjectedMessages.ts
```

### Step 1: 抽出 assistant/thread bootstrap

迁移逻辑：

- `findAssistantId`
- `fetchAssistantGraph`
- `ensureThreadReady`
- active session -> thread 切换

如果已有 `chatStreamRuntime.ts`，则继续把职责收拢到那里，而不是再堆回 hook。

### Step 2: 抽出消息投影

迁移：

- `projectRuntimeMessages`
- `extractMessageText`
- `extractMessageImages`
- persistence signature

### Step 3: hook 只做 orchestration

最终 `useChatStream.ts` 主要保留：

- submit
- stop
- upload / capture 组合调用
- status / error 状态协调

### Step 4: 验证

运行：

```bash
cd frontend
npm run test:unit
npm run build
```

**完成标准：**

- `useChatStream.ts` 不再包含大量 projector 细节
- 构建与测试通过

---

## 8. Task 5: 拆分 Desktop runtime

**目标：** 保持 `main.cjs` 极薄，同时把 `aelin_desktop_runtime.cjs` 从“单文件子系统”拆成 runtime 目录。

**当前文件：**

- `desktop/src/aelin_desktop_runtime.cjs`

**目标文件结构：**

```text
desktop/src/runtime/
  bootstrap.cjs
  backend.cjs
  frontend.cjs
  plugin_api.cjs
  capture.cjs
  execute.cjs
  windows.cjs
  tray.cjs
  ipc.cjs
  pet/
    state.cjs
    layout.cjs
    menu.cjs
```

### Step 1: 先拆无争议模块

优先拆出：

- `backend.cjs`
  - `startBackend`
  - Python 选择与 backend 进程引导
- `frontend.cjs`
  - `startFrontendDev`
  - `startFrontendServer`
- `plugin_api.cjs`
  - express app
  - `/v1/device/screen/capture`
  - `/v1/desktop/url/open`
  - `/v1/desktop/path/open`
  - `/v1/desktop/command/execute`

### Step 2: 拆截图与命令执行

迁移到：

- `capture.cjs`
- `execute.cjs`

这样 desktop plugin API 只做路由，具体能力在独立模块里。

### Step 3: 拆窗口与菜单

迁移到：

- `windows.cjs`
- `tray.cjs`
- `ipc.cjs`

### Step 4: pet 子系统最后拆

原因：

- pet 行为逻辑多
- 与状态 ticker、布局、菜单、情绪计算交织较多

Phase 1 不要求把 pet 完全重构到理想状态，但至少要把 runtime 级别的 bootstrap 和 plugin API 抽出去。

### Step 5: 验证

运行：

```bash
cd desktop
find src scripts -type f -name "*.cjs" -print0 | xargs -0 -n1 node --check
```

如果桌面端有更轻量的本地 smoke 命令，也一并运行。

**完成标准：**

- `aelin_desktop_runtime.cjs` 明显瘦身
- backend/frontend/plugin_api/capture 不再堆在一个文件里

---

## 9. Task 6: 测试与文档收尾

**目标：** 在结构调整后，补足“模块边界说明”和最小回归验证。

### Step 1: 后端最小回归

```bash
cd backend
pytest -q
```

如果全量过重，至少保证：

- agent server graph
- auth
- tool policy
- deepagents prompt
- run constraints
- remote control
- aelin device

这些与拆分相关的测试可运行。

### Step 2: 前端最小回归

```bash
cd frontend
npm run test:unit
npm run build
```

### Step 3: Desktop 静态检查

```bash
cd desktop
find src scripts -type f -name "*.cjs" -print0 | xargs -0 -n1 node --check
```

### Step 4: 补一个 runtime 说明文档

新增或更新一份短文档，说明：

- backend runtime assembly 的入口在哪
- frontend runtime projection 的入口在哪
- desktop runtime 入口在哪

避免后续再次把新逻辑堆回入口文件。

---

## 10. 风险与防回归策略

### 10.1 最大风险

1. 拆文件后 import 环依赖增加
2. 前端 projector 拆分后 message/tool/subagent 关联出错
3. Desktop 拆分时闭包变量和全局状态断裂

### 10.2 防回归策略

1. 第一轮允许保留兼容 re-export
2. 先抽纯函数，再抽状态逻辑
3. Desktop 先拆“无 UI 争议模块”，最后拆 pet
4. 每完成一个任务就运行对应最小测试，不要攒到最后一起炸

---

## 11. 建议的提交策略

不要一个大提交做完整个 Phase 1。

建议拆成 5 个 PR / commit 组：

1. `refactor(deepagents): split graph assembly helpers`
2. `refactor(deepagents): split tool runtime context executor policy`
3. `refactor(frontend): split execution runtime projection`
4. `refactor(frontend): shrink chat stream orchestration hook`
5. `refactor(desktop): split runtime bootstrap plugin and capture modules`

这样回归点更清楚，也更容易 review。

---

## 12. Phase 1 完成后的理想状态

完成后，Aelin 应达到：

- `backend/agent_server/graph.py` 是真正的薄入口
- DeepAgents 装配逻辑已模块化
- tool policy / executor / runtime context 已分离
- 前端 execution runtime 是独立层
- `useChatStream` 是 orchestration hook，而不是大一统实现
- Desktop runtime 已从单文件子系统退回为模块化运行时

这时再进入 Phase 2，去继续拉开：

- capability vs integration
- runtime vs bridge
- product API vs external adapter

才会比较稳。

---

## 13. 本计划与上一份调研的关系

这份文档是对下列调研文档的实施版收敛：

- `docs/aelin_deepagents_langchain_structure_review_20260402.md`

如果后续执行中发现某个模块拆分成本过高，应优先守住两个目标：

1. 主入口变薄
2. 稳定边界可单测

只要这两个目标守住，Phase 1 就是成功的。
