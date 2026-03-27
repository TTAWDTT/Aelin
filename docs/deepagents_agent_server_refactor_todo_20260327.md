# DeepAgents Agent Server 重构 Todo（2026-03-27）

参考方案：

- [deepagents_agent_server_refactor_plan_20260327.md](D:/Github/Aelin/docs/deepagents_agent_server_refactor_plan_20260327.md)

## 1. Agent Runtime 边界重建

- [x] 1.1 为 DeepAgents graph 新建 Agent Server 入口，明确 assistant / graph 注册边界
- [x] 1.2 把当前 chat runtime 所需的 graph 装配逻辑收敛成 Agent Server 可直接调用的入口
- [x] 1.3 提取统一的用户运行时上下文解析层：user、workspace、LLM config、attachment scope、tool runtime context
- [x] 1.4 确认 Agent Server 运行时可以直接驱动 DeepAgents thread / run / stream，而不是再走自定义 worker 壳

## 2. 用户配置 LLM 能力保留并标准化

- [x] 2.1 保留 `GET /api/v1/agent/config`
- [x] 2.2 保留 `PATCH /api/v1/agent/config`
- [x] 2.3 保留 `POST /api/v1/agent/test`
- [x] 2.4 把 graph 运行时的 provider / model / base_url / api_key / verify_ssl 注入改为统一 resolver
- [x] 2.5 确保前端不直接持有 runtime secret，运行时只从后端用户配置解析

## 3. remote-control / device / attachments / skills 保持完整

- [ ] 3.1 收敛 `remote-control` 核心业务层，保证 HTTP API 与 DeepAgents tool 共用同一实现
- [x] 3.2 保持 `remote-control` 独立 API 可用
- [x] 3.3 保持 device / `screen_get` 工具链可用
- [x] 3.4 保持 attachment 上传接口可用
- [x] 3.5 保持 attachment 检索 tool 在新 runtime 下可用
- [x] 3.6 保持 skills 挂载方式在新 runtime 下可用

## 4. 后端 chat 壳瘦身为极薄网关

- [ ] 4.1 删除或极限收缩 `backend/app/routers/deepagents_chat.py` 中自定义 worker 生命周期管理
- [ ] 4.2 删除或极限收缩 `backend/app/routers/deepagents_chat.py` 中自定义 SSE 事件转译
- [x] 4.3 删除或极限收缩 `backend/app/routers/deepagents_chat.py` 中自定义 idle/progress/tool-activity 判定
- [ ] 4.4 如果仍保留 FastAPI chat 入口，则只保留鉴权、上下文解析与极薄代理能力

## 5. 前端切回更原生的官方 useStream 主路径

- [ ] 5.1 盘点并删除 `deepagentsUseStreamTransport.ts` 中仅为自定义协议存在的补层
- [ ] 5.2 收薄 `useChatStream.ts`，让消息流主要依赖官方 thread / run / stream 语义
- [ ] 5.3 让执行面板直接消费官方 `messages / subagents / values.todos / tasks` 数据
- [ ] 5.4 删除 `executionStreamUtils.ts` 中仅用于自定义 timeline / graph 推断的逻辑
- [ ] 5.5 保持流式输出、停止生成、会话切换仍然可用

## 6. Graph 展示回归官方运行态语义

- [ ] 6.1 区分静态拓扑图与运行时高亮状态
- [ ] 6.2 让节点状态直接来自官方 stream 事件，而不是前端二次猜测
- [ ] 6.3 让 tool call / subagent / todo 在右侧执行面板完整可见
- [ ] 6.4 删除把正文流式文本硬塞进 timeline 的旧展示逻辑

## 7. 旧代码与冗余测试集中清理

- [ ] 7.1 删除与旧自定义 chat 壳强耦合的后端测试
- [ ] 7.2 删除与旧自定义 transport / timeline / trace 强耦合的前端测试与状态层
- [x] 7.3 收缩 `backend/app/services/deepagents/deepagents_graph.py` 中仅为旧壳兜底的逻辑
- [x] 7.4 删除迁移后不再需要的兼容代码、旧字段映射与冗余工具事件补层

## 8. 回归测试与真实链路验证

- [ ] 8.1 后端：覆盖用户配置 LLM、attachments、remote-control、tool runtime、stream cancellation
- [ ] 8.2 前端：覆盖流式聊天、停止生成、会话切换、执行面板显示
- [ ] 8.3 真实链路：普通问答
- [ ] 8.4 真实链路：联网搜索
- [ ] 8.5 真实链路：attachment 检索
- [ ] 8.6 真实链路：remote-control / device
- [ ] 8.7 真实链路：至少一条带 skill 的复杂请求

## 9. 最终收尾

- [ ] 9.1 统计功能代码量变化
- [ ] 9.2 更新架构文档与前端/后端接线说明
- [ ] 9.3 commit
- [ ] 9.4 PR 描述与验证说明
