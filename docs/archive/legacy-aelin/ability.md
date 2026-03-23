# Aelin 能力架构

> 注意：本文件主要记录的是早期的「plane / PinchTab」分层能力架构设想。  
> 在当前 DeepAgents 纯壳分支中，browser plane / PinchTab 能力已完全下线，
> 浏览与 remote-control 能力只通过 `device` 工具（+ DeepAgents 自身的多轮
> 推理与工具组合）提供。本文件保留作为历史设计参考，请以
> `docs/deepagents_arch.md` 中的说明作为当前架构的权威来源。

## 文档目的

这份文档用于定义 Aelin 的 Agent 能力架构。

Aelin 不应被理解为一个单纯的“LLM + tool calling”系统，而应当被理解为一个分层能力系统：

- 具备自身的基础 LLM 能力
- 能在合适场景下使用原子工具
- 能把复杂领域工作委派给独立的 plane
- 能通过 Aelin 自身独有的 planning / orchestration 能力，对任务进行分派、监督、续办与验收

在这个架构里，PinchTab 不应被视为普通工具，而应被视为一个 `plane`，更准确地说，是 `browser plane`。

相对而言，截图、执行web_search这类能力就应被当成原子工具使用，属于Aelin本身具备的“能力层”

## 四层能力模型

### 第一层：LLM 基础能力

这是 Aelin 自身的认知层能力。

它包括：

- 理解用户意图
- 语言生成
- 总结与解释
- 基于上下文进行推理
- 做判断与取舍
- 组织最终面向用户的表达

这一层是 Aelin 的思考基础，但它本身并不等于执行能力。

也就是说：

- 它不天然意味着可以完成复杂网页流程
- 不天然意味着可以管理外部系统
- 不天然意味着可以承担长流程任务执行

它是 Aelin 的“大脑基础”，不是它的“执行系统”。

### 第二层：Tool Use

这一层是原子能力层。

这里的能力通常表现为：

- 本地工具
- MCP
- 单步能力调用
- 结构化 API
- 一次性、短路径、边界清晰的执行动作

适合使用第二层的场景包括：

- 任务很小、很明确
- 行为路径很短
- 不需要长期状态
- 不需要把整项工作外包给一个独立执行系统
- Aelin 自己直接做这一步更高效

例如：

- 读取文件
- 发起 web_search
- 打开一个链接
- 截一张图
- 获取一个结构化接口结果

这一层更像是“手”。

它给 Aelin 提供细粒度动作，但不构成完整的任务承接系统。

之后gws或许会用这种方式来集成google相关的操作

### 第三层：Plane

这一层是独立可委派系统层。

`plane` 不是工具集合，也不是一组原子动作。
它是一个完整的、可承接某一类复杂任务的执行子系统。

一个真正的 plane 应当具备：

- 自己的领域边界
- 自己的运行时状态
- 自己的内部规划与执行逻辑
- 自己的任务推进方式
- 自己的结果输出形式

因此，Aelin 对 plane 的交互方式，不应该是：

- 一步一步操作它的底层动作

而应该是：

- 把目标交给它
- 监督它的进度
- 接收它的阶段结果
- 根据结果决定继续、修正、暂停、请用户配合或结束

这一层不是“手”，而是“人”。

也可以说：

- tool 是动作能力
- plane 是任务承接能力

未来可能存在的 plane 包括：

- `browser plane`
- `computer-use plane`
- `coding plane`
- `research plane`
- `office-work plane`

并不是所有能力都需要变成 plane。
只有当一个领域足够复杂、足够适合被整体委派时，才值得升格为 plane。

*值得注意的是，只有只有agent系统可以被称之为plane，因为plane要能够独立完成一个goal，往往会包括计划、执行这样的多轮迭代，并且需要一定的自主能力*

*为了适应plane的使用，或许会需要skill或是其他文档注入上下文中，当然，我更倾向于采用渐进式披露，或者说先给出目录，选择后检索细节的这种上下文注入方式*

### 第四层：Aelin 自身的 Planning 能力

这是 Aelin 最关键、也最有特色的一层。

这一层不是简单的“再多写一点 prompt”，而是 Aelin 作为上层 orchestrator 的核心能力。

这一层负责决定：

- 当前任务是否只需要第一层能力
- 当前任务是否只需要第二层工具
- 当前任务是否应该委派给第三层 plane
- 应该委派给哪个 plane
- 是否需要多 plane 协作
- 什么时候轮询进度
- 什么时候续上已有会话
- 什么时候请求用户配合
- 什么时候停止委派并开始整理最终答复

如果没有这一层，Aelin 只是一个会调用工具的聊天 Agent。

如果有了这一层，Aelin 才会成为一个真正的“总调度者”。

## 核心角色模型

一个更准确的理解方式是：

- 用户 = 超级大老板
- Aelin = 秘书 / 总协调者
- tool = 秘书具备的一些能力（比如简单操作或是写文档、google操作一类的能力）
- plane = 被委派出去办事的专业执行系统

因此，正确的关系应当是：

- 用户给 Aelin 目标
- Aelin 判断工作类型并进行分派
- plane 承担具体领域内的执行
- Aelin 监督进度、验收结果、整理输出
- Aelin 向用户汇报

这里最关键的一点是：

- Aelin 不应该亲自去做 plane 内部的细节动作

如果 Aelin 开始亲自点击网页、亲自决定是否滚动、亲自逐步操控 plane 的底层能力，那么 plane 就退化成了工具层。

## 为什么 PinchTab 属于第三层，而不是第二层

PinchTab 应当被归类为 `plane`，而不是普通工具。

这不仅是出于 Aelin 的产品目标，也是因为 PinchTab 官方项目本身就是按一个独立浏览器控制系统来设计的。

根据 PinchTab 官方 README，它的定位包括：

- 一个独立的 HTTP 服务
- 一个面向 AI Agent 的本地浏览器控制平面
- 以 server-first 的方式运行
- 管理 profile、instance、tab、dashboard
- 支持 headed / headless 模式
- 支持多实例
- 支持浏览器状态持久化
- 通过 CLI / HTTP API 对外暴露能力

参考：

- https://github.com/pinchtab/pinchtab
- https://raw.githubusercontent.com/pinchtab/pinchtab/main/README.md

这意味着 PinchTab 从项目定位上就不是“一个按钮点击工具”。

它本质上是一个浏览器领域执行子系统。

因此，在 Aelin 里，PinchTab 最合理的角色就是：

- `browser plane`

而不是：

- `open_tab`
- `click`
- `text`
- `snapshot`

这类原子动作更适合被视为 PinchTab 内部的能力，而不是 Aelin 与 PinchTab 的主要交互界面。

## PinchTab 作为 Browser Plane 的职责边界

### PinchTab 适合承担的工作

作为 browser plane，PinchTab 适合负责：

- 打开网站
- 导航页面
- 维持登录后的会话
- 执行多步网页流程
- 识别并操作页面元素
- 填写表单、点击按钮、提交信息
- 抽取页面文本或结构化快照
- 在需要时滚动、翻页、继续加载
- 对浏览器领域内的任务过程进行状态汇报

### PinchTab 不应承担的工作

PinchTab 不应负责：

- 全局用户意图判断
- 跨 plane 总调度
- 最终业务判断
- 非浏览器领域的工作
  - 例如代码修改
  - 本地记忆管理
  - 非浏览器原生桌面控制
  - 通用数据协调

这些职责依然属于 Aelin。

## 正确的 Aelin 与 Plane 交互方式

正确方式应当是：任务级委派 + 进度监督。

### 正确流程

1. 用户向 Aelin 提出目标。
2. Aelin 判断这是某个 plane 的领域任务。
3. Aelin 把高层目标交给 plane。
4. plane 在内部自行规划与执行。
5. Aelin 轮询或审阅阶段结果。
6. 如果 plane 需要用户配合，Aelin 再转达给用户。
7. 如果 plane 完成任务，Aelin 进行审阅和最终表达。

### 错误流程

如下这种流程是不对的：

1. Aelin 判断需要 PinchTab。
2. Aelin 自己调用 `health`。
3. Aelin 自己调用 `launch_instance`。
4. Aelin 自己调用 `open_tab`。
5. Aelin 自己调用 `text`。
6. Aelin 自己决定要不要滚动。
7. Aelin 自己决定要不要继续抓内容。

这并不是“把工作委派给 PinchTab”。

这只是 Aelin 在亲自操作浏览器，而 PinchTab 只是在提供手脚。

在这种情况下，PinchTab 实际上仍然停留在第二层。

## 一个正确的 Browser Plane 例子

用户说：

- “帮我总结我的 X 关注列表，按领域分类，并告诉我值得重点关注的人。”

正确的处理方式应当是：

1. Aelin 识别这是浏览器领域复杂任务。
2. Aelin 将整个目标交给 PinchTab。
3. PinchTab 自己打开 X，判断是否需要登录，进入关注列表，滚动加载，抽取账号信息，并做阶段整理。
4. 如果需要登录，PinchTab 告诉 Aelin 当前在等待用户登录。
5. Aelin 再告诉用户：“请完成登录，我会继续让它执行。”
6. 用户完成登录后，Aelin 再让 PinchTab 继续。
7. PinchTab 返回阶段性或最终结果。
8. Aelin 对结果进行审阅、组织和输出。

这个流程中的关键点是：

- Aelin 不干预 PinchTab 内部的网页动作细节

## Plane Directory 的概念

Aelin 应该存在一个 plane 目录，或者 plane catalog。

这个目录用于说明：

- 当前有哪些 plane
- 每个 plane 各自负责什么领域
- 每个 plane 能承担哪些任务类型
- 每个 plane 的工作边界是什么
- 每个 plane 可能需要什么用户配合

例如：

- `browser`
  - 负责网页访问、登录、导航、抽取、浏览器流程
- `computer_use`
  - 负责更广义的桌面界面操作，当 browser plane 不足以完成任务时作为补充
- `coding`
  - 负责代码、仓库、测试、构建
- `google`
  - 负责 Google Workspace 相关系统工作

plane 目录的意义在于：

- 第三层能力是“可见的、可委派的系统能力”
- 而不是藏在实现细节里的工具分支

## 一个真正的 Plane 需要具备什么契约

如果一个系统要被视为 plane，而不是工具包，那么它至少应当提供稳定的任务级接口。

例如：

- `start`
- `poll` 或 `status`
- `continue`
- `close` 或 `abort`

同时它应当具有清晰的状态机，例如：

- `running`
- `waiting_user`
- `blocked`
- `completed`
- `failed`

并且它的结果输出至少应包括：

- 当前总结
- 证据或产出
- 是否还存在不确定性
- 是否需要用户配合

## 当前 Aelin 缺失的部分

目前的 Aelin 已经具备：

- 第一层：基础 LLM 能力
- 第二层：tool use 能力

但相对薄弱的部分是：

- 真正的 plane-first 委派模式
- 清晰的 plane 目录
- 稳定的 plane 契约
- Aelin 自身的第四层 planning 能力

特别是，如果 PinchTab 仍然主要以低层浏览器原子动作的方式暴露给 Aelin，那么它并没有真正进入第三层。

## 目标方向

目标架构应当是：

- 第一层负责认知
- 第二层负责原子动作
- 第三层负责复杂任务承接
- 第四层负责 Aelin 自身的规划、分派、监督和验收

其中非常关键的一点是：

- PinchTab 应当从“浏览器工具”升级为“浏览器 plane”

只有这样，Aelin 才会从一个普通的 tool-calling chat agent，真正演化为一个多 plane 的高层执行系统。

## 设计原则

1. 不要把 plane 降格为一堆原子动作。
2. 不要让 Aelin 亲自完成 plane 内部的细节工作。
3. 原子、小型、边界清晰的任务优先使用第二层工具。
4. 复杂、长流程、强状态依赖的任务优先委派给第三层 plane。
5. 保留 Aelin 自身在第四层的独特价值：规划、路由、监督、验收、汇报。
6. 每个 plane 都应拥有清晰的领域边界和稳定契约。

## 最终总结

Aelin 的能力架构应被定义为四层：

- 第一层：LLM 基础能力
- 第二层：Tool Use
- 第三层：Plane
- 第四层：Aelin 自身的 Planning

在这个系统里：

- tool 是动作能力
- plane 是任务承接系统
- Aelin 是总调度者

因此，PinchTab 的正确定位是：

- `browser plane`

而不是普通工具。

这个区分非常关键。

只有把 PinchTab 放在第三层，Aelin 才能真正进入第四层，成为一个具备分派、监督、验收与多系统协作能力的执行型 Agent。

## Google Workspace 工具（Level 2）

对于 Gmail / Drive / Calendar 这类 Google Workspace 能力，Aelin 采用的是 **第二层原子工具 + Skill 指南** 的模式，而不是把 `googleworkspace/cli` 升格为 plane。

- 底层由本地 `gws` CLI 提供访问 Google Workspace API 的能力；
- `backend/app/services/google_workspace_cli.py` 通过 `GoogleWorkspaceCliService` 做了受控封装，只暴露：  
  - `runtime_status()` / `auth_status()`（安装与登录状态）  
  - `gmail_list_messages()` / `gmail_get_message()`  
  - `drive_list_files()`  
  - `calendar_list_events()`  
- 在 `AelinToolHub` 中，这些能力统一通过一个工具 `google_workspace` 暴露出来，作为 Level 2 原子工具：
  - 读能力 action：`runtime` / `auth_status` / `gmail_list` / `gmail_get` / `drive_list` / `calendar_list`
  - 写能力 action：`calendar_create_event` / `gmail_send` / `gmail_draft` 目前仅预留占位，返回 `write_actions_not_implemented`，避免被误用
  - 所有 action 都遵循统一的结果结构：`{"ok", "scope", "items"/"item", "raw", "error", "next_action"}`。

Skill 层通过 `backend/skills/google/SKILL.md` 指导 Aelin：

- 何时优先使用 `google_workspace`（访问用户私有邮件/文件/日历）而不是 `web_search`；
- 如何先调用 `runtime` / `auth_status` 判断是否需要用户在终端执行 `gws auth login`；
- 在未安装或未登录时，如何用中文解释 `install_hint` / `login_command`；
- 在规划层面，如何将 gws 的“读结果”与 diary / memory 结合，用于后续推理，而不是把 gws 当成 plane 来托管长任务。

总结来说（**以下为历史架构视角**）：

- 早期设计中，PinchTab 被视为第三层 plane，负责承接复杂浏览器任务；
- `google_workspace` 属于第二层工具，负责把 Gmail / Drive / Calendar 的结构化数据“端上来”；
- Aelin 则在第四层对这些数据做规划、归纳、记忆和最终汇报。

在当前 DeepAgents 分支中，plane / PinchTab 已下线，浏览器与桌面能力统一收敛到
`device` 工具与 DeepAgents 内部的多轮工具调用逻辑。
