# Aelin 向 DeepAgents / LangChain 靠拢的结构调研与改造建议

日期：2026-04-02

## 1. 背景

这份文档的目标不是讨论「Aelin 要不要继续使用 DeepAgents / LangGraph」，而是回答另一个更具体的问题：

- 如果 Aelin 继续大幅效仿 `deepagents`
- 并且希望代码结构比现在更清晰
- 那么应该学什么，不应该盲目照搬什么

我这次对照阅读了：

- `langchain-ai/deepagents`（本地调研快照：`06881cc`）
- `langchain-ai/langgraph`（本地调研快照：`ee0566d`）
- `langchain-ai/langchain`（本地调研快照：`b3dff4a`）
- LangChain / LangGraph / Deep Agents 官方文档

同时也回看了 Aelin 当前主链上的核心实现：

- `backend/agent_server/graph.py`
- `backend/app/services/deepagents/deepagents_graph.py`
- `backend/app/services/deepagents/tool_runtime.py`
- `frontend/src/features/chat/hooks/useChatStream.ts`
- `frontend/src/features/chat/executionStreamUtils.ts`
- `desktop/src/aelin_desktop_runtime.cjs`

## 2. 结论先行

我的核心判断有 4 条：

1. Aelin 的运行链路方向已经对了，但代码组织仍然偏「产品项目式 services 堆叠」，还没有完全进入 `deepagents/langchain` 那种「组合入口很薄，能力按稳定边界分层」的状态。
2. 真正值得学习的不是 LangChain 仓库的“大而全”，而是它的边界意识：
   - `core`
   - `prebuilt`
   - `sdk`
   - `partners`
   - `examples`
   - `tests`
   各自职责很清楚。
3. Aelin 当前最需要动刀的不是前端 UI 样式，而是 3 个结构热点：
   - 后端 DeepAgents 装配层过厚
   - 前端流式投影层过厚
   - Desktop runtime 单文件过厚
4. 不建议把 Aelin 改造成 LangChain 那种多发行包 monorepo；建议学习它们的“分层原则”，但继续保留 Aelin 作为产品仓库的组织方式。

一句话总结：

> Aelin 应该学习 DeepAgents 的“组合式 runtime”和 LangChain 的“稳定包边界”，而不是学习它们的仓库体量。

## 3. 官方仓库里最值得借鉴的模式

### 3.1 DeepAgents：把复杂度压进 middleware / backend，而不是压进入口文件

`deepagents` 的公开入口非常小：

- `libs/deepagents/deepagents/__init__.py`
- `libs/deepagents/deepagents/graph.py`

它最重要的设计不是“功能很多”，而是：

- `graph.py` 只做组装
- `backends/*` 处理文件系统 / sandbox / state 等后端差异
- `middleware/*` 处理 skills / memory / filesystem / summarization / subagents
- `tests/unit_tests`、`tests/integration_tests`、`tests/benchmarks` 明确拆开

对 Aelin 的启发：

- `build_chat_agent()` 应该更像 DeepAgents 的 `create_deep_agent()`：只负责拼装，不负责承载大量产品细节
- 工具策略、执行器、路径映射、能力注入、提示词拼接、运行结果投影，不该继续堆在一个文件里

### 3.2 LangGraph：把“底层 runtime”、“预制能力”、“SDK”、“CLI”拆成独立层

`langgraph` 仓库最有价值的不是 `graph` 本身，而是它把不同抽象层清楚拆开：

- `libs/langgraph`: 核心 runtime
- `libs/prebuilt`: 高层预制 agent / tool node
- `libs/sdk-py`: 与 LangGraph API 交互的 Python SDK
- `libs/cli`: CLI 与 monorepo 示例
- `libs/checkpoint*`: persistence / checkpoint 相关实现

这非常值得 Aelin 学：

- 核心运行时层
- 产品 API 层
- 桌面桥接层
- 前端 SDK / stream adapter 层

这些最好不要继续混成一个“services 大杂烩”。

### 3.3 LangChain：用“core / v1 / partners / standard-tests”保护长期演进

`langchain` 仓库里最重要的结构信号是：

- `libs/core`: 真正稳定的核心抽象
- `libs/langchain_v1`: 面向应用层的 agent API
- `libs/partners/*`: 各厂商集成单独分区
- `libs/standard-tests`: 把标准测试也做成独立模块

这说明一件事：

> 演进快的部分和稳定边界，必须分开。

对 Aelin 最直接的映射是：

- DeepAgents runtime 组装是“稳定边界”
- Desktop plugin / Google Workspace CLI / Web Search provider 是“易变集成”
- Remote control / bot bridge / legacy sync adapter 是“桥接层”

现在 Aelin 还没有把这三类边界完全拉开。

### 3.4 官方文档反复强调：上下文策略、工具选择、状态扩展，应尽量走 middleware / context schema

官方文档中反复出现的模式包括：

- `create_agent(..., middleware=[...])`
- 通过 `context_schema` 注入运行时上下文
- 通过 middleware 做动态工具过滤、动态 prompt、summarization、context editing
- 明确记录“传了什么上下文、为什么传”

对 Aelin 的含义很直接：

- 不要继续把更多策略往一个超大 system prompt 里堆
- 不要让产品逻辑偷偷从多个入口向 runtime 注入隐式上下文
- 能变成显式 runtime/context/tool contract 的，就不要继续藏在胶水代码里

## 4. Aelin 当前的优点

Aelin 不是从零开始乱的。相反，当前结构已经有几件事做得很好：

### 4.1 主聊天链路已经对齐官方模型

当前主路径已经是：

- 前端 `useStream(...)`
- Agent Server `/assistants` `/threads` `/runs/stream`
- `backend/agent_server/graph.py`
- `backend/app/services/deepagents/deepagents_graph.py`

这非常重要，说明你已经摆脱了旧自定义 SSE 协议。

### 4.2 记忆边界很清楚

当前你已经把长期记忆压回 `/memory/AGENTS.md`，这和 DeepAgents 的 file-based memory 思路是一致的。

### 4.3 产品壳已经相对收敛

后端产品路由已经大致收敛到：

- `/api/v1/agent/*`
- `/api/v1/attachments/*`
- `/api/v1/aelin/device/*`
- `/api/v1/aelin/remote-control/*`

这说明你已经在守住“产品壳”和“agent runtime”的边界。

### 4.4 `main.cjs` 已经是薄入口

Desktop 入口文件现在已经是正确方向，只是运行时本体仍然过大。

## 5. Aelin 当前最明显的结构问题

下面这些不是“代码写得差”，而是“下一阶段该继续拆边界了”。

### 5.1 后端 DeepAgents 装配层过厚

当前几个核心文件的体量：

- `backend/app/services/deepagents/deepagents_graph.py`: 1121 行
- `backend/app/services/deepagents/tool_runtime.py`: 491 行
- `backend/app/services/device/device_center.py`: 314 行

尤其 `deepagents_graph.py` 现在同时承担了：

- system prompt 组织
- tool schema 定义
- tool 注册
- tool 调用记录
- skill mount
- memory mount
- backend factory
- invoke payload 组装
- loop result 投影

这和 `deepagents` 官方仓库最不同的地方在于：

- DeepAgents 把“复杂度”拆进了 `middleware/*` 和 `backends/*`
- Aelin 还把“复杂度”留在装配文件里

### 5.2 `tool_runtime.py` 还在混合 3 层职责

当前它至少同时做了：

- runtime context 定义
- executor / semaphore / future 管理
- tool policy / signature / duplicate call 限制

这三个东西应该拆开，因为它们变化速度不一样：

- context contract：稳定
- executor implementation：中等变化
- policy heuristic：高变化

### 5.3 设备能力层同时混合了“业务语义”和“桌面插件传输语义”

`backend/app/services/device/device_center.py` 里既知道：

- Aelin 需要的业务动作
- Desktop plugin 的 HTTP path
- 错误码归一化方式
- screenshot 细节

这意味着它既是 capability service，又是 integration adapter。

更清晰的做法应该是：

- `capability` 只表达“我要截图/打开 URL/执行命令”
- `adapter` 才负责“去请求本地 desktop plugin”

### 5.4 前端 runtime projection 层过厚

当前几个核心文件的体量：

- `frontend/src/features/chat/executionStreamUtils.ts`: 771 行
- `frontend/src/features/chat/hooks/useChatStream.ts`: 570 行

这两个文件现在已经不是普通 hook / util 了，而是：

- stream adapter
- runtime state projector
- message projector
- execution graph projector
- artifact projector
- persistence coordinator

它们功能上没错，但结构上已经到了该拆的时候。

### 5.5 Desktop runtime 仍然是显著单点热点

`desktop/src/aelin_desktop_runtime.cjs` 当前约 4525 行。

虽然 `main.cjs` 已经薄了，但这个 runtime 文件仍然同时承载：

- Electron app bootstrap
- backend/frontend 进程管理
- Express proxy
- tray/menu
- pet window
- IPC
- 截图
- 本地路径打开
- 执行命令
- plugin API server

这已经不是“一个运行时模块”，而是“一整个桌面子系统”。

## 6. 我建议 Aelin 学什么，不学什么

### 6.1 应该学的

- 学 DeepAgents 的“组合入口极薄”
- 学 DeepAgents 的“能力通过 middleware / backend / protocol 分层”
- 学 LangGraph 的“core / prebuilt / sdk / cli 分层”
- 学 LangChain 的“stable core 与 fast-moving integrations 分离”
- 学官方文档强调的“context strategy 显式化”

### 6.2 不应该学的

- 不要把 Aelin 也拆成一堆可以单独发版的 Python package
- 不要为了“像 LangChain”而引入过度工程化目录
- 不要为了抽象而抽象，把本来很近的产品代码拆得四分五裂

最合理的目标不是“像官方仓库一样大”，而是：

> 在 Aelin 这个产品仓库里，拥有官方仓库级别的边界清晰度。

## 7. 建议的目标结构

下面是我认为比较适合 Aelin 的方向。

### 7.1 Backend 目标结构

建议把 `backend/app/services/deepagents` 重组为一个更明确的 runtime 包：

```text
backend/app/
  agent_runtime/
    assembly/
      graph.py
      prompt.py
      tool_registry.py
      skill_mounts.py
      memory_mounts.py
      backend_factory.py
      cache.py
    context/
      run_context.py
      runtime_resolver.py
      input_mapping.py
      output_mapping.py
    tools/
      contracts.py
      policy.py
      executor.py
      runtime_context.py
      registry.py
    delivery/
      delivery_paths.py
      managed_backend.py
    bridges/
      remote_control_sync_bridge.py

  capabilities/
    web/
    attachments/
    google_workspace/
    device/
    artifacts/

  integrations/
    llm/
    desktop_plugin/
    google_workspace_cli/
    web_search/
```

这个结构的核心思想是：

- `agent_runtime`: DeepAgents 装配与运行时边界
- `capabilities`: Aelin 真实业务能力
- `integrations`: 外部系统 / 外部进程 / 外部协议适配

#### 最关键的 5 个拆分动作

1. 把 `deepagents_graph.py` 拆成：
   - `assembly/graph.py`
   - `assembly/prompt.py`
   - `assembly/tool_registry.py`
   - `assembly/backend_factory.py`
   - `context/output_mapping.py`
2. 把 `tool_runtime.py` 拆成：
   - `tools/runtime_context.py`
   - `tools/executor.py`
   - `tools/policy.py`
3. 把 `device_center.py` 拆成：
   - `capabilities/device/service.py`
   - `integrations/desktop_plugin/client.py`
4. 把 `remote_control_chat_adapter.py` 明确标成 bridge，不再放在主 runtime 路径里
5. 让 `backend/agent_server/graph.py` 只做：
   - 解析 runtime
   - 查缓存
   - 调用 runtime assembly

### 7.2 Frontend 目标结构

建议保留 feature-first，但把 chat feature 内部再分层：

```text
frontend/src/features/chat/
  runtime/
    agentServer.ts
    threadRuntime.ts
    messageProjection.ts
    executionProjection.ts
    artifactProjection.ts
  model/
    chatTypes.ts
    executionTypes.ts
  hooks/
    useChatStream.ts
    useChatSession.ts
    useExecutionRuntime.ts
  stores/
    chatStore.ts
    executionPaneStore.ts
  components/
    ...
```

这里最重要的是：

- `useChatStream.ts` 应该退回“组合 hook”
- `executionStreamUtils.ts` 应该被拆成多个 projector
- `artifact` 逻辑不要继续横切在多个 util 里

#### 最关键的 3 个拆分动作

1. `useChatStream.ts` 只保留：
   - assistant/thread bootstrap
   - submit/stop orchestration
   - status coordination
2. 把 runtime message projection 单独拆出
3. 把 execution graph / lanes / tool calls / subagents / todos 的推导拆成多个纯函数模块

### 7.3 Desktop 目标结构

建议把 `desktop/src/aelin_desktop_runtime.cjs` 拆成一个 runtime 目录：

```text
desktop/src/runtime/
  bootstrap.cjs
  backend.cjs
  frontend.cjs
  windows.cjs
  tray.cjs
  ipc.cjs
  plugin_api.cjs
  capture.cjs
  execute.cjs
  pet/
    state.cjs
    layout.cjs
    emotion.cjs
    menu.cjs
```

建议保留：

- `main.cjs` 继续只做入口

优先拆出的模块应该是：

1. backend/frontend process bootstrap
2. plugin API server
3. capture / execute
4. pet window / tray / IPC

原因很简单：

- 这些模块之间的变化频率不同
- 现在都堆在 4525 行里，回归成本太高

## 8. 测试结构也应该顺手调整

官方仓库一个非常值得学的点，是测试按“语义层级”而不是按历史堆放。

建议 Aelin 后端测试至少分成：

```text
backend/tests/
  unit/
    agent_runtime/
    capabilities/
    integrations/
  contract/
    api/
    tools/
  integration/
    agent_server/
    deepagents_runtime/
    desktop_bridge/
```

当前测试文件虽然已经不少，但还是偏扁平，随着 runtime 继续演进，定位成本会越来越高。

## 9. 我最推荐的分阶段迁移顺序

### Phase 1：只做“薄入口化”，不改行为

目标：

- 不改任何 API 合同
- 不改主运行逻辑
- 只拆出超大文件里的稳定子模块

优先项：

- `deepagents_graph.py`
- `tool_runtime.py`
- `executionStreamUtils.ts`
- `aelin_desktop_runtime.cjs`

这是性价比最高的一步。

### Phase 2：拉开 runtime / capability / integration 边界

目标：

- 让产品能力和外部系统适配分开
- 让 graph 装配不再依赖具体 HTTP / shell / plugin 细节

优先项：

- `device_center.py` 拆 capability + desktop plugin adapter
- `tools_execute.py` / `tools_present_files.py` 背后的集成边界明确化
- `google_workspace` / `web_search` 适配层单独化

### Phase 3：清理 bridge 和 legacy wrapper

目标：

- 把“主链 runtime”
- “产品 API”
- “桥接入口”

彻底分开。

优先项：

- sync remote control bridge
- bot adapters
- 任何非主聊天链路的薄包装器

### Phase 4：补结构文档和结构测试

目标：

- 把新的组织原则写下来
- 避免后续再次回到“大文件胶水”

建议补：

- runtime package readme
- tool contract readme
- frontend stream projection readme
- desktop runtime module map

## 10. 我认为最值得立刻执行的具体修改

如果只允许我选 6 件事，我会建议你先做这 6 件：

1. 把 `backend/app/services/deepagents/deepagents_graph.py` 拆成 5 个文件，保留一个薄的 `build_chat_agent()` 入口。
2. 把 `backend/app/services/deepagents/tool_runtime.py` 拆成 `context / executor / policy` 三块。
3. 把 `backend/app/services/device/device_center.py` 改成 capability 层，另建 desktop plugin adapter。
4. 把 `frontend/src/features/chat/executionStreamUtils.ts` 拆成 execution projector 子模块。
5. 把 `frontend/src/features/chat/hooks/useChatStream.ts` 收缩成 orchestration hook，不再继续承担全部投影逻辑。
6. 把 `desktop/src/aelin_desktop_runtime.cjs` 拆成 runtime 目录，至少先把 `plugin_api`、`capture`、`process bootstrap` 拆出去。

## 11. 一个重要提醒：不要误学“目录很多”

我不建议你为了“更像官方”而把目录拆得非常深。

判断标准应该是：

- 这个子模块是不是一个稳定边界？
- 它是不是可以单独测试？
- 它是不是有独立变化节奏？
- 它是不是应该被多个入口复用？

只要 4 个问题里有 2 个以上回答“是”，就值得独立成模块。

否则就不要为了整洁感而制造新层级。

## 12. 最后判断

我的总体意见是：

- 架构方向：继续效仿 DeepAgents，正确
- 代码组织：应该继续向 DeepAgents / LangChain 靠拢
- 但靠拢的方式不是“更多抽象”，而是“更稳定的边界”

对 Aelin 来说，最理想的下一阶段状态应该是：

- Agent Server 很薄
- DeepAgents runtime assembly 很薄
- capability 与 integration 清晰分离
- frontend 的 stream projection 是独立层
- desktop runtime 不再是单文件子系统

如果做到这一步，Aelin 会比现在更接近「一个清晰的产品壳 + 一个稳定的 DeepAgents-native runtime」。

## 13. 调研来源

### 官方仓库

- DeepAgents: https://github.com/langchain-ai/deepagents
- LangGraph: https://github.com/langchain-ai/langgraph
- LangChain: https://github.com/langchain-ai/langchain

### 官方文档

- Deep Agents overview: https://docs.langchain.com/oss/python/deepagents/overview
- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- LangChain middleware / built-ins: https://docs.langchain.com/oss/python/langchain/middleware/built-in
- LangChain context engineering: https://docs.langchain.com/oss/python/langchain/context-engineering

### 本地对照文件

- `backend/agent_server/graph.py`
- `backend/app/services/deepagents/deepagents_graph.py`
- `backend/app/services/deepagents/tool_runtime.py`
- `backend/app/services/device/device_center.py`
- `frontend/src/features/chat/hooks/useChatStream.ts`
- `frontend/src/features/chat/executionStreamUtils.ts`
- `desktop/src/aelin_desktop_runtime.cjs`
