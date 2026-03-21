# Chat 主界面与 Plane / Tool 联动设计草案

> 目标：让 Aelin 的 Chat 主界面自然承载「LLM 本体 + 原子工具 + plane（外部 agent 系统）」三层能力，同时保持单页、扁平、黑白灰风格，不显得复杂但又能在需要时看清楚内部链路。

## 1. 能力分层心智模型

- **Level 1：Aelin 本体（LLM）**  
  负责理解用户需求、规划步骤、决定是否调用工具或 plane。对用户而言，这是「对话对象」。

- **Level 2：Tools / MCP（原子工具）**  
  各种小螺丝刀：截图、打开 URL、本地文件、gws 子命令等。它们由 Aelin 决定何时调用，不直接暴露给用户操作。

- **Level 3：Planes（外部 agent 系统）**  
  类似 Pinchtab、未来的 gws plane 等完整系统，可以独立规划和执行一系列操作。Aelin 在这一层的角色是「老板 / 秘书」：把任务打包交给 plane，监督进度，最后审阅输出。

UI 上需要明确表达这三层：谁在派活、谁在干活、谁在拿工具。


## 2. Chat 视图总体布局（左右分栏 / 窄屏上下）

在现有「左侧 NavRail」基础上，Chat 主区域改为**左右分栏**：

- **宽屏布局**：
  - 左侧主栏：**Chat Pane**
    - 普通对话时间线（消息气泡）。
    - 精简版工具/plane 调用信息（小 chip + 一行 summary）。
  - 右侧副栏：**Execution Pane**
    - 详细的工具调用链路。
    - 各 plane 的内部步骤、状态流。
    - 动态展示面板（未来可挂 Pinchtab / GWS 等特定可视化）。
  - 右侧 Execution Pane 可以整体收起/展开：
    - 默认展开（桌面场景）。
    - 收起时仅保留一个细窄的“执行面板”tab 区或图标。

- **窄屏布局（如窗口较窄 / 移动场景）**：
  - **上半部分**：Chat Pane（占主视野）。
  - **下半部分**：Execution Pane（默认折叠，只在需要时展开）。
  - 展开 Execution Pane 时，通过动画自下而上滑出，可覆盖部分 chat 区域。

在任意布局下，都保持：

- Chat Pane = 用户与 Aelin 的主视图（对话 + 轻量 trace 提示）。  
- Execution Pane = 需要时才看的“深度调试视图”（详细步骤 / plane 链路 / 动态面板）。


## 3. 左侧 Session 与 Plane 的联动

### 3.1 Session 行的小标记

为每个 session 增加极简状态标记：

- **Plane 偏好图标**：表示此会话最近使用的 plane（例如 Pinchtab / GWS），用统一风格的小 icon / 色块（不是大 logo）。  
- **进行中任务点**：当该 session 下存在进行中的 plane 任务时，在行右上角显示一个小点（淡淡的呼吸动画）。

联动规则：

- 当 Aelin 在某个 session 中首次委派 plane 任务时：  
  - 为该 session 记录 `preferred_plane`，更新左栏图标；  
  - 如果任务处于进行中，显示进行中小点。
- 当 plane 任务全部完成或被取消：  
  - 小点渐隐，只留下 plane 类型标记。

### 3.2 选中 Session 时的 Plane 状态更新

当用户在左侧切换 session：

- Plane 状态带自动切换到该 session 的 `preferred_plane`，并显示最近一次 plane 任务摘要。  
- 右侧 Plane Trace 面板默认切换到与该 plane 相关的视图（Pinchtab / GWS 等）。


## 4. Chat Pane：任务 Chip 与精简调用链

### 4.1 任务 Chip（Plane 委派）

在 Chat Pane 的时间线中，当 Aelin 决定把某条消息委派给 plane 时：

- 在该用户消息下方插入一个 **任务 chip**，内容示例：  
  `Aelin → Pinchtab · 进行中…` / `Pinchtab 完成 · 查看结果`
- Chip 上展示：  
  - plane 标记（小 icon）；  
  - 简短任务标题（例如「抓取 X 关注列表」）；  
  - 状态（进行中 / 完成 / 失败）。

交互（Chat Pane 视角）：

- 点击任务 chip：  
  - 如果 Execution Pane 已展开：右侧 Plane Trace 自动跳转到对应 plane 的任务节点；  
  - 如果 Execution Pane 已收起：先展开 Execution Pane，再跳转。  
  - 对话时间线可选地滚动到与此任务强关联的最近 Aelin 回复，并做轻微背景高亮。

### 4.2 Chat Pane 中的精简调用链

Chat Pane 只展示**精简版调用链摘要**，而不是所有 step 细节：

- **执行阶段**：在时间线顶部或输入框上方显示一条细 status bar，例如：  
  `正在调用工具… Pinchtab · web_search · gws`  
  - 当前执行的工具名称高亮，其余灰显。

- **最终回复生成完毕后**：  
  - status bar 自动折叠成一句话摘要：  
    `本轮调用了 3 个工具（Pinchtab，gws，device），详情见执行面板。`  
  - 提供一个小「查看执行详情」按钮：
    - 点击后展开 Execution Pane（如当前为收起状态）；  
    - 并在 Execution Pane 中滚动到本轮调用链的位置。

原则：

- Chat Pane 保持轻量：只告诉“有哪些工具/plane 参与了本轮任务”；  
- 调用顺序、每步状态、错误信息等详细内容全部放在 Execution Pane 中查看。


## 5. 工具 / Plane 的视觉身份（provider 图标与分组）

为保持整洁而不花哨，引入 **provider 级别** 的视觉身份：

- 为每个工具 / plane 定义一个 `provider`：  
  - `google`（对应 gws、gmail、drive 等 Google Workspace 工具）  
  - `pinchtab`（浏览器 plane）  
  - `aelin-core`（Aelin 内建 atomic tools）  
  - `other-mcp` 等。

- 每个 provider 分配统一的简约图形：  
  - 不直接抄官方 logo，而用几何 + 色块简化成一套系统：  
    - `google`：四色小块或四色环；  
    - `pinchtab`：小蟹 + tab 轮廓；  
    - `aelin-core`：单色点阵或方块。

- 这些 provider 图标用于：  
  - 左栏 session 行的小标记；  
  - 中间任务 chip 的前缀；  
  - Trace 调用列表的前缀。

这样用户能一眼看出「谁在干活」，同时 UI 不会变成「Logo 展示墙」。


## 6. Plane 内部链路展示（Pinchtab / GWS）

Plane 自身也是 agent，有自己的 internal loop，需要一个「内部监控视图」。

### 6.1 Plane Trace Tab

在右侧 Trace 面板中，为 plane 增加一个专门的 tab：

- Tab 分组示意：  
  - `Aelin 链路`：展示 Aelin 自己的 plan / tool_calls（现有 trace）。  
  - `Plane 链路`：展示当前 plane 的内部步骤（Pinchtab / GWS 等）。  
  - `工具调用`：所有 atomic 工具调用的汇总视图。

- 当 plane 任务进行中时：  
  - `Plane 链路` tab 自动高亮；  
  - 列出简化步骤：  
    - Pinchtab 示例：  
      - Step1: 打开 x.com  
      - Step2: 填写登录表单  
      - Step3: 跳转到关注列表  
      - Step4: 抓取关注数据  
    - GWS 示例：  
      - Step1: 列出今天的 Calendar 事件  
      - Step2: 读取目标文档  
      - Step3: 写入新的笔记

- 当用户点击任务 chip 或 Plane 状态带时：  
  - Plane 链路 tab 自动切到对应任务，并滚动到当前步骤位置。

### 6.2 与 Pinchtab 自身 UI 的关系

不在 Aelin 内嵌 Pinchtab 的完整 UI，而是：

- 用 plane trace 告诉用户「Pinchtab 正在做哪些高层动作」；  
- 提供一个「在 Pinchtab 中查看」按钮：  
  - 打开 Pinchtab 自己的 dashboard / 浏览器窗口（由 Pinchtab 负责渲染）；  
  - Aelin 只提供跳转，不强行 iframe / 镜像。

这样既尊重 Pinchtab 作为独立系统，又让 Aelin 一侧有足够的监督信息。


## 7. 输入区模式开关与 Plane / Tool 行为

在底部输入区上方增加两颗轻量开关：

- **模式开关：普通对话 / 委派 plane**  
  - 默认是普通对话。  
  - 切到「委派 plane」时：  
    - Plane 状态带轻微高亮一次，提示“这条消息会作为任务派给当前 plane”；  
    - 发送后必然生成一个 plane 任务 chip，并进入 Plane 链路视图。

- **工具开关：允许运用工具（on/off）**  
  - 默认开启。  
  - 关闭时：Aelin 对这一轮请求不主动使用工具（只用 LLM），Trace 顶部出现一条浅浅提示「工具已禁用」。

联动规则：

- 在已有 plane 任务进行中时：再次「委派 plane」会把消息追加到同一任务，Plane 链路里多一条 step，而不是创建新任务。


## 8. 渐进式落地顺序（建议）

为了避免一次性大改，可以按以下顺序分批实现：

1. **基础 plane 显示与任务 chip**  
   - 在 ChatTimeline 中加任务 chip；  
   - 在 Trace 面板加 Plane tab；  
   - 任务 chip ↔ Plane tab 点击联动。

2. **工具调用链的自动折叠**  
   - 现有 AgentTrace 调用链顶部增加“本轮调用 summary bar”；  
   - 最终答复完成后自动折叠，可手动展开。

3. **Session 小标记 + Plane 状态带**  
   - 左栏 session 行增加 plane 图标 & 进行中小点；  
   - 选中 session 时 Plane 状态带自动切换；  
   - 状态带点击可过滤 trace。

4. **Plane 内部链路显示（Pinchtab / GWS）**  
   - 从 Pinchtab / GWS 返回结构中抽象出 steps 数组；  
   - Plane 链路 tab 渲染这些 steps 为简化流水线；  
   - 提供“在 plane 中查看”链接。

5. **输入区模式开关**  
   - 增加「普通 / 委派 plane」「工具 on/off」两颗开关；  
   - 接入 agent loop 的参数，使得开关真正影响调用策略。

这一套落地完，Chat 主界面会自然地呈现出：

- 会话 → plane → 工具 的清晰分层；  
- plane 是真正可以「派活并监督」的一等公民；  
- 工具链和 plane 内部链路在执行阶段可见，结束后优雅退场。
