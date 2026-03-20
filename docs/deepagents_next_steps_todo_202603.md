# DeepAgents 下一步强化 TODO（2026-03 版）

> 目标：在当前“DeepAgents 唯一 Agent Loop + AGENTS.md 唯一长期记忆”基础上，继续收拢代码、提升可用性，让 Aelin 变成一个真正**围绕 DeepAgents 体系**运转的轻量外壳。

## 1. 记忆彻底收拢到 `/memory/AGENTS.md`

- [x] 列出 `AgentMemoryService` 中仍然访问 DB 的记忆路径（notes/todos fallback、并行 draft 记日志等），在文档中标记计划“保留兼容”或“完全移除”。
- [x] 将 `list_notes` / `list_todos` 的 DB fallback 行为改为可选：默认仅从 AGENTS.md 投影，DB 仅在显式 debug/迁移模式下访问。
- [x] 去掉并行记忆草稿 `_save_parallel_draft_entry` 对 DB notes 的写入，让并行记忆只写入文件化 insight 或 AGENTS.md。
- [x] 补充 2–3 个集成测试：重复对话 + memory 工具写入后，AGENTS.md 内容和 `/aelin/context` 的 summary/notes/todos/memory_layers 一致。
- [x] 更新 `deepagents_memory_convergence_todo.md`，标记“DB 记忆弱化/清理”相关项为已完成或调整后的新目标。

验收标准：  
- 所有长期记忆相关读写路径都可以通过 AGENTS.md 完成；  
- DB 记忆表中不再有“自动写入”的路径，仅保留明确标注的调试/迁移场景；  
- `/aelin/context` 在无 DB 的极简环境中也能正常工作。  

## 2. Skills 作为 DeepAgents 的一等公民

- [x] 设计一个统一的 skill loader，将当前本地 SKILL 目录映射为 DeepAgents skills（包含名称、描述、参数约定）。
- [x] 在 DeepAgents graph 配置中，将这些 skills 作为 `skills=[...]` 明确挂载，而不是依赖 prompt 拼接说明。
- [x] 为 plane、文件工具、Google Workspace 等重要技能撰写规范化 skill 描述：适用场景、副作用、风险提示。
- [ ] 添加 1–2 组 E2E 场景测试（例如 GWS 写文档 / 读文件再总结），验证仅依赖 skill 描述，DeepAgents 也能自然选择合适工具。

验收标准：  
- DeepAgents 的 agent 定义中，skills 列表清晰可见，且覆盖核心工具；  
- prompt 中不再出现大段“技能使用说明”硬拼字符串；  
- 在典型 skill 场景中，切换 provider 后 DeepAgents 仍能成功完成任务。  

## 3. 用 DeepAgents Run Graph 驱动 Execution Pane

- [x] 在 `deepagents_loop.py` 中以 `trace_steps` + `tool_runs` 形式规范化 DeepAgents run trace 结构，供上层统一消费。
- [x] 在 `aelin_core._try_agent_loop_chat` 中集中完成从 run trace → `AelinToolStep[]` 的映射，并通过 SSE 推送给前端。
- [x] 前端右侧 Execution Pane 仅消费 `tool_trace: AelinToolStep[]`，通过 `traceUtils` 解析 plane / tool 链路，不再依赖旧 agent loop 的 trace 类型。
- [x] 更新 plane 链路解析逻辑，支持 `plane_delegate` / `plane_status` / `plane_continue` 等阶段，确保 plane tab 能正确显示 DeepAgents 下的 plane 链路。

验收标准：  
- SSE 推送的工具链路完全来自 DeepAgents 的 `trace_steps` + `tool_runs` 结构，不再依赖旧 agent loop；  
- 同一请求在多次运行中的链路差异，能从 run trace 中直观看出（包括 plane 续上 / 工具 retry 等）；  
- 前端 Execution Pane 删除对 legacy trace 的依赖，仅围绕 `AelinToolStep[]` 与 `traceUtils` 工作。  

## 4. 让 plane 真正“DeepAgents 化”

- [ ] 明确列出当前 browser/goose/CLI/pinchtab plane 的入口、状态机和 Aelin 侧 glue 逻辑（包括 `should_resume_active_plane_for_query` 一类函数）。
- [ ] 为 browser plane 写一份 DeepAgents 风格的交互手册：open → status 轮询 → continue → 登录/验证码 handshake → 结果总结。
- [ ] 在 DeepAgents 内部为 plane 续上逻辑增加 middleware 或子 agent，让“是否复用任务/如何续上”主要由 DeepAgents 决定，Aelin 只做少数防呆 guard。
- [ ] 设计一个“需要登录”的标准流程：DeepAgents 说明需要用户操作 → `device.open_url` 打开可见浏览器 → 用户完成登录并回复“已登录，继续” → plane 任务 `continue` 接上。
- [ ] 为至少 2 个真实场景（如“百度首页要闻总结”“登录后查看某站点数据”）录制完整链路日志，并确认 plane 与 DeepAgents 协作自然无卡顿。

验收标准：  
- 典型浏览任务中，DeepAgents 会自发选择 plane 并合理使用 delegate/status/continue，而不是 Aelin 硬编码连续调用；  
- 对同一 plane 任务的追问，会优先续上已有 task，而不是每次创建全新任务（在日志中可见复用行为）；  
- 登录/验证码场景下，用户能在可见浏览器中完成动作，Aelin 负责把状态传回 DeepAgents，整条链路对用户透明易懂。  

## 5. Provider 兼容性与错误体验强化

- [ ] 扫描当前可配置的模型提供商（OpenAI / DeepSeek / Minimax 等），记录各自对 tool-calling / streaming 的支持差异。
- [ ] 在 `deepagents_loop` 中为“模型不支持工具调用 / provider 未配置 / 超时”等情况设计统一的错误返回结构，包含可读的 `stop_reason` 与 trace 步骤。
- [ ] 更新 `/aelin/chat` 路由，将上述错误结构转换为清晰的用户可见提示（例如“当前模型不支持工具调用，请在设置中切换到 X”）。
- [ ] 为每个主流 provider 配置一套最小测试场景：纯聊天 / web_search / plane / GWS / memory 工具写入，确保在 DeepAgents 下都能跑通或给出明确错误说明。

验收标准：  
- 切换 provider 后，常见错误（不支持 tools / key 未配置 / 超时）都会以统一方式反映在 `tool_trace` 和最终回答中；  
- 在前端不会再出现“模型声称调用了工具，但后端实际没有 tool_calls”的迷惑状态；  
- 至少 3 个 provider 上都有一条“从设置 → 聊天 → 工具调用”的完整演练记录。  

## 6. 文档与 Legacy 体验清理（DeepAgents 视角）

- [ ] 按照 `aelin_deepagents_journey_202602.md` 的时间线，盘点 docs 里仍提到 tracking / daily brief / notifications / 旧 agent loop 的章节。
- [ ] 更新 `architecture-status.md`，明确当前唯一 Agent Loop = DeepAgents、唯一长期记忆 = `/memory/AGENTS.md`，并将已移除体验放入“历史”或“archive”区域。
- [ ] 在 `frontend_rebuild.md` 中，删掉或标记 `/aelin/notifications`、`/aelin/proactive/poll`、老 tracking 中心、memory 视图等已退场模块。
- [ ] 为 DeepAgents 视角单独写一份简短“开发者入门”：从 `/api/v1/aelin/chat` 到 DeepAgents graph，再到 AGENTS.md 与 Execution Pane 的完整链路。

验收标准：  
- 新开发者只看 DeepAgents 系列文档和 `architecture-status.md` 就能理解当前架构，不会再被历史 tracking/通知/旧 memory 误导；  
- docs/ 中涉及旧 agent loop、tracking、通知中心的主要篇章要么被归档到 `docs/archive/`，要么显式标注“legacy”；  
- README 级别文档里，对“有记忆的 Aelin”的描述已经调整为基于 DeepAgents + AGENTS.md 的新实现。  
