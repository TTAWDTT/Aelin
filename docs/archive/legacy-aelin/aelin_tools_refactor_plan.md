# AelinToolHub 拆分与精简方案（draft）

本文件用于完成 TODO 中 A3-1 的“为 ToolHub 设计模块划分方案”。

## 现状概览

- 入口：`backend/app/services/aelin_tools.py`
- 聚合职责：
  - Web 检索与抓取（`web_search`、`crawl4ai_*` 等）
  - Google Workspace via `gws` CLI（`google_workspace` 及其子 action）
  - 浏览器 plane / PinchTab 系列（`plane`、`pinchtab`、`pinchtab_agent`、`pinchtab_session`）
  - 文件与附件（`attachment_search` / file-memory 相关工具）
  - skill 工具（基于 `skill_loader` 的 skill prompt/call）
  - 设备与屏幕（`device`、`screen_get`）

文件体积接近 2000 行，所有 `_tool_xxx` 内联在一个类中，维护和认知成本都偏高。

## 拆分目标

1. 保持外部行为完全不变：
   - `AelinToolHub.execute(name, args)` 的调用面保持不变；
   - `tool_definitions()` 暴露的工具集合不变；
   - 所有工具相关测试继续全绿。
2. 按 domain 拆到独立模块，使每个模块聚焦单一责任，便于后续扩展和重构。
3. `AelinToolHub` 自身只承载：
   - ToolHub 构造（依赖注入：db、user_id、workspace、memory_service、web_search_service 等）；
   - 工具注册与路由（从各 domain 模块加载定义，并委托执行）。

## 拆分模块设计（草案）

以下命名为建议，可在实现时微调：

- `app/services/tools_web.py`
  - 职责：
    - `web_search` 工具的实现（search / search_and_fetch 封装）。
    - Crawl4AI 相关工具（如存在 `crawl4ai_fetch` / `crawl4ai_extract` / `crawl4ai_deep_crawl`）。
  - 对外：
    - `get_web_tools(hub: AelinToolHub) -> dict[str, Callable[[dict], dict]]`

- `app/services/tools_gws.py`
  - 职责：
    - 统一封装 `google_workspace` 及其子 action（runtime/auth_status/gmail_list/gmail_get/drive_list/calendar_list/docs_create 等）。
    - 处理 `gws` CLI 的路径、auth 状态、错误转换。
  - 对外：
    - `get_google_workspace_tools(hub: AelinToolHub) -> dict[str, Callable[[dict], dict]]`

- `app/services/tools_browser_plane.py`
  - 职责：
    - `plane` 工具（browser plane 委派）；
    - PinchTab 低层工具（`pinchtab`）；
    - PinchTab agent/session 高层封装（`pinchtab_agent`、`pinchtab_session`）；
    - 与 `pinchtab_client` / `pinchtab_runtime` 的 glue。
  - 对外：
    - `get_browser_plane_tools(hub: AelinToolHub) -> dict[str, Callable[[dict], dict]]`

- `app/services/tools_files.py`
  - 职责：
    - `attachment_search` 与 file-memory 查询工具；
    - 可能还包括简单的文件读取/索引辅助工具（如存在）。
  - 对外：
    - `get_file_tools(hub: AelinToolHub) -> dict[str, Callable[[dict], dict]]`

- `app/services/tools_skill.py`
  - 职责：
    - 基于 `skill_loader` 封装的 `skill` 工具（读取 skill prompt / skill catalog 等）。
  - 对外：
    - `get_skill_tools(hub: AelinToolHub) -> dict[str, Callable[[dict], dict]]`

- `app/services/tools_device.py`（可选）
  - 职责：
    - `device` 工具（remote control / device_center glue）。
    - `screen_get` 工具（屏幕截图/观测）。
  - 对外：
    - `get_device_tools(hub: AelinToolHub) -> dict[str, Callable[[dict], dict]]`

## AelinToolHub 重构草案

重构后的 `AelinToolHub` 将：

- 在 `__init__` 中保持当前依赖注入签名不变；
- 新增一个私有方法 `_load_domain_tools()`：
  - 依次从上述模块调用 `get_*_tools(self)`；
  - 合并为内部的 `self._tools: dict[str, Callable[[dict], dict]]`；
- `tool_definitions()`：
  - 从 `self._tools` 构造工具定义列表（名称 + description）；
- `execute(name, args)`：
  - 将 `name` 归一化为小写；
  - 在 `self._tools` 中查找对应 callable 并执行；
  - 保持 error 处理/日志逻辑与当前实现一致。

## 渐进式迁移策略

1. **第一阶段（web domain）**
   - 先抽取 web_search 相关逻辑到 `tools_web.py`，验证：
     - `tests/test_aelin_tools.py` 中 web_search 用例；
     - `tests/test_web_search.py`；
   - 确认无行为变化后再处理下一个 domain。

2. **第二阶段（Google Workspace）**
   - 抽取 gws 相关 `_tool_google_workspace` 的实现；
   - 验证 GWS tests（`tests/test_aelin_tools.py` 中的 gws 用例、`tests/test_skill_loader.py` 的 gws skill 行为）。

3. **第三阶段（browser plane + PinchTab）**
   - 抽取 plane / PinchTab 系列工具；
   - 重点回归：
     - plane / PinchTab 工具 tests；
     - browser plane 实际链路（通过真实链路或已有集成测试）。

4. **第四阶段（files / skill / device）**
   - 逐 domain 抽取剩余工具；
   - 每完成一个 domain 的迁移就跑一次工具和 chat 相关测试。

## 验收要点

- 所有迁移完成后：
  - `backend/app/services/aelin_tools.py` 行数明显下降（目标：< 600 行），内部主要是：
    - ToolHub 类；
    - 各 domain module 的注册调用；
    - 少量跨 domain glue。
  - 工具行为完全兼容：
    - `tests/test_aelin_tools.py`、`tests/test_aelin_tool_policy.py`、涉及工具的 chat 用例全部通过；
    - DeepAgents 通过 `AelinToolHub.tool_definitions()` 暴露的工具名称及语义不变。

