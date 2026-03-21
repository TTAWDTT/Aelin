# Chat Plane UI 改造任务清单（TODO + 验收标准）

> 目标：实现「左/上 Chat Pane + 右/下 Execution Pane」的统一界面结构，让 plane/tool 链路在 UI 中既精简又可深入展开。  
> 本文只列待办项与验收标准，不包含具体实现细节。

---

## 阶段一：布局框架与 Pane 容器

- [x] 1.1 建立 Chat / Execution 两个顶层 Pane 容器
  - [x] 验收：在 Chat 主页面组件中（现有 ChatView），中部区域被划分为两个逻辑部分：
    - [x] `Chat Pane`：承载消息时间线和输入区；
    - [x] `Execution Pane`：承载工具/plane 链路视图。
  - [x] 验收：Pane 容器的拆分不改变现有路由结构（仍为单页 Chat），不引入新的页面。

- [x] 1.2 宽屏布局：左右分栏
  - [x] 验收：在宽屏（例如宽度 ≥ 1024px）下，Chat Pane 固定在左侧，Execution Pane 固定在右侧：
    - [x] Chat Pane 宽度优先，占据约 60–70%；
    - [x] Execution Pane 占据余下宽度。
  - [x] 验收：左右布局在切换 session 或刷新时保持稳定，不抖动、不闪烁。

- [x] 1.3 窄屏布局：上下堆叠
  - [x] 验收：在窄屏（例如宽度 < 1024px）下，改为：
    - [x] Chat Pane 在上，占主视野；
    - [x] Execution Pane 在下，默认折叠，只在展开时占据部分高度。
  - [x] 验收：从宽屏缩窄到窄屏时，Pane 的切换不会破坏当前会话内容（消息保持可见，Execution Pane 的状态也被保留）。

- [x] 1.4 Execution Pane 的收起 / 展开机制
  - [x] 验收：无论宽屏还是窄屏，Execution Pane 都支持显式的“折叠/展开”操作：
    - [x] 折叠时，仅保留一条窄区域或按钮（例如右侧/下方的小 tabs/图标），点击可展开；
    - [x] 展开时，有平滑的过渡动画（宽度/高度的渐变）。
  - [x] 验收：折叠状态下仍能通过 Chat Pane 里的“查看执行详情”按钮展开 Execution Pane。

---

## 阶段二：Chat Pane 内容与交互（任务 chip + 精简调用链）

- [x] 2.1 任务 Chip（plane 委派）
  - [x] 验收：当 Aelin 在某轮对话中委派了 plane 任务（例如 browser plane）：
    - [x] 在对应用户消息下方插入一个任务 chip；
    - [x] chip 文案至少包括 plane 名称（或简短标记）与当前状态（进行中/完成/失败）。
  - [x] 验收：点击任务 chip 时：
    - [x] 若 Execution Pane 收起，则先展开；
    - [x] 然后在 Execution Pane 中跳转到该 plane 任务对应的视图（例如 Plane Trace 里定位到此任务）。

- [x] 2.2 Chat Pane 顶部/底部的精简调用链状态条
  - [x] 验收：当本轮对话中存在工具/plane 调用时，Chat Pane 中出现一条精简 status bar，例如：
    - [x] 执行中：`正在调用工具… Pinchtab · web_search · gws`；
    - [x] 已完成：`本轮调用了 3 个工具（Pinchtab，gws，device），详情见执行面板。`
  - [x] 验收：status bar 内有一个「查看执行详情」入口：
    - [x] 点击后展开 Execution Pane（如当前为折叠）；
    - [x] 并在 Execution Pane 内聚焦到当前轮的执行详情。

- [x] 2.3 Chat Pane 轻量原则
  - [x] 验收：Chat Pane 不再铺开所有工具调用步骤：
    - [x] 不在消息流中重复渲染每次工具调用的详细信息；
    - [x] 工具错误/状态细节统一由 Execution Pane 展示，Chat Pane 只给出简短摘要。

---

## 阶段三：Execution Pane 内容结构（工具 / plane 视图）

- [x] 3.1 Execution Pane 内的视图分组
  - [x] 验收：Execution Pane 内部至少区分三个视图（可以是 tabs 或分段）：
    - [x] `Aelin 链路`：展示 Aelin 自己的 plan/tool_calls（现有 trace 的升级版）；
    - [x] `Plane 链路`：展示当前 plane（如 browser/pinchtab）的内部步骤；
    - [x] `工具调用`：展示 atomic 工具调用的列表视图。
  - [x] 验收：默认视图选择逻辑：
    - [x] 若当前轮有 plane 委派，则默认高亮 `Plane 链路`；
    - [x] 否则默认停留在 `Aelin 链路`。

- [x] 3.2 工具调用详情视图
  - [x] 验收：在 `工具调用` 视图下：
    - [x] 能看到本轮所有工具调用的列表（按时间顺序）；
    - [x] 每条包括：provider 图标、工具名、状态（完成/失败）、简短结果/错误摘要。
  - [x] 验收：从 Chat Pane 的 status bar 或任务 chip 跳转过来时：
    - [x] 能定位到对应轮次的调用列表，并高亮相关条目。

- [x] 3.3 Plane 链路视图（以 browser plane 为首个实现目标）
  - [x] 验收：在 `Plane 链路` 视图中：
    - [x] 对于当前活跃/最近的 plane 任务，展示其 step 列表；
    - [x] 每个 step 包含简短标题（如“打开 x.com”、“等待用户登录”）和状态；
    - [x] 若有 login/waiting_user 类型的 checkpoint，用明显标记区分。
  - [x] 验收：当 plane 任务处于 `waiting_user` 时：
    - [x] Plane 链路视图内有清晰的提示（与登录协同设计文档保持一致），指引用户完成下一步操作。

---

## 阶段四：左右 / 上下联动逻辑

- [x] 4.1 从 Chat Pane 到 Execution Pane 的跳转
  - [x] 验收：以下入口均能唤起 Execution Pane，并定位到对应内容：
    - [x] 点击任务 chip；
    - [x] 点击 Chat Pane status bar 中的「查看执行详情」；
    - [x] 点击与 plane 状态相关的提示（例如「浏览器 plane 等待登录」）。
  - [x] 验收：跳转时有明显但不刺眼的视觉反馈（例如短暂高亮目标区域）。

- [x] 4.2 从 Execution Pane 回到 Chat Pane 的焦点反馈
  - [x] 验收：当用户在 Execution Pane 中选择某个 tool 调用或 plane step 时：
    - [x] Chat Pane 中与该调用/step 对应的 Aelin 消息可以轻度高亮（背景微变色或左侧边缘线）；
    - [x] 高亮持续时间有限，避免干扰后续对话。

- [x] 4.3 窄屏下的上下联动
  - [x] 验收：在窄屏上下布局中：
    - [x] Chat Pane 的入口操作（chip / status bar）会使 Execution Pane 自下而上滑出；
    - [x] 再次点击空白区域或“收起”按钮可以让 Execution Pane 回到底部折叠状态；
    - [x] 动画流畅，不影响输入栏使用。

---

## 阶段五：Session + plane 状态的可视化增强

- [x] 5.1 左侧 Session 行显示 plane 小标记
  - [x] 验收：每个 session 行可显示最近使用的 plane 的小图标（例如 Pinchtab）：
    - [x] 图标风格简洁统一（与 provider 图标体系一致）；
    - [x] 不影响现有 session 文本显示。

- [x] 5.2 进行中任务指示点
  - [x] 验收：当某 session 下有 active plane 任务（状态为 queued/running/waiting_user/blocked）时：
    - [x] 在该 session 行右上角显示一个小圆点（可有轻微呼吸动画）；
    - [x] 所有 plane 任务结束或关闭后，小圆点消失。

- [x] 5.3 切换 Session 时 Execution Pane 的自动同步
  - [x] 验收：用户在左侧切换 session 时：
    - [x] Chat Pane 切换到该 session 消息；
    - [x] Execution Pane 自动展示该 session 的最近一轮执行信息：
      - [x] 若有 plane 任务：切到对应 plane 链路视图；
      - [x] 若无 plane 任务但有工具调用：切到工具调用视图；
      - [x] 若都没有：显示“暂无执行记录”的空状态。

---

## 阶段六：样式、动效与无障碍

- [x] 6.1 保持黑白灰 + 扁平风格
  - [x] 验收：新引入的 Pane 分割线、tab、按钮等组件：
    - [x] 仅使用黑白灰主色，不引入额外彩色背景；
    - [x] 用色主要体现在明暗层次，而非边框重线。

- [x] 6.2 动画与过渡
  - [x] 验收：Execution Pane 折叠/展开、tab 切换、scoll-to 的动画：
    - [x] 时长适中（通常 150–250ms 区间）；
    - [x] 不影响文字清晰度和输入操作；
    - [x] 允许通过系统/浏览器“减少动效”设置减弱或关闭（如可行）。

- [x] 6.3 基础无障碍检查
  - [x] 验收：主要可交互元素（Execution Pane 折叠按钮、tab、chip）：
    - [x] 可通过键盘操作获取焦点并触发；
    - [x] 有合理的 aria-label 或 role 标注（至少在代码结构层面不阻碍后续 a11y 加强）。

---

## 阶段七：验证与回归

- [ ] 7.1 与 browser plane（Pinchtab）的端到端链路验证
  - [ ] 验收：在本地拉起 backend + Pinchtab 后，执行一个典型 browser plane 任务（例如访问 X 关注列表）：
    - [ ] 在 Chat Pane 中看到 plane 任务 chip 与精简 status bar；
    - [ ] 在 Execution Pane 中看到 browser plane 的内部链路（至少包含“打开站点”和“等待登录”）；
    - [ ] waiting_user 场景下，登录提示与执行视图一致且可理解。

- [ ] 7.2 与现有工具调用的兼容性
  - [ ] 验收：对于只使用普通工具（如 web_search、gws）的对话：
    - [ ] Chat Pane 中的体验与原先相当或更清晰（有精简呼叫提示，不打断阅读）；
    - [ ] Execution Pane 能展示所有调用详情，无遗漏或异常报错。

- [ ] 7.3 回归检查：无 plane / 无工具场景
  - [ ] 验收：在完全不使用工具/plane 的纯聊天场景下：
    - [ ] Chat Pane 外观与行为接近当前版本（不出现空状态条干扰对话）；
    - [ ] Execution Pane 可默认处于折叠状态，或显示简短的“暂无执行信息”。
