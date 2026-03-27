# DeepAgents Agent Server 终局版 Todo（2026-03-27）

本文件描述的是“最终形态”，不是过渡形态。

已经拍板的终局目标：

- 聊天主链只保留官方 Agent Server：
  - `/assistants`
  - `/threads`
  - `/runs`
  - 前端 `useStream`
- Aelin 不再保留任何自定义 chat transport、自定义 SSE、自定义 stop_reason、自定义 tool_trace、自定义 graph 推断
- FastAPI 只保留业务 API：
  - 登录鉴权
  - 用户 LLM 配置
  - attachment 上传
  - device / remote-control
- DeepAgents runtime 只保留官方 graph 装配与业务工具挂载
- 旧的 `aelin chat shell`、旧 context 拼装层、旧流式包装层、旧兼容测试，最终都要删干净

## 一、终局后端结构

终局后端只允许保留下面这些职责：

- `backend/agent_server/*`
  - Agent Server graph 注册
  - Agent Server auth
- `backend/app/routers/auth.py`
  - 登录鉴权
- `backend/app/routers/agent.py`
  - 用户 LLM 配置与连通性测试
- `backend/app/routers/aelin_device.py`
  - device 辅助 API
- `backend/app/routers/aelin_remote_control.py`
  - remote-control API
- `backend/app/routers/attachments.py`
  - attachment 上传 API
- `backend/app/services/deepagents/*`
  - graph 装配、runtime resolver、input/output 映射、tool runtime
- `backend/app/services/tools/*`
  - files / web / gws / device 工具
- `backend/app/services/device/*`
  - remote-control 与 device 核心实现
- `backend/app/services/attachments/*`
  - 附件解析、存储、检索
- `backend/app/services/foundation/*`
  - llm / model catalog / encryption / gws cli
- `backend/app/services/memory/agent_memory.py`
  - DeepAgents 记忆正文
- `backend/app/services/memory/file_memory_bridge.py`
  - DeepAgents 文件记忆桥接
- `backend/app/services/web/*`
  - 搜索 provider 与聚合
- `backend/app/services/bots/*`
  - 保留 Feishu / QQ bot 业务能力，但不允许承载 chat runtime

终局后端明确不再允许保留下面这些职责：

- 自定义 chat worker
- 自定义 stream gateway
- 自定义 SSE 事件协议
- 自定义 graph 推断
- 独立的 Aelin chat orchestration 壳
- 旧 context bundle / summary / memory_layers 拼装

## 二、必须删除或迁移的后端文件

### 2.1 彻底删除 chat 壳与旧 context 壳

- [x] 删除 [backend/app/routers/aelin_context.py](/D:/Github/Aelin/backend/app/routers/aelin_context.py)
  - 原因：这是旧的 Aelin context bundle API，不属于 Agent Server 终局形态
  - 验收：`app.main` 不再注册该 router；前端与测试中不再引用 `/api/v1/aelin/context`

- [x] 删除 [backend/app/services/aelin/context_service.py](/D:/Github/Aelin/backend/app/services/aelin/context_service.py)
  - 原因：只服务于旧 context 拼装
  - 验收：代码库中不再有该模块导入

- [x] 删除 [backend/app/services/aelin/core_support.py](/D:/Github/Aelin/backend/app/services/aelin/core_support.py)
  - 原因：只服务于旧 `/aelin/context` 输出
  - 验收：删除后测试仍通过，且不再有 `_build_context_bundle` / `_build_cached_base_context_bundle` 引用

- [x] 删除 [backend/app/services/aelin/streaming.py](/D:/Github/Aelin/backend/app/services/aelin/streaming.py)
  - 原因：自定义 SSE 辅助函数，终局形态不允许存在
  - 验收：代码库中不再有 `_sse_event(...)` 的引用

### 2.2 拆掉 `aelin_chat.py` 中非 attachment 职责

- [x] 新增 [backend/app/routers/attachments.py](/D:/Github/Aelin/backend/app/routers/attachments.py)
  - 把 `aelin_chat.py` 中的 attachment 上传接口迁移到这里
  - 把 `aelin_chat.py` 中的 file-memory content 查询接口一并迁到这里，作为 attachment/file-memory 领域接口
  - 新 router 前缀固定为 `/attachments`
  - 终局接口为：`POST /api/v1/attachments/upload`
  - 终局接口为：`GET /api/v1/attachments/file-memory/content`
  - 验收：前端与其他调用方改走新接口，`aelin_chat.py` 完全可以删除

- [x] 删除 [backend/app/routers/aelin_chat.py](/D:/Github/Aelin/backend/app/routers/aelin_chat.py)
  - 前提：attachment 上传与 file-memory content 查询都已迁到 `attachments.py`
  - 原因：终局后端不允许存在名为 “chat router” 的自定义壳
  - 验收：`app.main` 不再注册 `aelin_chat.router`

### 2.3 收缩并最终消灭 `app/services/aelin/*` 中的壳层命名

- [x] 修改 [backend/app/services/aelin/runtime.py](/D:/Github/Aelin/backend/app/services/aelin/runtime.py)
  - 只保留“用户 LLM 配置解析”这一项职责
  - 删除 workspace slug、legacy 帮助函数中与 chat shell 命名相关的注释与语义
  - 验收：该文件只承担 config resolver，不再承担任何 chat/runtime 壳职责

- [x] 新增 [backend/app/services/foundation/agent_config_service.py](/D:/Github/Aelin/backend/app/services/foundation/agent_config_service.py)
  - 把 `backend/app/services/aelin/runtime.py` 中以下函数迁移到这里：
    - `default_config`
    - `config_out`
    - `resolve_llm_service`
    - `resolve_llm_service_for_user_id`
    - `normalize_workspace`
  - 验收：`agent.py` 与 `runtime_resolver.py` 改为引用新模块

- [x] 删除 [backend/app/services/aelin/runtime.py](/D:/Github/Aelin/backend/app/services/aelin/runtime.py)
  - 前提：上面的 resolver 已迁出
  - 原因：终局形态不再保留 `aelin.runtime` 这种旧壳命名
  - 验收：`app/services/aelin` 目录中不再有 runtime 相关代码

- [x] 处理 [backend/app/services/aelin/core.py](/D:/Github/Aelin/backend/app/services/aelin/core.py)
  - 最终只允许保留 remote-control 所需的同步入口
  - 删除无效 `event_cb`
  - `memory_summary` 固定返回空字符串
  - 文件名不再允许继续叫 `core.py`
  - 终局改名为 [backend/app/services/device/remote_control_chat_adapter.py](/D:/Github/Aelin/backend/app/services/device/remote_control_chat_adapter.py)
  - 验收：`remote_control.py` 改用新文件；`backend/app/services/aelin/core.py` 被删除

- [x] 删除 [backend/app/services/aelin/core.py](/D:/Github/Aelin/backend/app/services/aelin/core.py)
  - 前提：同步 chat 适配器已迁移到 device 域
  - 原因：终局形态不再允许 `aelin.core` 命名残留
  - 验收：`backend/app/services/aelin/core.py` 已删除，且无任何 import 残留

- [x] 删除 [backend/app/services/aelin/expressions.py](/D:/Github/Aelin/backend/app/services/aelin/expressions.py)
  - 原因：这是旧 Aelin legacy chat 的表情/表达层，不属于官方 Agent Server 主链
  - 验收：remote-control 与任何 API 不再依赖 `expression`

- [x] 删除整个 [backend/app/services/aelin](/D:/Github/Aelin/backend/app/services/aelin) 目录
  - 前提：以下迁移已完成：
    - `runtime.py` -> `foundation/agent_config_service.py`
    - `core.py` -> `device/remote_control_chat_adapter.py`
    - `attachment_service.py` -> `attachments/attachment_service.py`
    - `utils.py` -> `foundation/service_utils.py`
  - 终局决定：`app/services/aelin/*` 目录不再保留
  - 验收：代码库中不再存在 `from app.services.aelin ...`

## 三、后端入口最终只保留业务 API

- [x] 修改 [backend/app/main.py](/D:/Github/Aelin/backend/app/main.py)
  - 最终只注册下面这些 router：
    - `auth.router`
    - `agent.router`
    - `attachments.router`
    - `aelin_device.router`
    - `aelin_remote_control.router`
  - 删除 `aelin_chat.router`
  - 删除 `aelin_context.router`
  - 验收：`create_app()` 中不再出现任何 “chat / context shell” router

- [x] 保留 [backend/app/services/bots/feishu_bot.py](/D:/Github/Aelin/backend/app/services/bots/feishu_bot.py) 与 [backend/app/services/bots/qq_bot.py](/D:/Github/Aelin/backend/app/services/bots/qq_bot.py)
  - 终局决定：bot 能力保留，但它们只能调用业务 API / remote-control / Agent Server，不得重新引入自定义 chat runtime
  - 验收：`main.py` 中 bot 启动逻辑可保留，但 bot 代码里不能出现旧 chat stream 壳依赖

- [x] 检查 [backend/langgraph.json](/D:/Github/Aelin/backend/langgraph.json)
  - 保持 graph 入口为 `./agent_server/graph.py:make_graph`
  - 保持 auth 入口为 `./agent_server/auth.py:aelin_auth`
  - 保持 mounted app 为 `./app/main.py:app`
  - 验收：FastAPI 只充当业务附属 app，不再承载聊天运行时

## 四、前端最终只保留官方 useStream 语义

### 4.1 graph 与运行态必须完全分层

- [x] 修改 [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts)
  - assistant id 解析完成后，固定调用 `client.assistants.getGraph(assistantId, { xray: 2 })`
  - 把 `assistantGraph` 与 `stream` 一起返回
  - 不再引用 `stream.values.topology`
  - 验收：静态 graph 数据源唯一且只来自官方 API

- [x] 修改 [frontend/src/features/chat/executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts)
  - 删除所有“没有 graph 时自动补 nodes / edges”的逻辑
  - 删除所有“根据消息顺序生成 traversed edge”的逻辑
  - 运行时只保留：
    - lanes
    - tools
    - subagents
    - todos
    - values snapshot
  - 静态 topology 只接受 official `AssistantGraph`
  - 验收：代码中不再存在“derivedEdges / byNamespace 补边 / fallback topology”

- [x] 修改 [frontend/src/features/chat/components/ExecutionPane.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx)
  - `Graph` 页签固定拆成：
    - `Static graph`
    - `Live paths`
  - 当没有 official graph 时，只显示“Runtime did not publish a graph”
  - 不再使用 `Topology` 这个旧命名
  - 验收：界面不再暗示 graph 是前端自己推出来的

- [x] 修改 [frontend/src/features/chat/components/ExecutionPaneParts.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPaneParts.tsx)
  - `TopologyBoard` 只渲染官方 graph 的 nodes / edges
  - 没有 edge 时显示离散节点，不补串行线
  - 验收：不会再出现“图看起来总是串行”的假象

### 4.2 message 与 stream 状态不再额外造一层协议

- [x] 修改 [frontend/src/features/chat/hooks/chatStreamHelpers.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamHelpers.ts)
  - 保留“把官方 message 转成 UI message”的最小映射
  - 删除任何兼容旧 Aelin chat payload 的字段映射
  - 验收：这里只保留官方消息到 UI 气泡所需的最小转换

- [x] 修改 [frontend/src/features/chat/ChatView.tsx](/D:/Github/Aelin/frontend/src/features/chat/ChatView.tsx)
  - `ExecutionPane` 的输入改为 `stream + assistantGraph`
  - 取消任何对旧 topology/value 结构的额外判断
  - 验收：页面主容器只负责组合官方 stream 结果与产品 UI 组件

- [x] 修改 [frontend/src/features/chat/components/ChatStatusBar.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ChatStatusBar.tsx)
  - 右侧执行面板按钮显示条件固定为：
    - 正在流式运行
    - 或存在 official graph
    - 或存在 tools / subagents / lanes / todos
  - 不再通过推导 topology 节点数控制按钮
  - 验收：按钮显隐与官方运行态一致

### 4.3 旧前端冗余必须删掉

- [x] 新增 [frontend/src/features/chat/executionStreamUtils.test.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.test.ts)
  - 验证：
    - official assistant graph 会被正确归一化
    - 无 graph 时不会再补边
    - 只有 stream metadata 时仍可显示 lanes
  - 验收：测试直接锁死“前端不猜 graph”

- [x] 检查并删除任何仍引用以下旧概念的前端代码
  - `tool_trace`
  - `stop_reason`
  - 自定义 timeline graph
  - 自定义 SSE transport
  - 验收：`frontend/src/features/chat` 目录中不再存在这些词汇和对应状态层

## 五、Desktop 最终也只跑 Agent Server

- [x] 修改 [desktop/src/aelin_desktop_runtime.cjs](/D:/Github/Aelin/desktop/src/aelin_desktop_runtime.cjs)
  - 开发态与打包态统一使用 `langgraph dev` / Agent Server 启动链路
  - 不再保留任何假设“uvicorn 是聊天主入口”的逻辑
  - 验收：桌面端启动后，聊天仍然直接走 Agent Server

- [x] 修改 [desktop/src/main.cjs](/D:/Github/Aelin/desktop/src/main.cjs)
  - 删除所有对旧 `/api/v1/deepagents/chat/stream`、旧 chat backend、旧 uvicorn chat 主入口的依赖
  - 验收：桌面端只依赖 Agent Server 与业务 API

## 六、测试终局清理

- [x] 删除所有只验证旧 chat 壳的测试
  - 终局后端保留测试文件名单固定为：
    - `tests/test_agent_server_auth.py`
    - `tests/test_agent_server_graph.py`
    - `tests/test_remote_control.py`
    - `tests/test_aelin_tools.py`
    - `tests/test_aelin_attachment_service.py`
    - `tests/test_aelin_device.py`
    - `tests/test_llm_ssl.py`
    - `tests/test_settings.py`
    - `tests/test_schemas.py`
  - 终局明确删除的旧测试文件为：
    - `tests/test_aelin.py`
    - `tests/test_aelin_preflight_perf.py`
    - `tests/test_aelin_tool_policy.py`
    - `tests/test_aelin_utils.py`
    - `tests/test_agent_memory_deepagents.py`
    - `tests/test_deepagents_run_constraints.py`
    - `tests/test_google_workspace_cli.py`
  - 验收：`backend/tests` 的保留面严格围绕终局能力，没有 legacy chat 壳测试残留

- [x] 修改 [backend/tests/test_remote_control.py](/D:/Github/Aelin/backend/tests/test_remote_control.py)
  - 适配新的 `remote_control_chat_adapter.py`
  - 断言 `memory_summary == ""`
  - 验收：remote-control 仍能用，但不再携带 legacy chat 壳字段

- [x] 新增/更新前端回归
  - 新增 `frontend/src/features/chat/executionStreamUtils.test.ts`
  - 新增 `frontend/src/features/chat/hooks/useChatStream.test.ts`
  - `useChatStream.test.ts` 必须覆盖：
    - assistant id 解析
    - `assistants.getGraph(...)` 拉取
    - thread bootstrap
  - 验收：前端“官方 graph + 官方 stream”主路径有自动化覆盖

## 七、真实链路终局验收

- [x] 后端测试
  - 运行：`cd backend && pytest tests/test_agent_server_auth.py tests/test_agent_server_graph.py tests/test_remote_control.py tests/test_aelin_tools.py -q`
  - 必须全部通过

- [x] 前端构建
  - 运行：`cd frontend && npm run build`
  - 必须通过

- [ ] 真实链路 1：普通问答
  - 使用 Agent Server
  - 验收：流式输出正常

- [ ] 真实链路 2：联网搜索
  - 验收：右侧面板能看到官方 tool / lane / subagent 信息

- [ ] 真实链路 3：附件问答
  - 验收：上传走 `/api/v1/attachments/upload`，运行时仍能检索附件

- [ ] 真实链路 4：remote-control / device
  - 验收：业务 API 与 agent 工具都正常

- [ ] 真实链路 5：桌面端
  - 验收：桌面端不依赖旧 chat backend，也能工作

- [ ] 全局日志验收
  - 验收条件：
    - 运行日志中不再出现旧 `/api/v1/deepagents/chat/stream`
    - 代码库中不再存在旧自定义 chat stream 路由

## 八、终局文档

- [ ] 修改 [docs/deepagents_arch.md](/D:/Github/Aelin/docs/deepagents_arch.md)
  - 明确写清楚终局架构：
    - 聊天 = Agent Server
    - FastAPI = 业务 API
    - 静态 graph = `assistants.getGraph`
    - 运行态 = `useStream`
    - 不再存在自定义 chat transport

- [ ] 更新 README 系列文档
  - [README.md](/D:/Github/Aelin/README.md)
  - [README.en.md](/D:/Github/Aelin/README.en.md)
  - [README.zh-CN.md](/D:/Github/Aelin/README.zh-CN.md)
  - 明确写清楚新的 attachment 接口与启动方式

## 九、最终提交要求

- [ ] 所有旧 chat 壳文件删除后，再做一次代码搜索
  - 不允许再出现这些词：
    - `tool_trace`
    - `stop_reason`
    - `deepagents_chat`
    - `stream_gateway`
    - `aelin_context`
    - `Aelin chat shell`
    - `from app.services.aelin`
    - `/api/v1/deepagents/chat/stream`

- [ ] commit
  - 固定 commit message：`refactor(agent-server): remove remaining aelin chat shell and finalize native runtime`
