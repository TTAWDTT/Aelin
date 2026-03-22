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

- [ ] 1.2.2 合并文本切分与 token 提取逻辑  
  - 将当前在多个 block 解析路径中重复出现的：  
    - `_TOKEN_RE` / `_WS_RE` 驱动的 token 统计；  
    - 段落合并、长度限制、CJK/英文混排判断等逻辑  
  - 统一为一套小工具函数，例如：  
    - `_normalize_blocks_to_chunks(blocks, max_len, overlap)`  
    - `_extract_keywords(text, max_keywords)`  
  - 验收：  
    - `AttachmentChunk` 生成数量差异在预期范围内（可轻微变动，但不应爆炸性增长/缩减）；  
    - 搜索相关测试里 top hits 质量不下降。

- [ ] 1.2.3 校正 legacy Office 和 PDF OCR 路径  
  - 保留已在用的 legacy Office 转换（`doc/ppt/xls`→OOXML）和 PDF OCR fallback，但清理：  
    - 已无引用的旧 helper；  
    - 重复的 subprocess 调用封装。  
  - 将 Soffice/Tesseract 路径与超时配置集中在一处初始化逻辑，避免在多处分支重复。  
  - 验收：针对 doc/ppt/xls/pdf 的 ingest 测试用例行为稳定。

### 1.3 `web_search.py`（当前约 760 行）

- [ ] 1.3.1 抽出 provider 级实现  
  - 将 `_search_bing_html` / `_search_duckduckgo_*` / `_search_google_news_rss` / `_search_reddit_json` / `_search_hn_algolia` / `_search_wikipedia`  
    - 提取到 `web_search_providers.py`（或类似模块）；  
  - `WebSearchService` 只负责：  
    - 组装 provider 列表；  
    - 评分、去重与并发控制。  
  - 验收：`tests/test_web_search.py`、`tests/test_aelin.py` 中 web search 相关用例全绿。

- [ ] 1.3.2 精简 page excerpt fallback 逻辑  
  - 对 `_fetch_page_excerpt_best`：  
    - 将 http / reader / browser fallback 策略用一小段决策表表达，而不是层层嵌套 if。  
  - 对 Playwright fallback：  
    - 将 CDP/AX tree 的可选逻辑与主路径拆开，避免单个方法过长。  
  - 验收：DeepAgents `web_search` 工具在原有真实链路测试场景里行为不变或稍更稳（不再陷入过多无效 fallback）。

### 1.4 核心 DeepAgents glue：`aelin_core.py` + `agent_memory.py` + `aelin_tools.py`

- [ ] 1.4.1 `aelin_core.py` 保持 < 600 行  
  - 把残留的：  
    - SSE 相关 logging 和 trace 组装逻辑；  
    - 与「上下文拼装」紧耦合的辅助函数  
  - 进一步下沉到 `aelin_core_support.py` 或更细粒度模块中，使 `aelin_core.py` 只保留：  
    - FastAPI router；  
    - preflight（resolve service / memory summary）+ media ingest 入口；  
    - 调 `run_deepagents_loop` 并包装为 `AelinChatResponse`。  

- [ ] 1.4.2 `agent_memory.py`：只保留 AGENTS.md + DeepAgents 记忆  
  - 确认所有 DB 记忆与 openviking 残留路径已删除；  
  - 将仍然复杂的「memory snapshot 组装」逻辑拆薄，分成：  
    - AGENTS.md file 视图；  
    - 最近对话摘要；  
    - notes/todos 生成。  
  - 目标是让单文件行数进一步靠近 600 行以下。

- [ ] 1.4.3 `aelin_tools.py`：保持为最薄 tool hub  
  - 确保所有执行逻辑集中在 `tools_web/tools_files/tools_gws/tools_device` 等模块；  
  - 仅保留：  
    - 工具 metadata 描述（给前端/调试用）；  
    - `tool_definitions()` 汇总。  
  - 清掉不再使用的旧工具入口、兼容分支（包括 plane/openviking 时代遗留的描述）。

---

## 2. 附件：向 DeepAgents file 工具收缩

- [ ] 2.1 设计「附件 → DeepAgents 文件系统」桥接层  
  - 在 docs 中补一份短设计：  
    - 上传后的附件在工作区内映射到统一前缀路径（例如 `/attachments/<user>/<attachment_id>/<filename>`）；  
    - DeepAgents 的 file 工具/skills 只认这套虚拟路径。  

- [ ] 2.2 在服务层实现最薄上传入口  
  - 保持当前 FastAPI 附件上传 API，但实现上只负责：  
    - 将原始文件写入统一存储路径；  
    - 记录最小必要元数据（文件名/大小/MIME）。  
  - 后续解析、搜索尽可能交给基于文件的工具/skills。

- [ ] 2.3 将搜索/解析路径逐步迁移到 DeepAgents file 工具  
  - 为常见任务（“帮我找附件里的某段内容”）优先通过 DeepAgents file 工具实现：  
    - 如 skill 中的 `read_file` + `grep` 组合；  
    - 或未来基于文件的 RAG skill。  
  - `AelinAttachmentService.search` 逐步演变为仅对旧数据和 fallback 提供支持。

---

## 3. 前端：Chat & Execution Pane 精简

- [ ] 3.1 Chat 主视图 `ChatView.tsx` 降复杂  
  - 把与状态条 / tool trace / Execution Pane 相关的 UI 组件进一步拆到 `features/chat/components/*`，  
  - `ChatView` 只保留：  
    - 输入框 + 消息列表；  
    - 右侧 Execution Pane 布局开关。  

- [ ] 3.2 trace 渲染逻辑集中到 `traceUtils.ts` + 若干小组件  
  - 确保 trace 树构建和 UI 渲染解耦，减少重复的 “flatten trace / 挑选 tool steps” 逻辑。  
  - 删除所有 plane/pinchtab 时代残留结构判断，只保留 DeepAgents tool trace。

- [ ] 3.3 Settings 页压缩  
  - `AIConfigTab.tsx` 按分组拆出小组件（provider 选择 + 工具权限 + 超参），减少单文件行数。  
  - 去掉已不再对应后端行为的旧设置项。

---

## 4. Desktop：Electron 壳瘦身

- [ ] 4.1 `desktop/src/main.cjs` 目标 < 1500 行  
  - 将 pet/remote-control 相关逻辑尽量挪到独立模块（已有 `pet-*` 文件可进一步利用）；  
  - `main.cjs` 只负责：  
    - 启动 backend；  
    - 创建主窗口；  
    - 简单 IPC/菜单事件。  

- [ ] 4.2 删除已无用的 PinchTab/plane 时代残留选项  
  - 再次确认：  
    - 不再设置任何 `MERCURYDESK_PINCHTAB_*` 环境变量；  
    - 不再 require/bundle pinchtab runtime。  
  - 保证 desktop 架构文档明确只描述 DeepAgents + device 工具的交互。

---

## 5. 文档与测试：归档 & 收尾

- [ ] 5.1 再次归档旧架构文档  
  - 将与 DB 记忆 / plane / openviking 相关、已经不再对当前代码有指导意义的说明移动到 `docs/archive/legacy-*`。  
  - 保证 `docs/` 根下的主要文档全部指向 DeepAgents 现状。

- [ ] 5.2 测试精简不必要的集成场景  
  - 在保持回归覆盖的前提下，优先将 “针对已经删除架构” 的复杂集成测试改为更薄的单元测试，减少维护成本和噪音。  
  - 确保新的 DeepAgents 路径（记忆 / 工具 / agent loop）有清晰的核心测试。

---

## 6. 里程碑与验收

- [ ] 6.1 每完成一大块（1.x / 2.x / 3.x / 4.x）后统计一次行数  
  - 使用同样的度量方式（Python + ts/tsx/css + cjs/js/ts），记录在本文件末尾。  

- [ ] 6.2 当功能代码 ≈ 22k 行附近时：  
  - 回顾本文件，对照打勾项，确认没有因为精简引入明显体验倒退；  
  - 补一份短总结（可以追加到本 md 底部），记录本次 DeepAgents 22k 行收敛的整体路径。
