# DeepAgents 纯原生化 TODO（2026-03-25）

> 目标：把 Aelin 从“DeepAgents 内核 + Aelin 壳层兼容”继续收紧为“纯粹的 DeepAgents 壳”。
>
> 完成标准：
> 1. 聊天主链直接围绕 `create_deep_agent(...)` 与 `agent.stream(..., version="v2")` 运作。
> 2. 前端执行链路直接消费 LangGraph / DeepAgents 运行事件，而不是从 `tool_runs` 反推伪 graph。
> 3. 记忆、工具、skills 都尽量回归 DeepAgents 原生表达，不再保留多余的 Aelin 桥接层。

---

## 1. 后端流协议原生化

- [x] 1.1 审查并精简 `backend/app/routers/deepagents_chat.py`
- [x] 1.2 将聊天流主链切到 `agent.stream(..., stream_mode=[...], version="v2")`
- [x] 1.3 直接向前端透出原生运行事件，至少覆盖 `messages`、`updates`、`tasks`、`values`
- [x] 1.4 删除或下线仅为旧 `reply/final/tool_runs` 壳协议存在的翻译逻辑
- [x] 1.5 补齐新的流式协议测试，断言事件序列而不是旧壳字段

## 2. 前端聊天与执行链路原生化

- [x] 2.1 审查并精简 `frontend/src/shared/api/sse.ts`
- [x] 2.2 删除前端对旧 `reply / toolRuns / toolTrace / final.answer 覆盖补丁` 的主链依赖
- [x] 2.3 建立基于原生运行事件的 `executionEvents` 状态结构
- [x] 2.4 重写 `ExecutionPane`，直接展示真实运行事件时间线
- [x] 2.5 重写或删除 `AgentTracePanel.tsx` 与 `traceUtils.ts` 的伪 graph 推导逻辑
- [x] 2.6 评估并接入 DeepAgents / LangGraph 推荐的 `useStream` 用法；若暂不直连，也要把兼容层收薄到最小
- [x] 2.7 完成前端流解析与执行面板验证（当前仓库无前端单测基座，本轮以 `npm run build` 作为回归验证）

## 3. 工具层去壳与标准化

- [x] 3.1 审查并精简 `backend/app/services/deepagents/deepagents_graph.py`
- [x] 3.2 找出 `AelinToolHub` 在主链中的剩余职责，并逐项迁出
- [x] 3.3 找出 `AelinToolPolicy` 在主链中的剩余职责，并收紧到最薄保护层
- [x] 3.4 删除手工 `tool_runs` 记录作为主链执行数据源的角色
- [x] 3.5 让现有工具直接以标准 LangChain / DeepAgents tool 形式注册
- [x] 3.6 评估并接入 DeepAgents 自带可复用工具能力，避免重复手搓
- [x] 3.7 补齐工具注册与运行测试，确认 remote control / device / web search 不回退

## 4. 记忆与输入映射去桥接

- [x] 4.1 审查并精简当前 memory 装配链路
- [x] 4.2 删除 “Aelin memory summary -> `/memory/AGENTS.md`” 的桥接思路
- [x] 4.3 让 DeepAgents memory 成为唯一聊天记忆来源
- [x] 4.4 审查并精简 `backend/app/services/deepagents/input_mapping.py`
- [x] 4.5 让 history / images / attachments 的输入装配更贴近 DeepAgents 原生约定
- [x] 4.6 删除不再需要的旧上下文拼装逻辑与残留测试

## 5. 最终删旧层与收尾

- [x] 5.1 审查并删除 `backend/app/services/deepagents/deepagents_loop.py` 这类仅为旧壳保留的桥接层
- [ ] 5.2 继续排查并删除后端中残留的 Aelin agent-loop 命名、类型与兼容逻辑
- [ ] 5.3 继续排查并删除前端中残留的旧聊天协议字段与适配代码
- [ ] 5.4 更新 `docs/deepagents_arch.md` 等文档，说明新的纯原生链路
- [ ] 5.5 完成一轮真实链路测试，验证聊天、工具、skills、memory、remote control
- [ ] 5.6 清理冗余代码、运行测试、提交 commit

---

## 结果要求

- [ ] R1 聊天主链不再依赖旧 Aelin 自定义 SSE 语义
- [ ] R2 Execution Pane 不再从 `tool_runs` 反推执行过程
- [ ] R3 记忆主链不再依赖 Aelin 自己的 summary/bridge 方案
- [ ] R4 工具主链尽可能只保留 DeepAgents 标准注册方式
- [ ] R5 仓库整体进一步精简，并保持真实链路可用
