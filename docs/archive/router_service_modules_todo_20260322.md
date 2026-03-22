# Routers & Services 模块化重组 TODO（2026-03-22）

该文档是一次中间阶段的结构整理草案，最初放在 `backend/docs/`。

随着 Aelin 继续向“纯 DeepAgents 壳”收缩，这份 TODO 已不再作为当前执行主线，
因此迁移到 `docs/archive/` 作为历史记录保留。

原始内容如下。

---

# Routers & Services 模块化重组 TODO（2026-03-22）

目标：在不破坏现有行为的前提下，让 `app/routers` 和 `app/services` 模块化、分领域，更易读、易维护。重组过程分批进行，每批都要做到：

- 只做「移动 + 过渡 import」，不同时大改逻辑。
- 跑完 `pytest -q` 的核心用例和一两条真实链路（`/aelin/chat/stream`）。
- 清理掉无用的中间层再 commit。

---

## 1. Routers 按领域分包

### 1.1 创建子包结构

- [ ] 在 `app/routers/` 下创建子目录并添加 `__init__.py`：
  - `app/routers/aelin/`
  - `app/routers/core/`
  - `app/routers/integrations/`

### 1.2 Aelin 相关路由归类

- [ ] 将下列文件物理移动到 `app/routers/aelin/`：
  - `aelin.py`
  - `aelin_chat.py`
  - `aelin_context.py`
  - `aelin_device.py`
  - `aelin_remote_control.py`
  - `aelin_web_compat.py`
  - `aelin_text_helpers.py`
- [ ] 在原路径（如 `app/routers/aelin_chat.py`）保留一个薄过渡层：
  - 仅 `from app.routers.aelin.aelin_chat import router` 之类，让旧导入仍然可用。
- [ ] 更新 `app/main.py` 中的路由注册，优先从新子包导入（避免继续引用过渡文件）。

### 1.3 核心系统路由归类

- [ ] 将账号/认证/消息等路由文件移动到 `app/routers/core/`：
  - `accounts.py`
  - `auth.py`
  - `contacts.py`
  - `messages.py`
- [ ] 保留与 1.2 相同风格的过渡层，确保旧导入路径不立即失效。
- [ ] 核心路由在 `app/main.py` 中改为从 `app.routers.core.*` 导入。

### 1.4 外部入口 / 集成路由归类

- [ ] 将外部入口相关路由移动到 `app/routers/integrations/`：
  - `inbound.py`
  - `agent.py`（若仍需要保留 legacy `/agent` surface）
- [ ] 为这些文件同样添加过渡 import 层。

### 1.5 清理过渡层

- [ ] 全局搜索更新后的 import，逐步替换旧路径：
  - 例如从 `app.routers.aelin_chat` → `app.routers.aelin.aelin_chat`。
- [ ] 在确认没有引用后，删除多余的过渡文件（保留清晰的包结构）。

---

## 2. Services/chat 模块化

### 2.1 创建 chat 子包

- [ ] 在 `app/services/` 下创建 `chat/` 子目录并添加 `__init__.py`。

### 2.2 Agent loop & DeepAgents 相关文件迁移

- [ ] 将以下与 chat/agent loop 直接相关的模块移动到 `app/services/chat/`：
  - `aelin_core.py`
  - `aelin_core_support.py`
  - `aelin_context_service.py`
  - `aelin_chat_dispatch.py`
  - `aelin_chat_memory.py`
  - `aelin_loop_types.py`
  - `aelin_runtime.py`
  - `aelin_utils.py`
  - `aelin_tools.py`
  - `aelin_tool_policy.py`
  - `tools_context.py`
  - `tools_device.py`
  - `tools_files.py`
  - `tools_gws.py`
  - `tools_web.py`
  - `deepagents_graph.py`
  - `deepagents_loop.py`
- [ ] 在原路径保留与 routers 类似的过渡导出，确保 `app.services.X` 旧路径短期仍可用。

### 2.3 Memory & Web search 相关文件迁移

- [ ] 将记忆与检索相关模块迁移到 `app/services/chat/`（或 `chat/memory/` 子目录，视复杂度而定）：
  - `agent_memory.py`
  - `agent_memory_utils.py`
  - `file_memory_bridge.py`
  - `web_search.py`
  - `web_search_providers.py`
- [ ] 更新所有引用这些模块的地方为新路径，逐步去掉旧的别名导出。

### 2.4 核心 LLM & summarizer 保持共享

- [ ] 保持下列通用服务在 `app/services/` 根目录（不移动，仅视需要在未来拆 `core/` 子包）：
  - `llm.py`
  - `summarizer.py`
  - `encryption.py`
  - `avatar.py`
- [ ] 确保 chat 包对这些工具的导入统一通过清晰的路径（例如 `from app.services.llm import LLMService`）。

---

## 3. Services/media 模块化

### 3.1 创建 media 子包

- [ ] 在 `app/services/` 下创建 `media/` 子目录并添加 `__init__.py`。

### 3.2 附件处理相关迁移

- [ ] 将附件处理相关模块迁移到 `app/services/media/`：
  - `aelin_attachment_service.py`
  - `attachment_storage.py`
  - `attachment_parsing.py`
  - `attachment_ocr.py`
- [ ] 更新 `aelin_media.py`、`tools_files.py` 等对这些模块的导入路径。

### 3.3 媒体 ingest 相关迁移

- [ ] 将媒体 ingest 相关模块迁移到 `app/services/media/`：
  - `asr_text.py`
- [ ] 检查 `aelin_media.py` 和任何直接使用 MediaIngestService 的代码，更新导入路径。

---

## 4. Services/integrations 模块化

### 4.1 创建 integrations 子包

- [ ] 在 `app/services/` 下创建 `integrations/` 子目录并添加 `__init__.py`。

### 4.2 外部系统 / Bot 相关迁移

- [ ] 将外部集成相关模块迁移到 `app/services/integrations/`：
  - `google_workspace_cli.py`
  - `feishu_bot.py`
  - `qq_bot.py`
  - `remote_control.py`
  - `device_center.py`
  - `model_catalog.py`
  - `oauth_clients.py`
  - `oauth_state.py`
  - `sync_jobs.py`
- [ ] 更新对应 routers（如 `aelin_remote_control.py`、`accounts.py`）中的导入路径。

---

## 5. 清理与验证

### 5.1 逐步移除过渡导出

- [ ] 在完成每一大块迁移后，搜索使用旧路径导入的地方，逐步替换为新路径。
- [ ] 确认没有外部引用后，删除不再需要的过渡文件或别名导出。

### 5.2 测试与真实链路验证

- [ ] 每批迁移后运行至少以下测试：
  - `pytest tests/test_aelin.py -q`
  - `pytest tests/test_api.py -q`
  - `pytest tests/test_media_ingest.py -q`
  - `pytest tests/test_web_search.py -q`
  - `pytest tests/test_remote_control.py -q`

### 5.3 文档更新

- [ ] 在现有 DeepAgents/Aelin 架构文档中更新模块结构示意图，反映新的 `routers` 与 `services` 包布局。
