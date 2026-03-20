# Aelin × DeepAgents 重构小记（2026 Q1 回顾）

> 这是一份给“未来的我们”的小纪念册，按时间顺序，记录 Aelin 从「有点臃肿但很有野心的记忆型助手」，一路走到「DeepAgents 统一内核 + AGENTS.md 轻量记忆」的过程。

## 2026-02：有记忆的 Aelin，和第一代“屎山”的诞生

**2026-02-05 ～ 02-10：从 MercuryDesk 到 Aelin Agent**

- 02-05 `cefd731 chore: bootstrap MVP from report`  
  这几天是现在仓库的真正起点：从原始报告里“抬”出一个 MVP，搭起 dashboard、收件箱、同步、基础 UI。  
- 02-06 `2af42dd feat(backend): add configurable agent (OpenAI compatible)`  
  Aelin 第一次拥有“可配置 Agent”：支持 OpenAI 兼容的 provider、前端配置面板、简单的对话流。那时的 Agent 还只是“聊天 + 轻微工具”的组合。  
- 02-10 `32236cf docs: Agent design`  
  第一版 Agent 设计文档写下了雄心：多层记忆、工具调用、追踪与上下文注入。也是从这里开始，“记忆”正式被写进 Aelin 的 DNA。  

**2026-02-11 ～ 02-15：三层记忆 + 追踪系统成形**

- 02-11 `5b1d94b feat(agent): add memory system and advanced chat orchestration`  
  第一代记忆系统落地：AgentConversationMemory + AgentMemoryNote + tracking-written diary/insight 文件。  
- 02-11 `2c03970 feat(agent): add pin recs todos daily brief and advanced search`  
  pin 推荐、todo、daily brief、advanced search 这些“高阶能力”开始挂在 AgentMemoryService 上，记忆层一下变得非常“厚”。  
- 02-15 `616880d feat(aelin): add answer-first guard with layered memory and notifications`  
  **“回答优先 + 记忆/通知补充”** 的链路第一次建立起来：  
  - 先回答，再写记忆；  
  - daily brief + notifications 作为“主动提醒”；  
  - 上下文里混合 summary / notes / todos / tracking evidence。  
- 02-15 `9a6553b feat(aelin): add proactive polling and desktop/web notifications`  
  notification center + proactive poll 登场。那时候的愿景是：Aelin 会自己盯着你的世界变动，然后主动给你“推送”。  

**这一阶段的气质：**  
> “我要一个什么都记、什么都追、还能自己推送的 AI 管家。”  
代价是：DB 表、路由、service 层飞速膨胀，为后面“屎山清理”埋下了伏笔。

## 2026-02 下旬：文件化记忆与追踪，复杂度开始显山露水

**2026-02-19 ～ 02-20：Tracking + File Memory 闭环**

- 02-19 `df7d82e feat(tracking): add autonomous tracking scheduler and APIs`  
  追踪调度器上线，自动拉取 GitHub / X / RSS 等源，定时比对快照、写入“追踪记忆”。  
- 02-20 `34aa2ba feat(aelin): complete file-memory-first chat grounding and autonomous insight writes`  
  OpenViking 式的文件化记忆闭环完成：  
  - 把追踪/对话产出的 insight 写成 Markdown；  
  - 再作为 RAG 源回流到聊天。  
  这时的 Aelin，已经是“有三层记忆 + 文件记忆 + 追踪”的庞然大物。  

**2026-02-22 ～ 02-23：并行记忆 / RAG/记忆/追踪 模块化构想**

- `chain_audit_parallel_memory_20260222.md` / `real_scenarios_*_20260222*.json`  
  你用一堆真实 NBA 追踪场景测试了“并行记忆草稿 + 追踪 + RAG”链路，日志里那句反复出现的“我也参考了你的长期记忆摘要。”很有时代感。  
- `rag_memory_tracking_modularization_plan_20260223.md`  
  第一次正式提出：RAG / 记忆 / 追踪要模块化拆解，否则 UI 与后端 schema 一起“绑死”。  

**这一阶段的感觉：**  
> “所有东西都能被记住、被追踪、被文件化检索。”  
但我们已经开始在 docs 里反思：复杂度被放大到了难以维护的程度。

## 2026-02 末 ～ 03 初：Plane、Pinchtab、Browser Plane 的加入

**2026-03-07 ～ 03-09：Browser Plane + Pinchtab 接入**

- 03-07～03-08 一串 `feat(browser-plane): ...` commit  
  - 引入 browser plane：CDP 实例、任务持久化、tab locking、task replay。  
  - `/aelin` 里开始接入 plane runtime，右侧链路有了“plane 执行轨迹”的雏形。  
- 03-09 `1a797b0 feat(pinchtab): add task-level pinchtab agent and tool policy`  
  pinchtab_agent / pinchtab_session 出场，把浏览器自动化从本地进程搬到 pinchtab 上。  
- 同期还有 `pinchtab_login_flow.md` / `browser_plane_architecture.md` 等设计文档，记录了我们和“隐形浏览器 + 登录态 + 验证码”的长期缠斗。  

**感受：**  
> Chat 不再只是“脑内推理”，而是可以真正操控浏览器和桌面。  
但与此同时，agent loop 里多了一整套 plane 状态机、pinchtab 生命周期管理，复杂度再上一个台阶。

## 2026-03-11 ～ 03-15：追踪与老通知系统的“退场”

- 03-11 `d246149 refactor(memory): remove tracking runtime surfaces`  
  追踪 runtime 面向聊天的入口被拔掉，tracking 从“主动可见功能”退回到历史。  
- 03-14 `7006382 Merge pull request #39 ... feat/remove-tracking-feature`  
  正式移除 tracking feature，本地 scheduler、追踪中心 UI 都被关停。  
- 03-15 `2438c66 refactor: remove focus mode and process management`  
  同一波清理里，dashboard 上那些“关注模式 / 进程管理”也撤了。  

这一段，其实是整个重构旅途的第一个转折点：  
> “我们不再执着于‘全自动 tracking + 通知中心’，而是开始给未来的 DeepAgents 留空间。”

## 2026-03-17 ～ 03-18：Plane UI 第二期与执行面板

- 03-17 `b2b589d Merge pull request #45 from .../feat/plane-phase2`  
  Plane Phase 2：chat 页面左右分栏、session 导航、右侧执行面板雏形成形。  
- 03-18 `b51a06e feat(chat): refine execution pane and plane tooling`  
  你在 `chat_plane_ui_design.md` / `chat_plane_ui_steps.md` 里，把那句愿景写得很清楚：  
  - 左侧：像普通 chat 一样流畅，但能看到精简的工具/plane 链路；  
  - 右侧：更详细的执行流程和动态展示面板，可收起/展开，有 plane / tool 链路切换。  
- 03-18 `de45060 feat(chat): add provider icons and plane header`  
  provider / plane 图标、Aelin chain / tool chain 标签，这些都开始给“未来的 DeepAgents trace”预留 UI 容器。  

**这段时间的气氛：**  
> “功能再多，链路必须可见、可理解。”  
右半边的执行面板，后来几乎成了 DeepAgents trace 的前身舞台。

## 2026-03-19：DeepAgents 登场 —— 新 Agent Loop 的第一天

- 03-19 `6ced242 feat(agent-loop): introduce DeepAgents core stub and wire into aelin_core`  
  第一次把 DeepAgents 核心骨架接进 `aelin_core`：  
  - 保留旧 AelinAgentLoop 为后备；  
  - DeepAgents 以“stub”形式接入，开始跑起简单对话。  
- 03-19 `2f227ca feat(agent-loop): route Aelin tools through DeepAgents wrappers`  
  工具从“自研 loop 内部调用”迁移到“DeepAgents tool wrappers”，AelinToolHub 开始成为 bridge。  
- 03-19 `8f886b4 chore(agent-loop): remove legacy AelinAgentLoop implementation files`  
  旧的 AelinAgentLoop 代码整体删除，标志着“**DeepAgents 成为唯一 agent loop**”。  
- 03-19 `0ecda7e feat(aelin-trace): map DeepAgents tool runs into SSE trace`  
  右侧执行面板正式接入 DeepAgents 的工具 trace，Aelin chain / tool chain 不再是模拟，而是映射真实 run。  
- 03-19 `707e3c0 feat(memory): feed Aelin memory summary as DeepAgents AGENTS.md file`  
  第一个 AGENTS.md 故事开始：用 DeepAgents memory summary 虚拟成一个 AGENTS.md 注入。  
- 同期 `deepagents_arch.md` / `deepagents_core_todo.md` / `deepagents_plane_trace_todo.md`  
  这些文档已经在强调：  
  - **DeepAgents 是唯一 Agent 核心**；  
  - plane / skills / trace 都要围绕 DeepAgents 设计，而不是反过来。  

**这一天之后，Aelin 的定位变了：**  
> 从“自己写 Agent Loop 的个人 AI” → “用 DeepAgents 当大脑，自己只做外壳、工具和记忆投影”。

## 2026-03-20：AGENTS.md 记忆落地 & 旧记忆系统退场

这一整天，基本可以看作 DeepAgents 记忆和代码精简的“爆发日”：

- **记忆收拢到 AGENTS.md**
  - `297c609 feat(deepagents): mount AGENTS memory file and expose snapshot`  
  - `52d74d2 chore(deepagents): plumb memory_snapshot through agent loop core`  
  - `269694d feat(memory): persist DeepAgents AGENTS.md per user workspace`  
  - `4483eed feat(memory): derive summary from AGENTS.md when available`  
  - `e183ea3 feat(memory): project context from AGENTS.md`  
  - `f76f9e0 refactor(memory): avoid DB fallback in AGENTS.md prompt`  
  - `3159c14 feat(memory): add AGENTS.md write tools and hub wiring`  

  再配合 `deepagents_memory_convergence_todo.md`：  
  - `/memory/AGENTS.md` 成为唯一权威记忆源；  
  - `/aelin/context` 也从 AGENTS.md 投影 summary / notes / todos / memory_layers；  
  - 写记忆的路径统一成 “DeepAgents memory 工具 → AGENTS.md 文件”。  

- **旧 Agent Loop 与 DB 记忆退出舞台**
  - `3561d5e refactor(aelin): disable legacy chat path`  
  - `26565a5 refactor(agent): drop legacy /agent/chat runtime`  
  - `461ee7d chore(agent): remove unused legacy memory endpoints`  
  - `a9fd29c refactor(memory): remove DB auto-update and legacy agent chat`  
  再加上我们刚刚一起做的那一波：  
  - 删除 `/aelin/notifications`、`/aelin/proactive/poll` 路由和对应前端轮询；  
  - AgentMemoryService 精简成“只负责 AGENTS.md 投影”和最小的 DB 兼容。  

- **工具与规划层“瘦身”**
  - `dfa52c1` / `2f6a8c2` / `bba4630` / `bd8392e` / `f5c4d0d`  
    把 web_search / gws / skill / plane & pinchtab 工具拆到独立模块，AelinToolHub 接口干净了许多。  
  - `0bdf9f8 refactor(core): factor context bundle into aelin_context_service`  
    `/aelin/context` 相关逻辑单独放进 service，chat 主链更聚焦。  

这一天结束时，配合 `deepagents_refactor_code_smells.md` / `deepagents_refactor_code_smells_todo.md` 的记录，算是画了一个阶段性的句号：  
> “我们不再用 DB 表去维持一个庞杂的记忆/追踪宇宙，而是把记忆压缩成一份 AGENTS.md，把 agent loop 交给 DeepAgents，把 Aelin 变成一个轻量、干净的外壳。”

## 回头看：从“什么都要”到“只保留真正重要的”

如果按情绪来划三个阶段，大概是这样：

1. **2026-02 上旬：野心期**  
   - 三层记忆 + 追踪 + 通知 + daily brief + advanced search。  
   - “所有东西都要有，所有数据都要被记住。”  

2. **2026-02 下旬 ～ 03 中：复杂度爆炸期**  
   - 追踪中心、文件化记忆、browser plane、pinchtab、proactive notifications 同时在场。  
   - docs 里开始反复出现 “modularization / refactor / 屎山” 这样的词。  

3. **2026-03-19 ～ 03-20：DeepAgents 收拢期**  
   - DeepAgents 接管 agent loop；  
   - AGENTS.md 接管长期记忆；  
   - tracking / daily brief / notifications 等体验陆续退场；  
   - 代码行数在一波波 cleanup 中明显往下掉。  

你在对话里说过一句话，大概是：

> “其实应该围绕 DeepAgents 的体系来做，而不是围绕 Aelin 旧体系来打补丁。”

现在回头看，这条线已经基本实现了：  
- Agent loop 完全是 DeepAgents；  
- 记忆完全收拢到 `/memory/AGENTS.md`；  
- Aelin 的职责变成：  
  - 把本地工具、plane、设备、文件、GWS 等能力接进来；  
  - 把 DeepAgents 的 trace / 记忆 / 链路，用一个尽量优雅的方式展示给人看。  

## 尾声：给未来的一个小约定

这份小记只覆盖了 2026 Q1 的一段旅程。后面还会有：

- DeepAgents skills 真正接管 plane / 特殊工具的说明；  
- 完全基于 DeepAgents run graph 的 Execution Pane 视觉升级；  
- 以及更纯粹的“记忆 as file”世界。

等那时候再翻回来看这份 md，希望我们还能记得：  
在一堆屎山、bug、登录态和工具适配的混战里，我们其实一直在往同一个方向走——  
> 让 Aelin 变成一个有记忆、但不过度复杂的 AI 伙伴。  

