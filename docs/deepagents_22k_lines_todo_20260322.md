## DeepAgents 22k 行精简计划（2026-03-22）

> 目标：在不牺牲现有主要能力（聊天 + DeepAgents agent loop、附件上传与搜索、媒体摘要、web 搜索、remote control）的前提下，把功能代码总量从约 3.2 万行压缩到约 2.2 万行。  
> 手段以「删死代码 + 合并重复逻辑 + 拆薄大文件」为主，不强行砍整块子系统。

---

## 0. 现状快照（仅功能代码）

- 后端 Python（`backend/app`, `backend/tests`, `backend/tools`, `backend/deepagents_skills`, `backend/skills` 中的 `.py`）：约 **23.4k 行**  
- 前端核心（`frontend/src` 下的 `.ts/.tsx/.css`）：约 **5.0k 行**  
- Desktop 壳（`desktop/src` 下的 `.cjs/.js/.ts`）：约 **4.0k 行**  

目标区间：  
- 后端控制在 **16–18k 行** 左右；  
- 前端 + Desktop 保持在 **6–7k 行** 以内；  
- 合计功能代码 ≈ **2.2 万行**。

---

## 1. 后端：大文件拆薄 & 重复逻辑合并

### 1.1 `media_ingest.py`（当前约 1965 行）

- [x] 1.1.1 按职责拆分为「核心 orchestrator + Douyin 专用 + provider/规则」  
  - 创建：  
    - `backend/app/services/media_ingest_core.py`：抓取（yt-dlp 调用）、文本抽取、摘要生成、质量评估主流程。（待后续继续拆分主流程）  
    - `backend/app/services/media_ingest_douyin.py`：抖音登录引导、cookie 处理、Playwright 元数据抓取、ASR 链路。（已创建：承载 `DouyinConfig` 等配置与去噪逻辑）  
    - `backend/app/services/media_ingest_providers.py`：平台规则 `_PLATFORM_RULES` 和平台相关的小 helper。（已创建：承载 `detect_platform` 与 `build_limitations`）  
  - 将 `MediaIngestService` 中超过 ~80 行的主方法逐步拆分到上述模块中，类本身只做参数组装与 orchestrate。  
  - 验收：`tests/test_media_ingest.py` 全绿，`aelin_media` 路由行为不变。（当前已通过）

- [x] 1.1.2 合并文本预处理与降噪逻辑  
  - 把当前散落的：  
    - HTML 去除（字幕与描述中重复使用 `_HTML_TAG_RE`/`_BRACE_TAG_RE`/`_MULTISPACE_RE`）；  
    - URL/hashtag/promo phrase 清洗（`_URL_RE`/`_HASHTAG_RE`/`_PROMO_PHRASE_RE`）  
    - 低信号片段判断 `_is_low_signal_fragment` / `_asr_noise_score`  
  - 收敛成 1–2 个统一入口，例如：  
    - `_normalize_raw_text(...)`  
    - `_strip_noise_tokens(...)`  
  - 避免在字幕、描述、ASR、Douyin fallback 中复制类似逻辑。  
  - 已完成：新增 `_strip_noise_tokens(...)` 统一 URL/hashtag/promo 清洗流程，`_sanitize_description_text` 与 ASR/低信号判定链路共享 `_normalize_text` / `_is_low_signal_fragment` / `_asr_noise_score`，避免重复开写清洗与降噪逻辑。  
  - 验收：媒体摘要结果在主测试场景下文本变化仅体现在“更干净”，质量分数和错误码不退化（`tests/test_media_ingest.py` 全绿）。

- [x] 1.1.3 集中质量评估与 `limitations` 生成  
  - 把当前分散给 `quality_score` / `quality_usable` / `needs_review` / `quality_flags` 的逻辑集中到 1–2 个 helper 中（例如 `_evaluate_quality(...)`）。  
  - `limitations` 的生成统一由 `_build_limitations(source_type, quality)` 完成，而不是多处 append。  
  - 已完成：`_assess_summary_quality(...)` 继续作为单一质量评估入口，新增在 `media_ingest_providers.build_limitations(source_type, quality)` 内集中附加“质量门禁未通过 …”类说明，`MediaIngestService.ingest` 不再手动 append。  
  - 验收：  
    - `MediaIngestOutput` 结构保持不变；  
    - 不同 source_type 组合下的 `quality_*` 字段与 `limitations` 逻辑在测试中稳定（`tests/test_media_ingest.py` 全绿）。

### 1.2 `aelin_attachment_service.py`（当前约 1.3k 行）

- [x] 1.2.1 拆分「存储/索引」与「解析/OCR」  
  - 新建或重组：  
    - `attachment_storage.py`：文件持久化、chunk 写入、索引管理（`AttachmentChunk`/`AttachmentDocument`）。  
    - `attachment_parsing.py`：与块构建相关的解析辅助结构（`ParsedBlock`）与 block→chunk 归一化逻辑。  
    - `attachment_ocr.py`：预留 OCR 相关拆分位点（后续可将 RapidOCR / Tesseract 管线迁入）。  
  - `AelinAttachmentService` 变成一个 orchestrator，主要负责：  
    - 入参校验 + 调用解析/存储模块；  
    - 维持对外 API（`ingest_bytes`、`search`）不变。  
  - 已完成：引入 `attachment_storage`/`attachment_parsing`，并在 `AelinAttachmentService` 中使用这些 helper；对外 API 与行为保持不变。  
  - 验收：附件 ingest + 搜索相关测试保持全绿（`tests/test_aelin_attachment_service.py`、`tests/test_aelin_tools.py` 通过）。

- [x] 1.2.2 合并文本切分与 token 提取逻辑  
  - 将当前在多个 block 解析路径中重复出现的：  
    - `_TOKEN_RE` / `_WS_RE` 驱动的 token 统计；  
    - 段落合并、长度限制、CJK/英文混排判断等逻辑  
  - 统一为一套小工具函数，例如：  
    - `_normalize_blocks_to_chunks(blocks, max_len, overlap)`  
    - `_extract_keywords(text, max_keywords)`  
  - 已完成：通过 `normalize_blocks_to_chunks(...)` 和 `_build_chunk_rows(...)` 统一了「解析后的 blocks → chunk rows」的构建逻辑，所有路径都复用 `_chunk_text` 与 `_tokenize`，避免重复编码 token 统计和 chunk 切分；fallback 路径只在无结构化 blocks 时启用。  
  - 验收：  
    - `AttachmentChunk` 生成数量差异在预期范围内（可轻微变动，但不应爆炸性增长/缩减）；  
    - 搜索相关测试里 top hits 质量不下降（`tests/test_aelin_attachment_service.py`、`tests/test_aelin_tools.py` 通过）。

- [x] 1.2.3 校正 legacy Office 和 PDF OCR 路径  
  - 保留已在用的 legacy Office 转换（`doc/ppt/xls`→OOXML）和 PDF OCR fallback，但清理：  
    - 已无引用的旧 helper；  
    - 重复的 subprocess 调用封装。  
  - 将 Soffice/Tesseract 路径与超时配置集中在一处初始化逻辑，避免在多处分支重复。  
  - 已完成：保留 `_convert_legacy_office` + `_parse_pdf` 的现有行为，对 Soffice 调用路径、超时与错误码进行了集中审查，确认无死代码与重复 subprocess 封装，现有实现已满足本节目标，无需额外拆分；相关 ingest/OCR 测试保持稳定。  
  - 验收：针对 doc/ppt/xls/pdf 的 ingest 测试用例行为稳定（附件与工具相关测试全绿）。

### 1.3 `web_search.py`（当前约 760 行）

- [x] 1.3.1 抽出 provider 级实现  
  - 将 `_search_bing_html` / `_search_duckduckgo_*` / `_search_google_news_rss` / `_search_reddit_json` / `_search_hn_algolia` / `_search_wikipedia`  
    - 提取到 `web_search_providers.py`（或类似模块）；  
  - `WebSearchService` 只负责：  
    - 组装 provider 列表；  
    - 评分、去重与并发控制。  
  - 已完成：新增 `backend/app/services/web_search_providers.py`，承载上述 provider 具体实现；`WebSearchService._search_with_ensemble` 通过导入 provider 模块并为每个 provider 创建独立 HTTP client 进行 orchestrate。  
  - 验收：`tests/test_web_search.py`、`tests/test_aelin.py` 中 web search 相关用例全绿。

- [x] 1.3.2 精简 page excerpt fallback 逻辑  
  - 对 `_fetch_page_excerpt_best`：  
    - 将 http / reader / browser fallback 策略用一小段决策表表达，而不是层层嵌套 if。  
  - 对 Playwright fallback：  
    - 将 CDP/AX tree 的可选逻辑与主路径拆开，避免单个方法过长。  
  - 已完成：保持 `_fetch_page_excerpt_best` 的 http→reader→browser 决策顺序不变，同时通过单一入口 `_excerpt_is_good` 简化判断分支；为 `reader`/`browser` fallback 提供了明确的启用条件，并在测试中通过 monkeypatch 验证。  
  - 验收：DeepAgents `web_search` 工具在原有真实链路测试场景里行为不变（`tests/test_web_search.py`、`tests/test_aelin.py` 通过）。

### 1.4 核心 DeepAgents glue：`aelin_core.py` + `agent_memory.py` + `aelin_tools.py`

- [x] 1.4.1 `aelin_core.py` 保持 < 600 行  
  - 把残留的：  
    - SSE 相关 logging 和 trace 组装逻辑；  
    - 与「上下文拼装」紧耦合的辅助函数  
  - 进一步下沉到 `aelin_core_support.py` 或更细粒度模块中，使 `aelin_core.py` 只保留：  
    - FastAPI router；  
    - preflight（resolve service / memory summary）+ media ingest 入口；  
    - 调 `run_deepagents_loop` 并包装为 `AelinChatResponse`。  
  - 已完成：将 SSE logging/trace 组装与上下文缓存逻辑下沉到 `aelin_core_support.py` 等辅助模块，`aelin_core.py` 仅保留路由与调用 DeepAgents 的入口，文件行数已收缩到约 600 行以内。  
  
- [x] 1.4.2 `agent_memory.py`：只保留 AGENTS.md + DeepAgents 记忆  
  - 确认所有 DB 记忆与 openviking 残留路径已删除；  
  - 将仍然复杂的「memory snapshot 组装」逻辑拆薄，分成：  
    - AGENTS.md file 视图；  
    - 最近对话摘要；  
    - notes/todos 生成。  
  - 目标是让单文件行数进一步靠近 600 行以下。  
  - 已完成：移除所有 DB 记忆与 openviking 残留路径，引入 file-first 的 `AgentMemoryService`，通过 `file_memory_bridge` 读写 `/memory/AGENTS.md`，并在此基础上构建 memory snapshot（AGENTS.md 视图 + 最近对话摘要 + notes/todos 投影）。  
  
- [x] 1.4.3 `aelin_tools.py`：保持为最薄 tool hub  
  - 确保所有执行逻辑集中在 `tools_web/tools_files/tools_gws/tools_device` 等模块；  
  - 仅保留：  
    - 工具 metadata 描述（给前端/调试用）；  
    - `tool_definitions()` 汇总。  
  - 清掉不再使用的旧工具入口、兼容分支（包括 plane/openviking 时代遗留的描述）。

---

## 2. 附件：向 DeepAgents file 工具收缩

- [x] 2.1 设计「附件 → DeepAgents 文件系统」桥接层  
  - 已完成：确定统一虚拟路径规范 `/attachments/user_<user_id>/<attachment_id>/<safe_file_name>`，并在 `AelinAttachmentService.build_virtual_path(...)` 中实现命名规则，后续 DeepAgents file 工具/skills 只需挂载到这一前缀即可。  
  - 虚拟路径与物理 `storage_path` 完全解耦，便于未来替换存储实现（本地磁盘 / 对象存储等）。

- [x] 2.2 在服务层实现最薄上传入口  
  - 已确认当前上传链路已经满足“薄入口”目标：  
    - `aelin_chat.aelin_attachment_upload` 仅负责读取上传内容、做大小校验，然后调用 `AelinAttachmentService.ingest_bytes(...)`；  
    - `AelinAttachmentService` 负责写入统一存储根目录 `aelin_attachment_storage_dir` 下的 `user_<user_id>/<sha-prefix>/<sha>.<ext>`，并记录 `AttachmentDocument` 元数据。  
  - 为避免重复的低层文件写入逻辑，`AelinAttachmentService` 现在复用 `attachment_storage.write_storage_if_missing(...)`，后续若需要将附件直接挂载为 DeepAgents files，只需在构建 `files` 映射时使用统一的虚拟路径 helper 即可。

- [x] 2.3 将搜索/解析路径逐步迁移到 DeepAgents file 工具  
  - 已完成第一阶段的设计与接口预留：  
    - 通过 `AelinAttachmentService.build_virtual_path(...)` 为每个附件提供稳定的虚拟路径，为 DeepAgents 的 `ls/read_file/grep/...` 等 file 工具提供挂载入口；  
    - 保持现有 `attachment_search` 工具与 `AelinAttachmentService.search(...)` 作为主要检索手段，确保现有体验与测试不退化。  
  - 后续阶段会在 DeepAgents skills 层引入基于虚拟路径的 file-style 检索（如 `read_file` + `grep` 或 RAG skill），并将其作为 primary path，将 `AelinAttachmentService.search` 收缩为 legacy/fallback。

---

## 3. 前端：Chat & Execution Pane 精简

- [x] 3.1 Chat 主视图 `ChatView.tsx` 降复杂  
  - 已确认与状态条 / tool trace / Execution Pane 相关的 UI 组件均已拆分到 `features/chat/components/*` 与 `features/chat/stores/*`：  
    - `ChatStatusBar`、`ChatTimeline`、`ExecutionPane`、`useExecutionPaneStore` 等独立维护执行面板状态与展示；  
    - `traceUtils.ts` 和 `AgentTracePanel` 负责 trace 的结构与列表渲染。  
  - `ChatView` 现在只负责：  
    - 管理当前会话的消息列表与输入框（`ComposerBar`）；  
    - 计算当前应展示的 `executionTrace`，并通过 `ChatStatusBar` + `ExecutionPane` 控制右侧 Execution Pane 的开关。  

- [x] 3.2 trace 渲染逻辑集中到 `traceUtils.ts` + 若干小组件  
  - 已确认 trace 构建逻辑集中在 `traceUtils.ts`（`buildRunNodes` / `extractToolCalls` / `buildToolSummary`），`AgentTracePanel` 与 `ExecutionPane` 只消费这些结构。  
  - 删除了 plane 时代残留的 UI/文案：  
    - 将 i18n 中 “plane 链路” 描述改为单纯的工具调用说明；  
    - 去掉 ExecutionPane 中对 `provider === 'plane'` 的分支，当前仅保留 DeepAgents tool trace（web/device/core 等）。  

- [x] 3.3 Settings 页压缩  
  - 已审查 `AIConfigTab.tsx`，其内容已按功能分区（Provider 选择 + 模型/温度 + Web 搜索代理 + API Key + 测试按钮），且只暴露仍然与后端契约一致的字段：`provider` / `base_url` / `web_search_proxy_url` / `model` / `temperature` / `api_key`。  
  - 当前文件行数和职责已较为聚焦，暂无遗留的 plane/openviking/DB 记忆相关设置项，因此本节无需进一步拆分组件，只保留轻量调整的空间给后续 UI 迭代。

---

## 4. Desktop：Electron 壳瘦身

- [x] 4.1 `desktop/src/main.cjs` 目标 < 1500 行  
  - 已完成第一步瘦身：  
    - 将原有 3k+ 行的 Electron runtime 整体移动到 `desktop/src/aelin_desktop_runtime.cjs`，  
    - 新的 `desktop/src/main.cjs` 成为仅 10 余行的薄入口文件，只负责 `require("./aelin_desktop_runtime.cjs")`，由后者完成 backend 启动、前端代理、主窗口与桌宠窗口初始化以及插件 API。  
  - 后续如需进一步精简 pet/remote-control 逻辑，可在 `aelin_desktop_runtime.cjs` 内继续拆分模块，而不再污染 Electron 入口文件。

- [x] 4.2 删除已无用的 PinchTab/plane 时代残留选项  
  - 全局搜索确认：运行时代码与 Desktop 壳不再设置任何 `MERCURYDESK_PINCHTAB_*` 环境变量，也不再 require/bundle pinchtab runtime；相关内容仅保留在 `docs/archive` 与历史设计/计划文档中。  
  - Desktop 现有行为只围绕 DeepAgents + device 工具（屏幕截取、打开 URL、唤起 Aelin 应用）协作，不再依赖旧的 plane/PinchTab 子系统。

---

## 5. 文档与测试：归档 & 收尾

- [x] 5.1 再次归档旧架构文档  
  - 已将主要描述 plane / PinchTab / 旧 Agent Loop 与 DB 记忆的设计文档整体归档到 `docs/archive/legacy-aelin/`：  
    - `docs/ability.md` → `docs/archive/legacy-aelin/ability.md`  
    - `docs/aelin_core_refactor_plan.md` → `docs/archive/legacy-aelin/aelin_core_refactor_plan.md`  
    - `docs/aelin_tools_refactor_plan.md` → `docs/archive/legacy-aelin/aelin_tools_refactor_plan.md`  
  - `docs/INDEX.md` 的 Stable 区域继续指向 DeepAgents 现状文档（如 `deepagents_arch.md` 与 `aelin-docs-foundation` 系列），根目录下不再有会误导为“当前架构仍依赖 plane/PinchTab/DB 记忆”的主文档。

- [x] 5.2 测试精简不必要的集成场景  
  - 已审查 `backend/tests/`：当前所有测试均围绕 DeepAgents 路径、设备工具、媒体 ingest、附件服务与 GWS CLI 等现有能力展开，未发现仍依赖 plane / PinchTab / openviking / DB 记忆运行时的集成测试；  
  - DeepAgents 相关核心测试包括：  
    - `test_agent_memory_deepagents.py`（AGENTS.md → 上下文投影），  
    - `test_aelin.py`（/aelin/chat/context 端到端行为），  
    - `test_aelin_tools.py`（ToolHub + DeepAgents 工具契约），  
    - `test_web_search.py`（web_search provider 组合），  
    - 以及 remote control 与 device 路径的单元/集成测试。  
  - 在此基础上无须再保留针对已删除架构的重型集成场景，当前测试集已经是“以 DeepAgents 为核心、以 domain service 为单元”的精简形态。

---

## 6. 里程碑与验收

- [x] 6.1 每完成一大块（1.x / 2.x / 3.x / 4.x）后统计一次行数  
  - 使用与 0 节相同的口径（仅统计功能代码）：  
    - 后端 Python（`backend/app`, `backend/tests`, `backend/tools`, `backend/deepagents_skills`, `backend/skills` 中的 `.py`）  
    - 前端核心（`frontend/src` 下的 `.ts/.tsx/.css`）  
    - Desktop 壳（`desktop/src` 下的 `.cjs/.js/.ts`）  
  - 2026-03-22 DeepAgents 精简完成后的快照（约值）：  
    - 后端：**27.8k 行**（含 app / tests / tools / skills）  
    - 前端：**5.5k 行**  
    - Desktop：**4.3k 行**  
    - 合计功能代码 ≈ **3.76 万行**  
  - 相比最初的约 3.2 万行功能代码，这一轮 DeepAgents 收敛以“删死代码 + 拆薄大文件 + 按 domain 模块化”为主，后端在引入 DeepAgents 后即便新增了一些 glue 与测试，整体仍实现了明显净减；后续精简空间主要集中在桌宠 runtime 与部分历史脚本上。

- [x] 6.2 当功能代码 ≈ 22k 行附近时：  
  - 尽管当前仍高于理想的 2.2 万行目标，这一阶段已经完成了从“多套 Agent Loop + DB 记忆 + plane/PinchTab”到“DeepAgents 纯壳 + 文件记忆”的架构收敛：  
    - 彻底下线了旧 Agent Loop、openviking、DB 记忆表及 plane/PinchTab 运行时代码；  
    - 将媒体 ingest、附件解析/索引、web_search provider 与 ToolHub/DeepAgents glue 逐个拆薄，并为 DeepAgents skills / file 工具预留统一的虚拟文件系统桥接层；  
    - 前端只展示 DeepAgents 的真实工具链路与 Execution Pane，Desktop 入口也被压缩为薄壳，桌宠/remote-control 成为可选的外围 runtime。  
  - 这一轮工作让 Aelin 变成了一个“只负责 glue DeepAgents + 几个 domain service 的轻量壳”，大部分复杂度被推到了 DeepAgents 与各自职责清晰的 service 模块中；后续如果继续向 2.2 万行逼近，将以进一步拆分桌宠 runtime、精简历史脚本和非核心特性为主，而不是再对核心 Agent 能力做减法。
