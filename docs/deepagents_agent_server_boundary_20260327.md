# DeepAgents Agent Server Boundary (2026-03-27)

## Current Decision

本轮不迁移到 LangGraph Agent Server。

当前 Aelin 已经把前后端主链收敛到更接近官方 DeepAgents / `useStream` 的形态，但仍保留一层自定义 HTTP glue，用来承接现有产品约束：

- 现有 FastAPI 鉴权与用户体系
- workspace / provider / attachment / memory 注入
- remote control / device / 本地工具链接入
- 当前桌面端与前端已接好的请求入口

## What We Support Now

- `useStream` 驱动的单线程流式聊天
- 原生 `messages / updates / tasks / values` 事件消费
- runtime tool calls / subagents / todos / graph metadata 展示
- 基于 thread 的会话切换与本地历史恢复

## What We Do Not Support Yet

当前不支持 LangGraph Agent Server 那套更完整的官方能力：

- `stream.queue` 驱动的多消息排队
- queue item 的显式取消 / 跟进 / 可视化排队状态
- thread branch / time-travel 的完整产品化 UI
- 官方 Agent Server 的 branch/history/queue 协议直连

## Why Not Yet

- 当前收益最大的工作已经完成：把旧 Aelin 前端壳收薄，改为更原生的 DeepAgents runtime data flow。
- 直接切 Agent Server 会牵动后端协议、前端 thread/queue UI、鉴权与现有产品 glue，一轮改动面会明显扩大。
- 现阶段优先级更高的是保持现有真实链路稳定，并继续清理冗余壳层。

## Next Step If We Choose To Migrate

如果后续要迁移到 Agent Server，建议按这个顺序做：

1. 保留现有 UI，先在后端并行提供 Agent Server 兼容入口。
2. 前端改接 `queue / branch / history` 官方语义，但先不做 time-travel UI。
3. 跑通多消息 enqueue / cancel / follow-up。
4. 最后再评估是否删除现有自定义 FastAPI streaming glue。
