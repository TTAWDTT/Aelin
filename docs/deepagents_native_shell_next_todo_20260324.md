# DeepAgents 原生壳收尾 TODO（后续阶段）

> 目标：在当前“DeepAgents 原生壳 + 能力服务”的基础上，进一步把历史 Aelin 壳彻底退出主链、让前端 Execution Pane 更贴近 DeepAgents run graph，并做一轮最终的规范对齐与文档收束。

---

## 1. 后端：彻底下线 `/aelin/chat*` 聊天壳

- [x] 1.1 找出所有还依赖 `/api/v1/aelin/chat` / `/api/v1/aelin/chat/stream` 的调用方
  - [x] 后端测试（`tests/test_aelin.py` 等）：保留 `/aelin/context` 相关用例，将 `/aelin/chat*` 相关用例改为占位或跳过，避免再真实命中已删除路由。
  - [x] 任何仍然通过 HTTP 调用这两个路由的代码：确认生产代码中不存在此类调用。

- [x] 1.2 将这些调用方迁移到 `/api/v1/deepagents/chat/stream`
  - [x] DeepAgents SSE 协议的端到端验证已经集中在 `test_deepagents_shell.py` 中，作为新的主链路测试。
  - [x] 旧 `/aelin/chat*` 路径不再作为聊天入口进行测试，只保留少量 skip/占位用例记录历史行为。

- [x] 1.3 删除 `/aelin/chat` 与 `/aelin/chat/stream` 路由
  - [x] 从 `backend/app/routers/aelin_chat.py` 中移除这两个 endpoint，仅保留附件上传与 file-memory 内容相关接口。
  - [x] 确认 `backend/app/routers` 中不再有针对 `/aelin/chat*` 的路由定义，聊天主链唯一入口为 `/api/v1/deepagents/chat/stream`。

---

## 2. 后端：精简 Aelin 专用类型与桥接层

> 只删除“确实只为旧壳存在”的类型和字段；仍在 DeepAgents bridge 中真实使用的，可以保留或适度重命名。

- [x] 2.1 清理只服务旧壳的类型
  - [x] 检查 `AelinChatRequest` / `AelinChatResponse` / `AelinToolStep` 的使用点：它们目前仍是 DeepAgents 壳（包括 `/deepagents/chat/stream`、remote control、调试脚本）使用的主 DTO，不再只服务旧 `/aelin/chat*`，因此暂不重命名或删除。
  - [x] 确认不存在“完全未引用”的 Aelin 前缀类型；如后续彻底移除 `/aelin` 命名空间时，可在新的重构波次将这些 DTO 统一重命名为更中性的 `ChatRequest` / `ChatResponse`。

- [x] 2.2 审查 `loop_types.py` 与 `AelinAgentLoopResult`
  - [x] 确认 `AelinAgentLoopResult` 及其相关类型只作为 “DeepAgentsLoopResult → 统一桥接结果” 的薄 DTO，当前仅在 DeepAgents bridge 与测试工具中使用，不再承载第二套 Agent Loop 实现。
  - [x] 搜索 `STOP_REASON_*` 常量的使用点，确认它们只存在于 bridge 和测试中；目前没有完全未引用的常量，因此未做删除。后续如简化 stop_reason 语义，可单独整合或压缩枚举。

- [x] 2.3 清理不再需要的工具策略/壳
  - [x] 审查 `AelinToolPolicy`：当前仅用于限制 DeepAgents 工具调用（总次数 / 写操作次数 / 写工具开关），不再承载旧 Aelin 工具协议逻辑。
  - [x] 确认 `classify_tool_call` 仅根据工具名与 action 判定是否为写操作，不包含 plane/pinchtab 等历史分支；暂未发现多余字段或行为，因此保持现有实现。

---

## 3. 前端：Execution Pane run graph 强化（可选增强）

- [x] 3.1 设计 run graph 内部结构
  - [x] 基于 DeepAgents streaming 事件，定义一个前端内部的 `RunNode` / `RunEdge` 结构（节点 = tool/llm/branch/subgraph，边 = 执行顺序或依赖）

- [x] 3.2 在适配层构建 run graph
  - [x] 在 `traceUtils.ts`（或新模块）中，从 DeepAgents chunk / `tool_runs` 重建一棵 run graph：按时间顺序 + 工具调用分组
  - [x] 保持现有 “工具调用列表” 视图可用，新加一个基于 run graph 的视图作为增强

- [x] 3.3 Execution Pane UI 升级
  - [x] 为 run graph 设计一个轻量可视化（时间线或简单的树），避免过度复杂
  - [x] 支持在 Execution Pane 中切换 “工具列表视图” 与 “run graph 视图”

---

## 4. DeepAgents 规范对齐与机械扫

- [x] 4.1 对照 DeepAgents 最新文档审查 tools 用法
  - [x] 确认所有工具都通过 DeepAgents `tools` 接口注册，不再走任何历史兼容层
  - [x] 确认工具返回结构（`result/summary/error` 等）与 DeepAgents 推荐格式对齐

- [x] 4.2 对照 DeepAgents skills 规范审查 skills 用法
  - [x] 确认所有 skills 都来自 `SKILL.md` 目录（`backend/deepagents_skills/` + `AELIN_DEEPAGENTS_EXTRA_SKILLS_DIR`）
  - [x] 删除已不再需要的旧 skill 兼容层或包装

- [x] 4.3 再次确认记忆只走 `/memory/AGENTS.md`
  - [x] 确认没有任何残留的 DB 记忆 / openviking 路径
  - [x] 确认 MemoryMiddleware 使用的是统一的 AGENTS.md 文件，而不是额外的 “隐性记忆” 源

---

## 5. 文档与 README 最终收束

- [x] 5.1 更新架构文档
  - [x] 在 `docs/deepagents_arch.md` 中补充 “无 `/aelin/chat*` 壳” 的最终形态
  - [x] 在 `docs/deepagents_native_shell_migration_202602-202603.md` 中加一小节说明本轮收尾

- [x] 5.2 标记 legacy API
  - [x] 在 `docs/INDEX.md` 中，把 `/aelin/*` 聊天接口标记为 legacy/兼容接口（或完全移除，如果 1 完成并对外不再暴露）

- [x] 5.3 统一 README 描述
  - [x] 确认 `README.md` / `README.en.md` / `README.zh-CN.md` 都只把 DeepAgents 壳当成主入口，不再提 “Aelin Agent Loop”
