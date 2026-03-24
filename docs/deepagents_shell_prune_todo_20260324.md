# DeepAgents 壳层继续精简 TODO（2026-03-24）

> 目标：继续把 Aelin 中“只为兼容旧聊天壳而存在”的桥接层删掉，尽可能收敛成  
> **DeepAgents 原生流式协议 + 极薄 HTTP glue + 少量 domain services**。

---

## 1. 收敛消息构造逻辑

- [x] 1.1 提取统一的 DeepAgents 输入构造器
  - [x] 将 `query/history/images -> messages/files` 的构造逻辑抽成一个小模块
  - [x] 让 `/api/v1/deepagents/chat/stream` 与 `deepagents_loop.py` 共用这份逻辑

- [x] 1.2 删除重复映射
  - [x] 删除 `deepagents_chat.py` 与 `deepagents_loop.py` 中重复的 history / images 拼装代码
  - [x] 保持只剩一份真正的 DeepAgents 输入映射实现

验收标准：
- [x] 聊天主链与 bridge 链都通过同一个输入构造函数生成 `messages`
- [x] 不再存在两套相似的 history / image 映射代码

---

## 2. 删除 DeepAgents → Aelin AgentLoopResult 桥接层

- [x] 2.1 收紧 `deepagents_loop.py`
  - [x] 让 `deepagents_loop.py` 不再产出 `AelinAgentLoopResult`
  - [x] 改为返回更贴近 DeepAgents 的轻量结果：`answer / tool_runs / usage / memory_snapshot / error`

- [x] 2.2 删除 `loop_types.py`
  - [x] 删除 `AelinAgentLoopResult`
  - [x] 删除 `AgentLoopTraceStep`
  - [x] 删除 `AgentLoopToolRun`
  - [x] 删除 `STOP_REASON_*`

- [x] 2.3 清理 bridge 内的旧语义判断
  - [x] 评估并删除 `stop_reason` 驱动的旧失败分类
  - [x] 删除仅服务旧壳的 `_answer_has_unsupported_action_claims` 兼容逻辑，并将结果提取逻辑收紧为最小保留实现

验收标准：
- [x] `backend/app/services/deepagents/deepagents_loop.py` 不再依赖 `backend/app/services/aelin/loop_types.py`
- [x] 聊天主链中不存在 `stop_reason` / `AgentLoopTraceStep` 的内部桥接

---

## 3. 精简 `aelin/core.py` 的兼容壳

- [x] 3.1 删除旧 trace 拼装
  - [x] 删除 `AelinToolStep` 风格的中间 trace 拼装逻辑
  - [x] 删除只服务旧右侧链路的 `tool_trace` 生成代码

- [x] 3.2 删除旧 fallback 壳
  - [x] 删除 `attachment_prefetch_fallback` 风格的旧聊天 fallback
  - [x] 删除 `fallback_to_legacy` 相关逻辑

- [x] 3.3 删除旧 answer 后处理
  - [x] 评估并删除 `expression` / 老式回答修饰逻辑
  - [x] 保持返回尽量贴近 DeepAgents 的自然输出

- [x] 3.4 只保留必要 preflight
  - [x] 保留 workspace / provider / memory / tool_hub 这些真正必要的 glue
  - [x] 删除不再必要的兼容层辅助代码

验收标准：
- [x] `aelin/core.py` 明显缩短，只剩 DeepAgents 主链真正需要的 glue
- [x] 不再承担旧 SSE / tool_trace / fallback 壳的职责

---

## 4. 删除 `chat_dispatch.py` 与旧聊天 fallback 入口

- [x] 4.1 清理 `chat_dispatch.py`
  - [x] 删除 `dispatch_aelin_chat(...)` 这层旧聊天 fallback 入口
  - [x] 确认聊天主链只经由 DeepAgents 路由或直接 DeepAgents service

- [x] 4.2 调整调用方
  - [x] remote control / 其他入口如果仍调用 `dispatch_aelin_chat`，改为直接走新的 DeepAgents chat service

验收标准：
- [x] `backend/app/services/aelin/chat_dispatch.py` 被删除
- [x] 仓库中不再有 `dispatch_aelin_chat` 作为聊天主入口

---

## 5. 压缩聊天 schema 到更中性的 DeepAgents 壳

- [x] 5.1 审查当前 schema
  - [x] 审查 `AelinChatRequest`
  - [x] 审查 `AelinChatResponse`
  - [x] 审查 `AelinToolStep`

- [x] 5.2 删除只服务旧聊天壳的字段
  - [x] 删除不再被 DeepAgents 主链使用的响应字段
  - [x] 删除只为旧 trace/stop_reason 设计的 schema

- [x] 5.3 统一命名
  - [x] 视影响范围将 `AelinChat*` 改成更中性的 `Chat*` 或 DeepAgents shell 命名

验收标准：
- [x] 聊天 schema 更贴近 DeepAgents 原生流式协议
- [x] 不再保留大量只服务旧壳的字段/类型

---

## 6. 清理 remote control / bot 的旧壳依赖

- [x] 6.1 检查 remote control
  - [x] 检查 `device/remote_control.py` 是否仍依赖 `AelinChatResponse` / `tool_trace` / `dispatch_aelin_chat`
  - [x] 改为消费新的 DeepAgents 最终结果

- [x] 6.2 检查 Feishu / QQ bot
  - [x] 确认机器人链路不再依赖旧聊天兼容壳
  - [x] 删除对应桥接逻辑

验收标准：
- [x] remote control / bot 入口不再依赖旧聊天壳
- [x] DeepAgents 成为所有聊天能力入口的唯一内核

---

## 7. 最终收尾

- [x] 7.1 删除死代码与过时测试
  - [x] 删除本轮清理后不再引用的 helper / DTO / 测试
  - [x] 删除仅服务旧聊天壳的文档说明

- [x] 7.2 真实链路测试
  - [x] 启动真实后端
  - [x] 验证 `/api/v1/deepagents/chat/stream`
  - [x] 验证前端聊天
  - [x] 验证 remote control（若保留）

- [x] 7.3 文档同步
  - [x] 更新相关 DeepAgents 架构文档
  - [x] 记录这轮删壳的最终状态

验收标准：
- [x] 聊天主链只剩 DeepAgents 壳
- [x] 旧 Aelin 聊天兼容层被尽可能删净
- [x] 代码体积进一步下降，维护成本进一步降低
