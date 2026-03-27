# DeepAgents 原生链路现状（2026-03-25）

> 这份文档只描述当前已经落地的 Aelin × DeepAgents 架构，不再保留旧 Aelin agent loop、`tool_trace` 协议或 plane / PinchTab 时代的设计草案。

## 1. 当前目标

Aelin 现在的方向是：

- DeepAgents / LangGraph 负责 agent 运行时本身。
- Aelin 只保留必须的外壳能力：
  - 认证与 API 路由
  - provider / workspace 选择
  - 本地工具接入
  - AGENTS.md 文件记忆
  - 附件、device、remote control 这类产品能力

换句话说，主链已经从：

`Aelin 自研 loop -> 自定义 trace -> 前端`

收缩成：

`DeepAgents agent.stream(...) -> 轻量 SSE 包装 -> 前端`

---

## 2. 聊天主链

### 2.1 主入口

聊天 UI 的主入口是：

- `POST /api/v1/deepagents/chat/stream`

实现位置：

- [deepagents_chat.py](D:/Github/Aelin/backend/app/routers/deepagents_chat.py)
- [deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py)
- [input_mapping.py](D:/Github/Aelin/backend/app/services/deepagents/input_mapping.py)

### 2.2 运行流程

1. 路由读取 `query / workspace / history / images / attachment_ids`。
2. 解析当前用户的 provider/model 配置。
3. 读取当前 workspace 的 `AGENTS.md` 文本作为唯一记忆输入。
4. 构造 tool runtime context。
5. 通过 `build_chat_agent(...)` 创建 DeepAgents agent。
6. 直接调用：

```python
agent.stream(
    invoke_payload,
    stream_mode=["messages", "updates", "tasks", "values"],
    version="v2",
    subgraphs=True,
)
```

7. 将 LangGraph / DeepAgents 原生运行事件按 SSE 向前端透出。

### 2.3 当前 SSE 事件

当前前端消费的事件集合是：

- `start`
- `messages`
- `updates`
- `tasks`
- `values`
- `final`
- `error`
- `done`
- `ping`

已经删除的旧聊天兼容事件：

- `reply`
- `tool_trace`
- `memory_summary`

也就是说，前端现在不再依赖“旧 Aelin 自定义聊天协议字段”来重建执行链路。

---

## 3. 前端链路消费方式

关键文件：

- [sse.ts](D:/Github/Aelin/frontend/src/shared/api/sse.ts)
- [executionEventUtils.ts](D:/Github/Aelin/frontend/src/features/chat/executionEventUtils.ts)
- [ExecutionPane.tsx](D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx)

当前前端做的是：

- 直接消费 `messages / updates / tasks / values` 这些原生运行事件。
- 把它们压成一个很薄的 `executionEvents[]` 视图模型。
- `ExecutionPane` 直接展示真实事件时间线和工具列表。

当前已经删除的旧前端壳逻辑：

- 从 `tool_runs` 反推伪 graph
- `reply` 兼容分支
- `memorySummary` 聊天气泡字段
- `tool_trace` / `AelinToolStep` 前端依赖
- 旧 `/api/v1/aelin/chat` 调用入口

---

## 4. 记忆

### 4.1 唯一记忆来源

DeepAgents 记忆现在只认：

- `/memory/AGENTS.md`

实际来源是当前用户、当前 workspace 的 AGENTS 文件文本。

### 4.2 已删除的旧思路

下面这些已经不再是聊天主链的记忆来源：

- DB 记忆摘要注入
- `memory_summary -> /memory/AGENTS.md` 的二次桥接
- 旧上下文 bundle 参与 agent 主链
- openviking / plane / proactive 时代的额外上下文拼装

### 4.3 `/aelin/context` 的定位

`GET /api/v1/aelin/context` 仍然保留，但它现在只是一个 UI 视图接口：

- 用于把 AGENTS.md 投影成 `summary / notes / todos / memory_layers`
- 不再反向参与 DeepAgents 聊天主链

---

## 5. 工具与 skills

### 5.1 工具

工具主链已经收紧到 DeepAgents 标准注册方式：

- 由 [deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py) 注册为 LangChain / DeepAgents tools
- 由 [tool_runtime.py](D:/Github/Aelin/backend/app/services/deepagents/tool_runtime.py) 提供运行时上下文与调用上限保护

当前主链工具包括：

- web search
- attachment search
- google workspace
- device
- screen capture
- skill / file 相关能力

`AelinToolHub` 还存在，但定位已经收缩成“产品侧工具实现的薄适配层”，不是 agent loop 本身。

### 5.2 skills

skills 根目录：

- `backend/deepagents_skills/`

挂载方式：

- 将 `SKILL.md` 文件挂到虚拟文件系统
- 统一通过 DeepAgents 的 skills 目录能力暴露给 agent

这意味着以后新增 skill，主路径就是：

1. 在 `backend/deepagents_skills/<skill_name>/SKILL.md` 下新增内容
2. 如有必要补充配套说明文件
3. 不需要再手工往 system prompt 里塞一大坨说明文字

---

## 6. Aelin 还保留什么壳

当前仍然保留的 Aelin 外壳，主要是产品边界而不是 agent runtime：

- `/api/v1/agent/*`
  - provider / base_url / model / key 配置
- `/api/v1/aelin/context`
  - AGENTS.md 的 UI 投影视图
- `/api/v1/aelin/attachments/upload`
  - 附件导入
- `/api/v1/aelin/memory/file-memory/content`
  - 文件记忆查看
- `/api/v1/aelin/device/*`
  - 屏幕抓取与设备能力
- `/api/v1/aelin/remote-control/*`
  - 远控入口

另外还保留一个同步包装层：

- [core.py](D:/Github/Aelin/backend/app/services/aelin/core.py)

它的职责已经不是“旧 agent loop”，而是：

- 给 remote control / bot 这类非流式入口提供同步 `run_chat_request(...)`
- 在失败时返回一个统一 fallback

它不是聊天 UI 的主入口。

---

## 7. 已明确删除的东西

以下内容不再属于当前架构：

- 旧 Aelin agent loop 状态机
- `deepagents_loop.py` 独立桥接层
- plane / PinchTab 主链
- `reply` 流事件
- 前端 `tool_trace` 依赖
- 前端 `memory_summary` 依赖
- 旧 `/api/v1/aelin/chat` 前端主调用路径

---

## 8. 当前仍需继续收口的方向

虽然主链已经很接近原生 DeepAgents 了，但仍有两类“外壳”是刻意保留的：

1. 产品接口壳
   - 例如附件上传、device、remote control、agent config
2. 非流式兼容壳
   - 例如 `run_chat_request(...)` 给 bot / remote control 走同步返回

这些不是历史包袱，而是 Aelin 作为产品必须保留的边界。

真正需要继续避免的是：

- 再重新发明一套聊天协议
- 再把额外上下文偷偷塞回主链
- 再从文本里硬扒 tool 信息去模拟 graph

只要继续守住这三点，Aelin 就会保持“DeepAgents 内核 + 很薄产品壳”的状态。
