# Aelin 答辩问题全集

> 覆盖技术、产品、工程、商业、团队五个维度，附建议回答方向。

---

## 一、技术深度类

### Agent Loop

**Q: Agent Loop 最多跑几轮？默认是几轮？**
> 可配置，默认 `max_rounds=1`，可通过环境变量调高。单轮超时 10s，总超时 12s。

**Q: 工具调用失败或返回错误结果，会怎么处理？**
> 工具结果直接注入上下文，LLM 会基于错误信息继续推理。没有专门的结果校验层，这是已知局限性。如果工具持续失败，Loop 会在"连续两轮无进展"时自动终止。

**Q: 六大工具族是怎么决定调用顺序的？LLM 自主决定还是规则决定？**
> LLM 自主决定调用哪个工具、什么时候调用。策略引擎（`AelinToolPolicy`）只做"准入控制"——检查是否允许调用、次数是否超限、读写分类，不干预顺序。

**Q: 读写分离是怎么实现的？**
> `classify_tool_call()` 对每个工具调用进行分类。读工具（`context_get`、`diary`、`web_search` 等）提交到 `ThreadPoolExecutor` 并行执行；写工具（`profile.append_note`、`tracking.create`、`device.mode_apply`）串行顺序执行。

**Q: 为什么不用 LangChain 或 LlamaIndex 这类 Agent 框架？**
> 第三方框架黑盒多、版本不稳定、定制成本高。自实现的 Loop 对超时、策略、并发有精确控制，整体代码量可控，不引入额外依赖。

---

### 记忆系统

**Q: OpenViking 是什么？是你们自己开发的吗？**
> OpenViking 是一个外部 Python 库，提供语义检索能力。Aelin 通过 `_OpenVikingAdapter` 动态加载，兼容多个版本的 SDK。如果 SDK 不可用，自动回退到本地词法检索，做到功能不断档。

**Q: 本地词法检索的打分逻辑是什么？**
> 三项组合：① query 字符串是否出现在文件中；② 分词后各 token 命中数量（正则 `[A-Za-z0-9_\u4e00-\u9fff]+`）；③ kind 权重（`insights > timeline > snapshots > profile`）。

**Q: insight（洞察）写入有没有去重？会不会反复写同样内容？**
> 目前没有去重策略，这是已知的技术债，在 `openviking_report.md` 中已明确列为"下一步建议"。改进方向是对 insight 标题做语义相似度去重。

**Q: 记忆文件和数据库之间数据一致性怎么保证？**
> 数据库是权威数据源，文件系统是投影副本。如果数据库删除了追踪目标，对应的文件目录不会自动清理。这是当前已知局限，后续会加 GC 机制。

**Q: 記憶会不会无限增长？怎么管理？**
> 有 recency decay 机制，老旧未引用项权重递减。用户可手动删除笔记和调整追踪边界。insight 写入也需经过 LLM 判断 `should_write` 和 `confidence`，不会无脑写入。

---

### 搜索系统

**Q: 七个搜索源同时查，结果怎么合并？重复的怎么处理？**
> 每个结果按 provider 权重 + 排名位置 + 关键词 token 命中三项综合打分，然后 URL 去重、标题去重，合并排序取 Top K。

**Q: 搜索结果的质量怎么保证？万一全是垃圾内容？**
> 内容抓取时有三级质量检测：识别 CAPTCHA/屏蔽页面、检测"请开启 JavaScript"提示、识别 CJK 内容权重。`_excerpt_is_good()` 判断摘要是否有效，不够好才向下一级回退。

**Q: Playwright 无头浏览器会不会很慢？**
> Playwright 是最后兜底方案，只在直接 HTTP 和 Reader API 都失败时才启用。正常情况下大部分结果走 HTTP 抓取，延迟在秒级以内。

**Q: 为什么不用 Google Search API 直接解决？**
> 商业 API 有调用限额且要收费，影响零成本部署的核心设计原则。自建 7 源搜索不依赖任何付费接口，且有三级回退保证高可用性。这也验证了团队在搜索聚合方面的工程能力。

---

### 追踪系统

**Q: 追踪调度器是怎么实现的？用了什么调度框架？**
> 没用第三方调度框架。`TrackingAutonomyService` 自己实现了一个后台线程循环（`_loop` 方法），用 `threading.Event` 做睡眠和唤醒控制，用 `ThreadPoolExecutor`（最多 16 个 worker）并发执行追踪任务。

**Q: 追踪任务失败了怎么办？有重试机制吗？**
> 有指数退避机制，`_max_backoff_seconds` 默认 21600（6小时）。连续错误超过 `_error_threshold`（默认 10 次）后，target 会进入 `paused` 状态，不再调度，等待用户手动恢复。失败时会写入失败快照到文件系统。

**Q: 追踪最小间隔是多少？能追很高频的数据吗？**
> 最小间隔 `_min_interval` 默认 30 秒，最大 86400 秒（1天）。URL 类型默认 180s，关键词类型默认 120s。这个设计考虑了对目标网站的礼貌请求，不做高频爬取。

**Q: 追踪变更检测的原理是什么？怎么判断"有变化"？**
> `_diff_changes()` 方法对比前后两次抓取的 `payload` 字典，检测字段级别的 new/update/remove 变化。变更事件按 `_severity()` 评分分级，写入 `timeline/*.md`。

**Q: 支持哪些平台的追踪？**
> Connector 类型：X/Twitter、微博、Bilibili、抖音、小红书、RSS。通用类型：任意 URL（HTTP 抓取）、关键词（搜索引擎）。共计 8 种来源类型。

---

### 工程与架构

**Q: 为什么选 SQLite？多用户场景能扩展吗？**
> 当前定位是个人助手，SQLite 零依赖、易部署、无需额外服务。数据库层已有 `user_id` 隔离设计，迁移 PostgreSQL 只需换 `DATABASE_URL`，业务逻辑不需要改。

**Q: 并发安全怎么保证？SQLite 有写锁问题吗？**
> 追踪调度器有专门的 SQLite 重试机制：`_sqlite_retry_attempts` 默认 4 次，`_sqlite_retry_base_delay_seconds` 默认 0.15s 指数退避。同时用 `threading.Lock` 保护共享的调度状态。

**Q: Electron 打包后多大？启动速度怎么样？**
> （需提前实测数据）Electron 打包含 Chromium 内核，一般在 150-300MB 区间。启动速度取决于是否同时启动后端进程，通常 3-8 秒。

**Q: 后端用了 FastAPI 的哪些高级特性？**
> Depends 依赖注入（用户认证、DB 会话）、StreamingResponse（流式聊天）、APIRouter 模块化路由、Lifespan 事件管理（启动/关闭追踪调度器）、自定义中间件（CORS）。

**Q: 流式聊天是怎么实现的？**
> 使用 FastAPI 的 `StreamingResponse` + SSE（Server-Sent Events）格式，`_sse_event()` 封装事件格式。前端通过 `EventSource` 或 `fetch` with `ReadableStream` 接收流式输出。

---

## 二、产品与设计类

**Q: 目标用户是谁？**
> 有持续关注特定领域信息需求的个人用户：研究人员、投资者、内容创作者、重度信息消费者。核心痛点是"需要跨时间追踪某个话题的变化"。

**Q: 和 Notion AI、Obsidian AI 插件比有什么优势？**
> Notion/Obsidian 是笔记工具加了 AI，需要用户手动管理信息。Aelin 是 AI 原生 + 自动追踪，用户不需要手动整理，系统自动采集、自动沉淀 insight，越用越了解你。

**Q: 和 Perplexity、Kimi 比有什么区别？**
> Perplexity/Kimi 是无状态的即时搜索问答，每次都从零开始。Aelin 有持续积累的追踪记忆，能引用"上周你追踪的 X 仓库更新了什么"，这是 Perplexity 做不到的。

**Q: 用户怎么知道哪些信息是从记忆来的，哪些是实时搜索来的？**
> 回答中包含 citation（引用）系统，`AelinCitation` 标注来源类型（file_memory/web/tracking）。前端可以呈现来源标记，让用户区分证据类型。

**Q: 隐私怎么保证？数据会上传到哪里吗？**
> 全部数据本地存储（SQLite + 文件系统），不上传任何第三方服务器。敏感字段可选 Fernet 加密，密钥完全由用户持有。唯一的网络请求是调用用户自己配置的 LLM API（OpenAI/Anthropic 等）。

**Q: 为什么叫 Aelin？**
> 古诺斯语，意为"火炬"。寓意：在信息洪流中为用户点亮方向，持续照明而不只是一闪而过。

---

## 三、工程完成度类

**Q: 有没有写测试？覆盖率多少？**
> 后端有 pytest 测试套件，前端有 vitest 单测。（需提前跑一下 `pytest -q` 和 `npm test` 确认通过情况，准备具体数据）

**Q: 项目现在能跑吗？有没有 Demo 数据？**
> 可以现场演示。建议提前准备好：已有追踪历史的 workspace、已有对话记录的账号、几个有代表性的追踪目标。

**Q: 代码里为什么还有 MercuryDesk 字样？**
> 项目从 MercuryDesk 演进重命名为 Aelin，数据库名（`mercurydesk.db`）和环境变量前缀（`MERCURYDESK_`）是历史遗留的技术债，正在逐步清理。核心业务逻辑已全部以 Aelin 命名。

**Q: 项目用了哪些开源许可证需要注意的依赖？**
> 主要依赖：FastAPI（MIT）、SQLAlchemy（MIT）、React（MIT）、Electron（MIT）、httpx（BSD）、Playwright（Apache 2.0）。均为开源友好许可证，无商业限制问题。

**Q: 部署难度如何？普通用户能自己装吗？**
> Electron 打包后是一键安装包（NSIS），普通用户可以直接安装。需要用户自行配置 LLM API Key（OpenAI/Anthropic 等）。后端作为独立二进制一起打包，无需用户安装 Python。

---

## 四、扩展与未来类

**Q: 未来有没有计划支持多用户 / 团队协作？**
> 数据库层已有 `user_id` 和 `workspace` 隔离设计，为多用户预留了扩展空间。当前版本聚焦个人场景，多用户需要在认证和数据隔离上进一步完善。

**Q: 连接器怎么扩展？第三方能接入吗？**
> 所有连接器实现统一的 `Connector` Protocol（`fetch_new_messages` 接口），新增数据源只需实现这个接口，返回标准化的 `IncomingMessage`。可以开放 SDK 让第三方接入。

**Q: 有没有想过开源？**
> 项目文档（`project-transition-playbook.md`）中已有 4 周开源打包计划：稳定化 → 边界定义 → 核心抽取 → 公开发布。计划提取 `md-connectors-core`、`md-sync-engine` 等为独立 SDK。

**Q: RAG 有没有考虑过？**
> 当前的文件记忆系统本质上已经是"可写 RAG"——追踪内容写入 Markdown 文件，LLM 回答时检索注入上下文。如果后续接入向量数据库，`insights/*.md` 可作为高权重语料层直接使用。

**Q: 桌面宠物和 AI 助手功能有什么实质联系？**
> 宠物情绪引擎感知用户工作状态（CPU 使用率、空闲时间、深夜检测），而 Aelin 的 Agent 也通过 `device` 工具感知设备状态。两者共享同一套设备感知数据，宠物是 Agent 状态的可视化映射。

---

## 五、团队与项目管理类

**Q: 团队几个人？分工怎么样？**
> （根据实际情况准备）

**Q: 项目开发了多长时间？**
> （根据实际情况准备）

**Q: 遇到的最大技术挑战是什么？**
> 建议回答：追踪调度器的并发控制 + SQLite 写锁处理——多个追踪任务并发写数据库时容易死锁，最终通过指数退避重试 + 线程级别的 source 并发限制（`_source_workers`）解决。

**Q: 如果重来，你会做哪些不同的决定？**
> 建议回答：早期应该先定好 OpenViking 的接口规范再写适配层，而不是边调 SDK 边兼容多版本。另外 MercuryDesk → Aelin 的命名迁移如果在更早期做会更干净。

---

## 六、刁钻细节类（高概率被追问）

| 问题 | 答案 |
|------|------|
| `_TOKEN_RE` 正则是什么？ | `[A-Za-z0-9_\u4e00-\u9fff]+`，匹配英文单词和中文字符 |
| kind 权重排序？ | insights > timeline > snapshots > profile |
| 追踪最小间隔？ | 30 秒（可配置） |
| 追踪默认间隔？ | URL 类型 180s，关键词类型 120s |
| 文件记忆默认返回几条？ | `openviking_query_limit` 默认 8，可配到 12 |
| Agent Loop 默认几轮？ | 1轮，可配置 |
| 单轮超时多少？ | 10 秒 |
| 总超时多少？ | 12 秒 |
| 全局追踪 worker 数？ | 最多 16 个（`tracking_global_max_workers`） |
| 数据库文件名？ | `mercurydesk.db`（历史遗留名） |
| 环境变量前缀？ | `MERCURYDESK_` |
| insight 写入条件？ | LLM 输出 `should_write=true` 且 `confidence` 达标 |
| 追踪错误阈值？ | 连续 10 次失败后 target 进入 paused 状态 |
| 最大退避时间？ | 6 小时（21600 秒） |
| 支持哪些 LLM？ | 任意 OpenAI 兼容 API（OpenAI、Anthropic、本地模型等） |
