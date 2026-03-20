# `media_ingest.py` 精简与重构待办清单

> 说明：本文件只包含待办项和验收标准，详细背景可结合 `docs/deepagents_refactor_code_smells.md` 中 B1 条目一起阅读。

## 目标

- 保持现有对外行为和 API 不变（包括 `MediaIngestService`、`MediaIngestOutput`、`MediaIngestError`、`aelin_media_pipeline` 相关逻辑、以及 `tests/test_media_ingest.py` 全部用例）。
- 在不引入新依赖的前提下，最大程度减少 `media_ingest.py` 内部屎山：
  - 收紧职责边界（抓取 / 预处理 / 评分 / 生成摘要）。
  - 删除真正未被调用的 helper。
  - 合并明显重复的逻辑分支。
- 为未来按平台拆分（Douyin / 通用视频 / 纯文本等）预留清晰边界。

---

## M1. 基线梳理与行为锁定

- [x] **M1-1 列出现有对外入口与关键数据流**
  - 操作：
    - 在本文件或 `deepagents_refactor_code_smells.md` 中简要列出：
      - `MediaIngestService` 的公开方法签名及其职责（例如 `ingest_url` / `ingest_with_raw_text` 等，名称以实际代码为准）。
      - 与 `aelin_media_pipeline.py` 的调用关系（如何从 `MediaIngestOutput` 转成最终 chat 文本）。
    - 用注释或简单架构图标记「输入是什么、输出是什么、中间主要阶段有哪些」。
  - 验收标准：
    - 任意新开发者阅读本 TODO 就能在 3 分钟内说清楚：
      - 「谁在调 `MediaIngestService`？」
      - 「成功路径和错误路径分别长什么样？」

- [x] **M1-2 用测试锁定当前行为**
  - 操作：
    - 在每一批重构之前，至少能稳定跑通：
      - `backend/tests/test_media_ingest.py`
      - 任意一个调用 media ingest 的上层集成测试（若有）。
    - 记录一份当前测试通过的基线（例如在本文件中追加一小节“当前基线于 2026-03-?? 验证”）。
  - 验收标准：
    - 在整个重构过程中，始终保证上述测试用例保持通过，无新增 `xfail` / `skip`。

---

## M2. 内部 helper 审计与删除死代码

- [x] **M2-1 枚举 `media_ingest.py` 内部所有 `def _xxx` helper**
  - 操作：
    - 使用 `rg "def _" media_ingest.py` 或等价方式，列出所有私有 helper 名称。
    - 根据调用链（`rg` / 简单搜索）标记每个 helper 是：
      - 「主流程使用」
      - 「仅 tests 使用」
      - 「完全未使用」
  - 验收标准：
    - 本文件或附带笔记中，有一份明确的 helper 列表和使用情况标注。

- [x] **M2-2 删除完全未使用的 helper 与常量引用**
  - 操作：
    - 逐个删除标记为「完全未使用」的 `_xxx` helper 以及相关常量引用。
    - 每次删除后运行：`tests/test_media_ingest.py`。
  - 验收标准：
    - 删除后 `tests/test_media_ingest.py` 依旧全绿。
    - `rg` 确认这些 helper 名称已不再出现在代码中（仅可出现在历史文档中）。

- [ ] **M2-3 合并重复或高度相似的文本预处理逻辑**
  - 操作：
    - 找出用于：
      - 文本清洗（去 HTML / 标签 / 多余空格等）。
      - 口癖/推广语过滤（如 `_PROMO_PHRASE_RE` 等）。
      - URL / hashtag / timecode 清理。
    - 若存在高度相似或重复的逻辑片段，合并为统一 helper，减少复制粘贴代码。
  - 验收标准：
    - 代码中用于文本预处理的函数数量明显减少，命名清晰（例如 `_clean_raw_text` / `_strip_noise_tokens` 等）。
    - 测试中涉及文本清洗/质量评分的用例行为不变（通过断言结果文本保持一致或更合理）。

---

## M3. 按职责切分大函数与状态

- [ ] **M3-1 切分“抓取 / 解码 / 预处理 / 摘要生成”四个阶段**
  - 操作：
    - 找出 `MediaIngestService` 中「超长」的核心方法（行数明显 > ~80 行）。
    - 将其内部逻辑按阶段拆解到私有 helper，例如：
      - `_fetch_media_and_metadata(...)`
      - `_extract_or_transcribe_text(...)`
      - `_score_and_filter_candidates(...)`
      - `_build_llm_prompt_and_call(...)`
    - 确保每个 helper 仅依赖必要的参数，尽量少用/不用实例字段以外的全局状态。
  - 验收标准：
    - 任意一个核心方法行数显著下降（目标：< 80 行）。
    - 阅读新拆出来的 helper 名称即可大致理解该阶段的职责。

- [ ] **M3-2 收紧 Douyin 特定逻辑的边界**
  - 操作：
    - 将 Douyin 专用逻辑集中在一处或少数 helper 中，例如：
      - `_prepare_douyin_cookies_and_login(...)`
      - `_transcribe_douyin_audio(...)`
    - 避免 Douyin 相关细节散落在多个分支中。
  - 验收标准：
    - 搜索 `douyin` 时，主要逻辑集中在有限几个 helper 内，主流程只见少量高层调用。
    - Douyin 相关测试（若有）全部通过，行为与当前保持一致。

- [ ] **M3-3 将质量评分与“可用性”判定逻辑集中**
  - 操作：
    - 把质量评分与 `quality_usable` / `needs_review` 等字段设置逻辑集中在一个或少数 helper 中，例如 `_evaluate_quality_and_flags(...)`。
    - 保持评分算法不变，仅改为统一入口，避免不同分支分别更新同一字段导致行为难以理解。
  - 验收标准：
    - 质量相关字段的赋值路径更清晰（例如只在一两个 helper 中集中处理）。
    - 测试里涉及质量分数 / 标志位的用例行为保持一致。  

---

## M4. 为未来模块化拆分做准备（可选）

- [ ] **M4-1 设计“按平台拆分”的目标结构草图**
  - 操作：
    - 在本文件中追加一小节，草拟未来可能的文件拆分方式，例如：
      - `media_ingest_core.py`：通用抓取 + 文本预处理 + LLM 总线。
      - `media_ingest_douyin.py`：Douyin 特定登录 / cookie / ASR 逻辑。
      - `media_ingest_generic_video.py`：通用视频站点的处理规则。
    - 暂不真正拆分文件，只确保当前 `MediaIngestService` 内部调用关系与该草图保持一致方向。
  - 验收标准：
    - 草图足够清晰，未来若要拆文件，只需“搬运 helper + 更新 import”，无需重新理解业务逻辑。

- [ ] **M4-2 标记潜在的跨模块依赖与风险点**
  - 操作：
    - 在草图中标记：
      - 依赖 `settings` / 外部程序（如浏览器 / ffmpeg 等）的地方。
      - 与其他 service（如 `LLMService` / `ASRTextProcessor` / web 代理等）的耦合点。
    - 为未来可能的抽象接口（例如 “任意 ASR 后端”）预留 TODO 备注。
  - 验收标准：
    - 新人在阅读草图时可以快速知道“哪些部分是 IO-heavy / side-effect-heavy，哪些部分是纯计算”。

---

## M5. 收尾与文档更新

- [ ] **M5-1 更新 `deepagents_refactor_code_smells.md` 与相关文档**
  - 操作：
    - 将本次 `media_ingest.py` 的精简结果在 `deepagents_refactor_code_smells.md` 对应 B1 条目中做简要总结。
    - 如有必要，补充一份“媒体 ingest 链路架构图”（可放在 `docs/media_ingest_*.md` 文件中）。
  - 验收标准：
    - 文档中的描述与最新代码结构保持一致，没有继续引用已删除的 helper 或旧路径。

- [ ] **M5-2 代码风格与可读性最终检查**
  - 操作：
    - 对 `media_ingest.py` 做一次整体阅读，检查：
      - 命名是否统一、表达职责是否清晰。
      - 是否存在明显的长函数 / 深嵌套分支仍未处理。
    - 如有必要，做少量收尾重构并再次跑 `tests/test_media_ingest.py`。
  - 验收标准：
    - 你主观认为 `media_ingest.py` 已从“屎山”变为“高复杂度但结构清晰的模块”，后续可以在局部迭代中继续优化，而不需要一口气“大手术”。
