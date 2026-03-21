# DeepAgents Plane & Trace Integration TODOs

> 目标：让 plane / pinchtab 与 DeepAgents 协作自然，右侧链路 UI 直接展示 DeepAgents 的真实运行图，同时逐步收缩旧的规划状态机逻辑。

---

## 1. Plane + DeepAgents 协作（browser / goose / CLI plane）

### 1.1 为 plane 写清晰的 DeepAgents skills

- [ ] 为 browser plane 添加更详细的 skill 说明：
  - [ ] 在 `backend/deepagents_skills/plane_browser/` 中补充：
    - [ ] goal 模板示例（打开页面 + 关注要素 + 输出形式）。
    - [ ] 何时使用 `delegate` / `status` / `continue`。
    - [ ] `state = running / completed / waiting_user` 的解释与推荐下一步。
  - [ ] 添加一两个真实场景例子（如「百度首页要闻总结」），帮助 DeepAgents 学习模式。
- [ ] 为 goose plane 预留 skill 模板：
  - [ ] 在 `backend/deepagents_skills/plane_goose/` 中补充：
    - [ ] goose plane 的目标类型（复杂网站、多步流程、登录+导航+采集）。
    - [ ] 推荐在何种场景下优先 goose 而不是 web_search / browser plane。
- [ ] 为未来 CLI-Anything plane 设计 skill 骨架：
  - [ ] 描述 CLI plane 的通用模式：
    - [ ] 如何构造 goal 以便 plane 能在 CLI 中执行任务。
    - [ ] 适用的任务类型（批量操作、脚本化、自动化）。

验收标准：
- [ ] DeepAgents 在面对复杂网页/站点任务时，倾向用 plane 而不是生硬地 web_search 或 device。
- [ ] 在涉及登录/验证码的任务中，能通过 plane 的 state 正确提示用户「请先在浏览器完成登录」。

### 1.2 让 DeepAgents 主导 plane 任务续上逻辑

- [ ] 检查 `aelin_core._try_agent_loop_chat` 中关于 plane snapshot / forced_tool_runs 的逻辑。
- [ ] 设计更 DeepAgents 风格的续上方式：
  - [ ] 通过 skill 告诉模型：
    - [ ] 如果已有活跃 plane task（同一 plane / workspace / user），优先通过 `plane status` / `continue` 续上。
    - [ ] 只有在明确「另起一个独立目标」时才 `delegate` 新任务。
- [ ] 减少或删除 Aelin 侧对 plane 的强制续上插入（forced_tool_runs）：
  - [ ] 保留仅在「兼容旧行为」必需时的最小桥接逻辑。

验收标准：
- [ ] 对同一 plane 任务（如反复追问某网站信息），DeepAgents 倾向自动续上已有 task，而不是每次创建新 task。
- [ ] 在移除大部分 forced_tool_runs 后，plane 相关测试与真实场景仍可正常完成。

### 1.3 规范「waiting_user」场景的协作模式

- [ ] 在 plane skill 中明确说明：
  - [ ] 当 plane 报告需要用户交互（如验证码、登录）时，应返回 `state` 或类似标记。
  - [ ] DeepAgents 在这种情况下应向用户解释需要的操作，并等待用户确认（例如用户回复「已登录，继续」）。
- [ ] 在 DeepAgents + Aelin 的接口上约定：
  - [ ] 当 plane 返回「waiting_user」或等价状态时：
    - [ ] agent loop 停在 `plane_waiting_user`。
    - [ ] 提示用户在本地浏览器完成操作。
    - [ ] 下一轮对话由用户明确表示已经完成，再继续对该任务调用 `status` / `continue`。

验收标准：
- [ ] 在浏览器请求需要登录/验证码的站点时，链路不会直接失败，而是进入「等待用户完成登录」状态。
- [ ] 用户在完成登录后简单回复（如「已登录，继续」），agent 能正确续上 plane 任务。

---

## 2. DeepAgents Run Graph → Aelin Execution Pane

### 2.1 获取 DeepAgents 的完整 run trace

- [ ] 调研 DeepAgents / LangGraph 提供的 run graph / event API：
  - [ ] 找到从 `agent.invoke(...)` 获取结构化执行节点与边的方式。
  - [ ] 明确可区分的节点类型：模型调用、tool 调用、子 agent、filesystem 操作、summarization 步骤等。
- [ ] 在 `run_deepagents_loop` 中：
  - [ ] 将 DeepAgents run trace 提取到单独的数据结构（例如 `DeepAgentsRunTrace`）。
  - [ ] 保留现有 `trace_steps`（高层阶段）与 `tool_runs`（工具调用），再增加 run graph 细节。

验收标准：
- [ ] 为典型请求打印出的 run trace 能够清晰显示完整步骤，包括子 agent 与 plane 调用。
- [ ] 现有的 `AelinAgentLoopResult` 仍然兼容（新增字段不会破坏旧字段语义）。

### 2.2 将 run trace 映射为更细粒度的 `AelinToolStep`

- [ ] 在 `_try_agent_loop_chat` 中扩展 trace 映射逻辑：
  - [ ] 除了当前的 `result.trace_steps` 与 `tool_runs` 外：
    - [ ] 遍历 run graph 中的关键节点，为每类节点建立对应的 `stage`：
      - [ ] `agent_plan`：高层分析与规划步骤。
      - [ ] `agent_tool`：由 DeepAgents 决定的普通工具调用。
      - [ ] `plane_delegate`：plane 委派开始节点。
      - [ ] `plane_status` / `plane_continue`：plane 状态轮询、继续节点。
      - [ ] `agent_summary`：最终总结生成步骤。
- [ ] 控制 trace 数量与 detail 长度，避免 SSE 负载过大：
  - [ ] 只保留对用户理解有帮助的关键节点信息。

验收标准：
- [ ] 前端右侧 Execution Pane 在常见场景下能清楚展示：
  - [ ] 规划 → 工具 → plane 委派 → plane 状态 → 最终回答 的整体链条。
- [ ] Trace 数量在可接受范围内（不会成为性能瓶颈）。

---

## 3. 瘦身旧规划状态机（转 skill 驱动）

### 3.1 盘点并分类旧规划函数

- [ ] 在 `aelin_core` / `aelin_chat_planning` 中梳理旧规划逻辑：
  - [ ] 找出与工具选择/路由强相关的函数（如 `_plan_tool_usage`, `_critic_tool_plan`, `_build_intent_contract` 等）。
  - [ ] 找出与回答质量验证/grounding 相关的函数（如 `_judge_answer_grounding`, `_check_evidence_coverage`, `_verify_reply_answer`）。
- [ ] 将这些函数按「策略价值」分类：
  - [ ] 必须保留（如强安全约束）。
  - [ ] 可以转 skill（作为模型参照的规则）。
  - [ ] 可以删除或极度简化（已被 DeepAgents 能力替代的部分）。

验收标准：
- [ ] 有一份清晰列表标明每个规划函数的处理方案（保留 / skill 化 / 移除）。

### 3.2 将可转移的策略迁移到 skills

- [ ] 为通用规划规则编写 skill 文档，例如：
  - [ ] 「什么时候优先使用 web_search vs plane vs gws」。
  - [ ] 「如何避免在没有证据时自信回答」。
  - [ ] 「回答中如何引用检索到的关键证据」。
- [ ] 将这些 skill 文档放入合适的 skill 目录：
  - [ ] 如 `backend/deepagents_skills/planning/` 或按实际工具分散到相关 skill 下。

验收标准：
- [ ] 在减弱或移除对应 Python 规划函数后，DeepAgents 在典型任务中仍能做出合理工具选择与回答。
- [ ] skill 文档易读、可修改，不依赖 Python 逻辑更新。

### 3.3 最小化保留的硬规则

- [ ] 为必须保留的少数硬规则保留轻量逻辑，例如：
  - [ ] 当查询是纯媒体 URL 且明显要求总结时，仍然直接走 `media_ingest` 工具流。
  - [ ] 当请求明显是 attachment-only 任务时，可以跳过 DeepAgents，直接用 attachment 工具 + 模板回答。
- [ ] 确保这些硬规则逻辑与 DeepAgents 不冲突：
  - [ ] 可以在进入 DeepAgents 前先执行一部分「确定性路由」，再把剩余问题交给 DeepAgents。

验收标准：
- [ ] 规划相关 Python 代码量显著减少，核心逻辑集中在少数统一入口上。
- [ ] DeepAgents 在大多数场景中成为主要的决策与规划来源。

> 注：现有 Aelin 记忆状态机不再迁移，允许旧记忆直接丢失；
> 未来记忆系统将基于 DeepAgents 的虚拟文件与 memory 能力重新设计，届时另起文档与 TODO，不在本文件范围内。
