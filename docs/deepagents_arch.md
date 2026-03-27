# DeepAgents 原生链路现状（2026-03-27）

> 这份文档只描述当前已经落地的 Aelin × DeepAgents 架构，不再保留旧 Aelin agent loop、`tool_trace` 协议或 plane / PinchTab 时代的设计草案。

## 1. 当前目标

Aelin 现在的主链是：

- LangGraph Agent Server 负责 assistant / thread / run 生命周期。
- DeepAgents graph 负责 agent 本身、工具注册、记忆挂载与 subagent/skill 能力。
- Aelin 只保留产品边界：
  - 认证与用户隔离
  - provider / workspace / attachment 上下文解析
  - `/api/v1/agent/*` 配置接口
  - `/api/v1/aelin/*` 产品接口（attachments、device、remote control、context）

也就是说，主链已经从：

`Aelin 自研 loop -> 自定义 SSE 协议 -> 前端`

收缩成：

`LangGraph Agent Server -> 官方 run stream -> useStream 前端`

---

## 2. 聊天主链

### 2.1 主入口

聊天 UI 的主入口已经切到官方 Agent Server：

- `GET /assistants`
- `POST /threads`
- `GET /threads/:thread_id`
- `POST /threads/:thread_id/runs/stream`

关键实现位置：

- [langgraph.json](D:/Github/Aelin/backend/langgraph.json)
- [graph.py](D:/Github/Aelin/backend/agent_server/graph.py)
- [auth.py](D:/Github/Aelin/backend/agent_server/auth.py)
- [deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py)

### 2.2 运行流程

1. 前端通过 LangGraph SDK 创建或复用 thread。
2. `useStream(...)` 向官方 `/threads/:thread_id/runs/stream` 提交消息。
3. Agent Server 通过 [auth.py](D:/Github/Aelin/backend/agent_server/auth.py) 解析当前用户，并给 thread/store 自动加 owner scope。
4. Agent Server 通过 [graph.py](D:/Github/Aelin/backend/agent_server/graph.py) 解析当前运行上下文：
   - `user_id`
   - `workspace`
   - `attachment_ids`
5. `graph.py` 调用运行时 resolver：
   - 读取当前用户的 provider / model / api_key / base_url 配置
   - 读取当前 workspace 的 `AGENTS.md`
   - 构造 DeepAgents tool runtime context
6. 通过 `build_chat_agent(...)` 创建 DeepAgents agent，并把官方 run stream 直接透给前端。

### 2.3 当前事件语义

前端现在直接消费官方运行态数据，而不是旧 Aelin 自定义事件：

- `messages`
- `tasks`
- `values`
- `subagents`
- tool call metadata

已经删除的旧聊天兼容事件/字段：

- `reply`
- `tool_trace`
- `memory_summary`
- `stop_reason`
- 自定义 `/api/v1/deepagents/chat/stream` worker 生命周期

---

## 3. 前端链路消费方式

关键文件：

- [useChatStream.ts](D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts)
- [executionStreamUtils.ts](D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts)

当前前端做的是：

- 使用 `@langchain/langgraph-sdk` 的 `Client`
- 使用 `@langchain/react` 的 `useStream`
- 以 `threadId = sessionId` 直接对接官方 thread / run 语义
- 从 `messages / getToolCalls / subagents / values` 重建右侧执行态

当前已经删除的旧前端壳逻辑：

- 自定义 SSE transport
- 旧 `/api/v1/deepagents/chat/stream` 解析
- `reply` 兼容分支
- `tool_trace` / `AelinToolStep` 前端依赖
- `memorySummary` 聊天气泡字段

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
- 由运行时 resolver 注入当前用户、workspace、attachment scope、write policy

当前主链工具包括：

- web search
- attachment search
- google workspace
- device
- screen capture
- skill / file 相关能力

### 5.2 skills

skills 根目录：

- `backend/deepagents_skills/`

挂载方式：

- 将 `SKILL.md` 文件挂到 skills 根目录
- 统一通过 DeepAgents 的 skills 目录能力暴露给 agent

以后新增 skill，主路径就是：

1. 在 `backend/deepagents_skills/<skill_name>/SKILL.md` 下新增内容
2. 如有必要补充配套说明文件
3. 不需要再手工往 system prompt 里塞一层兼容说明

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

它的职责是：

- 给 remote control / bot 这类非流式入口提供同步 `run_chat_request(...)`
- 在 agent 无结果时返回统一 fallback

它不是聊天 UI 的主入口。

---

## 7. 已明确删除的东西

以下内容不再属于当前架构：

- 旧 Aelin agent loop 状态机
- 自定义 `/api/v1/deepagents/chat/stream`
- `deepagents_chat.py`
- `stream_gateway.py`
- `reply` 流事件
- 前端 `tool_trace` 依赖
- 前端 `memory_summary` 依赖
- 旧 `/api/v1/aelin/chat` 前端主调用路径

---

## 8. 继续演进时的约束

当前必须继续守住三条边界：

- 不再重新发明一套聊天协议
- 不再把额外上下文偷偷塞回主链
- 不再从文本里硬扒工具信息去模拟 graph

只要继续守住这三点，Aelin 就会保持“DeepAgents 内核 + 官方 Agent Server + 很薄产品壳”的状态。
