# DeepAgents 终态清理 TODO

> 本文档用来跟踪将 Aelin 精简为“纯 DeepAgents 壳”的最后一轮大扫除。只有全部打勾后，才视为完成。


## 1. 记忆：彻底只剩 DeepAgents / AGENTS.md

- [x] 删除 DB 记忆模型：从 `backend/app/models.py` 中移除 `AgentConversationMemory`、`AgentMemoryNote` 及相关关系字段。
- [x] 清空 DB 记忆读写路径：从 `backend/app/services/agent_memory.py` 中删掉所有对 `AgentConversationMemory`、`AgentMemoryNote` 的 DB 级操作，只保留 AGENTS.md 读写和只读投影。
- [x] 清理所有调用 DB 记忆的业务代码：在 `backend/app/services/aelin_core.py`、`backend/app/services/aelin_context_service.py`、`backend/app/services/aelin_tools.py` 等处，改成只依赖 `AgentMemoryService` 的 AGENTS.md 视图，不再 import / 使用 DB 记忆模型。
- [x] 完全移除 openviking：从 `backend/requirements.txt`、`backend/app/settings.py`、`backend/app/services/openviking_bridge.py`、`backend/app/services/openviking_utils.py`、以及所有 `file_memory_bridge` 调用中，改为 DeepAgents/StateBackend 或简单文件 IO；然后删除整个 openviking 适配层和配置项。
- [x] 确认 `/memory/AGENTS.md` 是唯一“权威记忆源”：在 docs 中明确写出 “记忆 = DeepAgents 虚拟文件 + AGENTS.md，DB 中不再存储任何长期记忆或会话摘要”。

## 2. 工具：彻底统一为 DeepAgents 工具层

- [x] 确认 Agent Loop 中不再存在任何 “手搓工具 planner”：在 `backend/app/services/aelin_core.py` 中搜索并删除所有基于 query 自己决定先用哪个工具的逻辑，保证工具调用只来自 DeepAgents 图（`run_deepagents_loop` → `build_chat_agent` → `build_chat_tools`）。
- [x] 将所有仍在用的能力型工具都收口到 `tools_*.py` + `build_chat_tools`：确保 web_search / attachments / GWS / device / screen_get 及以后新增工具，全部通过 `backend/app/services/tools_*.py` + `backend/app/services/deepagents_graph.py` 暴露，而不是在别处再造壳。
- [x] 把 `AelinToolHub` 压缩为“最薄壳”：在 `backend/app/services/aelin_tools.py` 中移除所有执行逻辑，只负责注入上下文 + 暴露 OpenAI-style 描述给前端/调试；执行统一走 `tools_*.py`。
- [x] 在 docs 中明确写清：工具契约由 DeepAgents 工具描述决定，Aelin 不再维护第二套 planner 或签名。

## 3. Skills：彻底 DeepAgents 化 & 接入方法明确

- [x] 固化 skills 目录结构：以 `backend/deepagents_skills/` 为唯一技能入口，移除旧的与 Agent Loop 强耦合的 skills 目录或说明，将 plane/pinchtab 相关 skill 整体归档或删除（见第 4 点）。
- [x] 补一份简短的 `docs/deepagents_skills_guide.md`：说明“如何新增一个 skill、目录结构、DeepAgents 如何自动挂载 skill 文件到 files/memory”，给未来你自己和别人看。
- [x] 确认 `build_chat_agent` 中对 skills 的挂载完全按照 DeepAgents 官方推荐写法，不再额外包一层 Aelin 特有逻辑。

## 4. plane / PinchTab：彻底从运行时和认知中消失

- [ ] 删除剩余的 pinchtab / plane 常量与配置：从 `backend/app/settings.py` 等处移除 `_PINCHTAB_EXE` 及 plane/pinchtab 相关配置常量。
- [ ] 删除或归档 plane/pinchtab skills：把 `backend/skills/pinchtab/`、`backend/deepagents_skills/plane_browser/` 等与 plane/pinchtab 强相关的 skill 目录和 README 要么整体移入 `docs/archive/`，要么直接删除（取决于你是否还想作为历史文档保留）。
- [ ] 全局搜索 `pinchtab`、`plane`：确保在代码、配置、提示词、文档中不再出现任何会误导 DeepAgents 或未来维护者“这里还有 plane”的痕迹；仅允许在 `docs/archive/` 中出现。
- [ ] 更新能力总览文档：在 `docs/*` 里明确声明 plane/pinchtab 已下线，当前浏览/remote-control 能力只通过 device 工具 + 其他 DeepAgents 能力提供。

## 5. 代码体量：大文件彻底瘦身到 DeepAgents 风格

- [ ] 按行数列出所有 > 600 行的 Python 文件：重点关注 `backend/app/services/aelin_core.py`、`backend/app/services/aelin_chat_planning.py`、`backend/app/services/media_ingest.py`、`backend/app/services/openviking_bridge.py`、`backend/app/services/aelin_attachment_service.py` 等。
- [ ] 对仍然需要的逻辑进行“纯拆分、不改行为”的模块化：把上述大文件拆成多个职能清晰的小模块（例如 `aelin_chat_planning_web.py` / `aelin_chat_planning_offline.py`），确保单文件控制在 ~600 行以内。
- [ ] 删除不再需要的“历史路径”逻辑：在拆分过程中，抓住机会删除那些已经被 DeepAgents 完全替代、且不再会通过任何 API 走到的分支，保证不是“把屎山拆成好几块”，而是真正减法。
- [ ] 在 docs 里补一句约定：Agent/工具/记忆相关的 service 文件应尽量保持在 600 行以内，超出时必须先考虑拆分或删旧逻辑。

