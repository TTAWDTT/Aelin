---
title: DeepAgents Official Gap Analysis
slug: /reference/deepagents-gap-analysis
description: 对比官方 DeepAgents 与 Aelin 当前接入方式，解释现有差距、成因与修复优先级。
---

# DeepAgents Official Gap Analysis

> 更新时间：2026-03-30
>
> 目的：说明 Aelin 当前的 DeepAgents 接入与官方 DeepAgents 之间的真实差距，避免把一系列系统性问题误判成单点的“模型超时”或“某个工具坏了”。

## 结论摘要

Aelin 现在不是“官方 DeepAgents 原样可用”，而是：

- 官方 DeepAgents 中间件栈仍在
- Aelin 自定义工具层额外叠加在上面
- Aelin 自定义结果映射层又把很多运行态能力压扁成普通聊天响应

因此，Aelin 当前最核心的问题不是某个单独的 `write_file` 调用慢，而是下面三个闭环没有对齐：

- 文件语义没有统一
- 执行语义没有统一
- 运行态与交付物没有被完整呈现给前端

这也是为什么很多复杂任务会表现为：

- `write_file` 看起来成功，但用户拿不到真实文件
- `execute` 看起来可用，但无法消费 `write_file` 的产物
- `task` 理论存在，但用户感知不到 subagent 是否真的创建和完成
- 最终交付物即使生成，也不会自然出现在产品界面上

## 调研范围

本分析同时参考了三类材料：

- 官方 DeepAgents 文档
  - [Overview](https://docs.langchain.com/oss/python/deepagents/overview)
  - [Backends](https://docs.langchain.com/oss/python/deepagents/backends)
  - [Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
  - [Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)
  - [Frontend Overview](https://docs.langchain.com/oss/python/deepagents/frontend/overview)
- 本地安装的 DeepAgents 源码
  - `D:/anaconda/Lib/site-packages/deepagents/...`
- Aelin 当前接入实现
  - [backend/app/services/deepagents/deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py)
  - [backend/app/services/deepagents/managed_backend.py](D:/Github/Aelin/backend/app/services/deepagents/managed_backend.py)
  - [backend/app/services/deepagents/model_timeout_middleware.py](D:/Github/Aelin/backend/app/services/deepagents/model_timeout_middleware.py)
  - [backend/app/services/deepagents/runtime_resolver.py](D:/Github/Aelin/backend/app/services/deepagents/runtime_resolver.py)
  - [backend/app/services/tools/tools_execute.py](D:/Github/Aelin/backend/app/services/tools/tools_execute.py)
  - [backend/app/services/device/device_center.py](D:/Github/Aelin/backend/app/services/device/device_center.py)
  - [backend/app/services/device/remote_control_chat_adapter.py](D:/Github/Aelin/backend/app/services/device/remote_control_chat_adapter.py)

## 官方 DeepAgents 的设计假设

## 1. 官方默认能力面

官方 `create_deep_agent(...)` 默认会把下列能力组织进同一套 agent 运行体系：

- `write_todos`
- `ls`
- `read_file`
- `write_file`
- `edit_file`
- `glob`
- `grep`
- `task`
- `execute`，但仅当 backend 支持 `SandboxBackendProtocol`

对应源码入口见：

- [graph.py](D:/anaconda/Lib/site-packages/deepagents/graph.py)
- [filesystem.py](D:/anaconda/Lib/site-packages/deepagents/middleware/filesystem.py)
- [subagents.py](D:/anaconda/Lib/site-packages/deepagents/middleware/subagents.py)

这里最重要的不是“工具数量多”，而是这些工具默认共享同一个 backend 抽象。

## 2. 官方文件语义

官方 DeepAgents 的文件系统不是固定等于宿主机文件系统，它取决于 backend。

常见两类语义：

- `StateBackend`
  - 文件保存在 LangGraph state 中
  - 会跟随 thread / checkpoint 持续一段时间
  - 不是宿主机真实落盘
- `FilesystemBackend` / `LocalShellBackend` / 其他 sandbox backend
  - 文件可能真正在磁盘或 sandbox 中持久化

这意味着官方 `write_file` 的语义是：

- “写入当前 backend 的文件世界”
- 不自动等价于“写入用户电脑上的真实文件”

见：

- [state.py](D:/anaconda/Lib/site-packages/deepagents/backends/state.py)
- [protocol.py](D:/anaconda/Lib/site-packages/deepagents/backends/protocol.py)

## 3. 官方执行语义

官方 `execute` 是 FilesystemMiddleware 内建工具的一部分，但只在 backend 支持 `SandboxBackendProtocol` 时才真正暴露。

也就是说，官方 DeepAgents 默认假设：

- 文件工具和执行工具依赖同一个 backend 抽象
- 如果 backend 不支持执行，就不要让模型依赖 `execute`

对应实现见：

- [filesystem.py](D:/anaconda/Lib/site-packages/deepagents/middleware/filesystem.py)
- [protocol.py](D:/anaconda/Lib/site-packages/deepagents/backends/protocol.py)
- [local_shell.py](D:/anaconda/Lib/site-packages/deepagents/backends/local_shell.py)

## 4. 官方 subagent 语义

官方 DeepAgents 把 subagent 作为第一等能力处理：

- 主 agent 有 `task` 工具
- 默认会有 general-purpose subagent
- subagent 与主 agent 共享统一的能力模型，只是上下文隔离
- 返回时通过 `Command(update=...)` 把结果折叠回父 agent 状态

见：

- [subagents.py](D:/anaconda/Lib/site-packages/deepagents/middleware/subagents.py)

## 5. 官方前端与 artifact 假设

官方文档明确强调：

- 前端应该能看到 todo、subagent、values、工具流
- sandbox / backend 场景里，artifact 需要通过应用侧 upload/download 机制回收

也就是说，官方 DeepAgents 并不只关注“最终一句回答”，而是关注整条运行链路的状态可见性与产物回收。

见：

- [Frontend Overview](https://docs.langchain.com/oss/python/deepagents/frontend/overview)
- [Sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)

## Aelin 当前接入现状

## 1. Aelin 仍然在使用官方 DeepAgents 中间件

Aelin 在 [deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py) 中调用了 `create_deep_agent(...)`。

这意味着下面这些官方能力理论上仍然存在：

- `FilesystemMiddleware`
- `SubAgentMiddleware`
- 官方 `read_file / write_file / edit_file / task`
- 官方 summarization / patch tool calls 等中间件

所以，Aelin 当前并不是“完全绕开了 DeepAgents 官方体系”。

## 2. Aelin 同时叠加了自己的工具面

Aelin 又通过 `tools=tools` 显式注入了自己的能力：

- `web_search`
- `attachment_search`
- `google_workspace`
- `device`
- `screen_get`
- `execute`，仅在桌面插件开关开启时

这些工具来自：

- [deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py)
- [tool_runtime.py](D:/Github/Aelin/backend/app/services/deepagents/tool_runtime.py)
- [tools_execute.py](D:/Github/Aelin/backend/app/services/tools/tools_execute.py)

这一步本身没有错，但它引入了一个重要事实：

> Aelin 的能力面已经不是“纯官方 DeepAgents”，而是“官方中间件工具 + Aelin 自定义工具”的混合面。

## 3. Aelin 的默认 backend 是 StateBackend，不是 sandbox backend

Aelin 当前 backend 构造方式是：

- 默认 backend：`StateBackend(runtime)`
- 技能目录：挂到 `FilesystemBackend(..., virtual_mode=True)`
- 外层包装：`ManagedCompositeBackend`

见：

- [deepagents_graph.py](D:/Github/Aelin/backend/app/services/deepagents/deepagents_graph.py)
- [managed_backend.py](D:/Github/Aelin/backend/app/services/deepagents/managed_backend.py)

这意味着：

- 默认文件写入落在 DeepAgents 线程态文件系统里
- 技能目录是只读挂载
- 默认 backend 本身不具备官方 sandbox execute 语义

## 4. Aelin 的 execute 是自定义桌面插件桥，不是官方 backend-native execute

Aelin 自己注册的 `execute` 最终走的是桌面插件 HTTP 接口：

- [tools_execute.py](D:/Github/Aelin/backend/app/services/tools/tools_execute.py)
- [device_center.py](D:/Github/Aelin/backend/app/services/device/device_center.py)

因此，Aelin 的 `execute` 与官方 DeepAgents 的 `execute` 有本质区别：

- 官方：backend 原生能力，和文件工具共用同一抽象
- Aelin：额外接入的一条外部命令桥

## 5. Aelin 的前端响应被压缩成普通 ChatResponse

DeepAgents 运行完后，Aelin 最终返回前端的是：

- `answer`
- `actions`
- `memory_summary`

见：

- [remote_control_chat_adapter.py](D:/Github/Aelin/backend/app/services/device/remote_control_chat_adapter.py)

而下面这些 DeepAgents 运行态能力没有被完整透出：

- `files`
- subagent 状态流
- todos
- 官方文件工具调用轨迹
- artifact 下载入口

这会大幅削弱用户对能力是否真的执行成功的感知。

## 差距清单

## 1. 文件工具与执行工具不再共享同一个文件世界

这是当前最大的架构差距。

官方 DeepAgents 的理想形态是：

- `write_file`
- `edit_file`
- `read_file`
- `execute`

都围绕同一个 backend 文件语义展开。

而 Aelin 当前是：

- 官方 `write_file` 默认写进 `StateBackend`
- Aelin 自定义 `execute` 在桌面插件侧执行

结果就是“两套文件世界”：

- DeepAgents 线程态文件世界
- 宿主机真实文件世界

这直接导致下面这些问题：

- `write_file` 成功，但 `execute` 看不到这个文件
- `execute` 生成了真实文件，但 `read_file` 不一定能读取到
- “写文件 -> 执行 -> 再读文件”无法自然闭环

## 2. write_file 的产品语义与用户预期不一致

`StateBackend.write()` 的官方语义本来就只是：

- 更新 `runtime.state["files"]`
- 返回 `files_update`

它不是宿主机真实落盘。

所以从系统视角看：

- `write_file` 未必坏了
- 但它也未必完成了用户心中的“写出一个真实交付文件”

这不是单纯工具 bug，而是“官方 backend 语义”和“Aelin 产品预期”之间没有重新对齐。

## 3. execute 虽然存在，但不是官方那种 backend 原生 execute

官方 `execute` 的优点是：

- 可由 FilesystemMiddleware 根据 backend 能力自动启闭
- 和文件系统语义一致
- 对模型来说更稳定

Aelin 当前的 `execute` 则是：

- 额外注册的 custom tool
- 命令发到桌面插件
- 与官方文件 backend 不同源

这会造成：

- 模型需要理解两套不同的能力边界
- 开发者日志里看到的是“有 execute”
- 实际上它并不继承官方 execute 的那套一致性

## 4. subagent 在理论上存在，但在产品层几乎不可观测

官方 `task` 和 general-purpose subagent 仍然存在。

但 Aelin 当前没有把下面这些信息完整呈现给用户或调试层：

- 哪一次真的调用了 `task`
- 创建了哪个 subagent
- subagent 中间产生了什么步骤
- subagent 输出了哪些状态更新

同时，Aelin 自己记录的 `tool_runs` 只覆盖自定义工具，不覆盖官方文件工具和 `task`。

因此用户体验上会变成：

- 不能确定 subagent 是否真的创建
- 不能判断失败是发生在“没调用”还是“调用了但没展示”

## 5. artifact 没有形成“生成 -> 回收 -> 呈现”的交付闭环

官方 DeepAgents 文档在 sandbox 场景下非常强调 artifact 下载与回收。

Aelin 当前缺的是这一层：

- agent 生成文件后，谁负责把它认定为“交付物”
- 交付物从哪一层取回
- 前端如何可点击、可预览、可下载

这就是为什么你之前观察到：

- 可能生成过中间文件
- 但最终交付物并不会自然呈现出来

## 6. 能力声明与真实能力面不一致

Aelin 在 `/runtime/capabilities.json` 里只写入了自定义工具名和技能挂载信息。

但官方 middleware 实际还会再注入：

- `read_file`
- `write_file`
- `edit_file`
- `glob`
- `grep`
- `task`

这会带来两个后果：

- 模型对自己“真正有哪些能力”的自我认知可能不完整
- 开发者调试时也容易被 capability 文件误导

## 7. 额外补丁中间件增加了协议脆弱性

Aelin 额外引入了：

- `DeepAgentsModelTimeoutMiddleware`
- `DeepAgentsToolMessageSanitizerMiddleware`

官方本身又已经有：

- `PatchToolCallsMiddleware`

这些补丁解决了一些兼容性问题，但也意味着：

- 历史消息里的 tool call / tool result 对账更复杂
- 更容易出现 provider 侧 `tool_call_id` 不匹配
- 某些失败并不是 DeepAgents 官方核心逻辑导致，而是“混合补丁层”导致

你日志里出现过的 `Invalid tool_call_id`，就高度符合这种“协议层补丁叠加后更脆”的症状。

## 差距形成的原因

## 1. Aelin 的产品目标比官方 DeepAgents 更复杂

官方 DeepAgents 更偏向“统一 backend 驱动的 agent runtime”。

Aelin 想承载的是：

- 聊天产品
- 桌面插件
- 本地执行
- Google Workspace
- 设备控制
- 文件预览与交付

这使得 Aelin 很自然地开始往 DeepAgents 外面叠加产品层能力。

## 2. 为了安全和工程控制，Aelin 没直接采用官方 sandbox/local-shell backend

如果直接上官方 `LocalShellBackend` 或更完整的 sandbox backend：

- 文件与执行会天然闭环
- 但宿主机执行风险会更大

所以 Aelin 目前选择了：

- 文件继续用 `StateBackend`
- 执行走桌面插件桥

这个取舍有合理性，但代价就是一致性下降。

## 3. 前端没有按官方 DeepAgents 的原生状态流来消费

官方前端强调：

- messages
- values
- todos
- subagents
- sandbox artifacts

Aelin 当前产品响应仍然更像普通聊天接口，只保留：

- `answer`
- 少量 `actions`

所以很多“能力其实存在”的东西，在用户视角里就像“不存在”。

## 4. 兼容性补丁越来越多，逐步偏离官方语义

随着下面这些补丁加入：

- 模型超时中间件
- tool message sanitizer
- 自定义能力文件
- 自定义 execute
- 自定义 tool limiter

系统越来越像“在 DeepAgents 外面又搭了一个半独立编排层”。

这会让问题变成：

- 不是一个点坏了
- 而是官方假设被逐步拆散了

## 对几个关键疑问的判断

## 1. 是不是 write_file 本身坏了

不能简单下这个结论。

更准确的说法是：

- 在官方 `StateBackend` 语义下，`write_file` 很可能是正常的
- 但它写入的是线程态文件，而不是宿主机真实文件

所以“工具没坏”和“产品上不够用”可以同时成立。

## 2. 是不是代码没有真正执行

不一定。

更可能的情况是：

- 代码确实执行了
- 但执行发生在桌面插件对应的宿主机环境里
- 与 `write_file` 产生的线程态文件不在同一个文件世界

因此用户会感觉像“前一步没生效”。

## 3. 是不是文件没有真实写入

如果调用的是官方 `write_file` 且默认 backend 是 `StateBackend`，那答案大概率是：

- 没有真实写到宿主机文件系统
- 只写到了 LangGraph / DeepAgents 的运行态文件映射里

## 4. 是不是 subagent 没有真正创建

目前不能直接判断“没创建”。

更合理的判断是：

- `task` 理论仍在
- subagent 很可能可以创建
- 但创建、运行、完成的可观测性太弱

所以产品表现更像“它没有发生”。

## 5. 为什么很多 skill 测试最终都表现成 75s 超时

75s 超时是真实现象，但它更像放大器，不是唯一根因。

当系统存在下面这些不一致时：

- 文件与执行脱节
- subagent 不可观测
- artifact 不可回收
- tool 协议补丁复杂

模型更容易：

- 长时间组织参数
- 反复在错误能力模型里规划下一步
- 进入“看起来在工作，但没有真正闭环”的状态

这时 75s 只是最后把问题暴露出来。

## 修复优先级建议

## P0：统一文件语义与执行语义

先明确产品要哪一种：

- 方案 A：保留 `StateBackend`，但明确它只是 agent scratch space，再补一条“导出为真实交付物”的桥
- 方案 B：引入真正统一的 sandbox/backend，使 `write_file` 与 `execute` 共享同一文件世界

这是最先要定的架构决策。

## P1：补齐 artifact 回收与呈现链路

必须把“文件生成成功”转成产品可见事实：

- 识别交付物
- 回收交付物
- 在前端展示为可点击、可预览、可下载

否则即使 agent 真做成了事，用户仍然会认为失败。

## P1：把官方运行态信息真正透给前端

至少要显式呈现：

- todos
- subagents
- 官方文件工具调用
- 交付物状态

否则 DeepAgents 的过程价值会被严重折损。

## P2：让 capability 宣告与真实工具面一致

`/runtime/capabilities.json` 不应只列自定义工具。

否则模型和开发者都在一个不完整的能力镜像上做决策。

## P2：收敛协议补丁，减少 tool_call_id 风险

应该重新梳理：

- 官方 `PatchToolCallsMiddleware`
- Aelin 自己的 sanitizer
- provider 对 tool history 的要求

尽量避免双重修补。

## 最终判断

截至 2026-03-30，Aelin 与官方 DeepAgents 的最大差距不是：

- “少了一个工具”
- “只是超时”
- “只有 write_file 有 bug”

而是：

> 官方 DeepAgents 依赖“统一 backend + 统一状态流 + 统一前端语义”；
> Aelin 当前则是“官方中间件仍在，但文件、执行、subagent 观测、artifact 交付已经分裂成多层混合体系”。

因此，后续如果要真正把复杂任务做稳，核心工作不该只盯着“调大超时”或“修某个工具”，而应该优先修复：

- backend 语义统一
- artifact 交付闭环
- 运行态前端可见性

只有这三件事先对齐，复杂技能、海报生成、项目搭建、真实文件交付、代码执行这些问题才会一起明显好转。

## DeerFlow 对照

## 1. 为什么要看 DeerFlow

官方 DeepAgents 更像一个通用 agent runtime 能力层。

DeerFlow 则更进一步，明确把自己定义成一个 long-horizon super agent harness：

- 有 agent runtime
- 有 sandbox
- 有 memory
- 有 skills
- 有 subagents
- 有 Gateway API
- 有前端
- 有 artifact / upload / download 入口

换句话说，DeerFlow 不只是“让 agent 能跑起来”，而是把“agent 怎样真正交付结果”也作为一等问题处理。

参考：

- [DeerFlow GitHub README](https://github.com/bytedance/deer-flow)
- [DeerFlow 官网](https://deerflow.tech/)

## 2. DeerFlow 的关键工程特征

根据官方仓库与公开文档，DeerFlow 至少有下面几类和 Aelin 直接相关的设计：

- 明确的多服务架构
  - LangGraph Server 负责 agent runtime
  - Gateway API 负责 models、skills、memory、artifacts、uploads
  - Next.js Frontend 负责实时 UI
  - Nginx 统一代理入口
- 明确的 harness / app 分层
  - Harness 负责 agent、sandbox、tools、memory、skills、models
  - App 层只负责外部 API 与渠道接入
- 明确的 sandbox 执行模型
  - 支持本地或容器 / K8s provider
  - 强调 per-thread isolated execution
  - 强调 read / write / run 在同一个“computer”里完成
- 明确的 artifact 与上传下载链路
  - Gateway API 负责 artifacts 和 uploads
  - 客户端接口包含上传文件等能力
- 明确的前端运行态展示
  - 实时流式执行
  - 强调 planning、sub-tasking、long task running
  - 强调技能渐进加载与 runtime 环境可感知

参考：

- [DeerFlow GitHub README](https://github.com/bytedance/deer-flow)
- [DeerFlow 官方站点](https://deerflow.tech/)
- [DeepWiki for DeerFlow overview](https://deepwiki.com/bytedance/deer-flow/1-overview)

## 3. Aelin 与 DeerFlow 的主要差距

## 3.1 DeerFlow 把“agent runtime”和“应用层”边界切得更清楚

DeerFlow 明确区分：

- Harness
- App layer

并且还有文档化的依赖方向约束。

而 Aelin 当前虽然也在往“LangGraph Agent Server + 产品 API”方向收敛，但实际仍然存在较强的混合层：

- backend 里既有 agent runtime 组装
- 又有产品定制工具
- 又有前端映射适配
- 又有桌面执行桥

结果是很多问题难以归位：

- 是 runtime 问题
- 是 product adapter 问题
- 还是 desktop bridge 问题

在 DeerFlow 里，这种边界通常更清晰。

## 3.2 DeerFlow 的文件、执行、sandbox 是一体的

这是 DeerFlow 对 Aelin 最值得学习的一点。

DeerFlow 官方对外讲得非常直接：

- agent 有一个“computer”
- 可以 read / write / run
- 而且这是同一个 sandbox runtime

这使得它天然更容易完成下面的闭环：

- 写文件
- 执行代码
- 生成 artifact
- 回收 artifact
- 呈现 artifact

Aelin 当前最核心的短板恰好就在这里：

- `write_file` 主要是 `StateBackend`
- `execute` 主要是桌面插件桥
- 两者默认不是同一文件世界

所以 DeerFlow 的优势不只是“它有 execute”，而是：

> 它把文件与执行当作同一个运行时问题来建模。

## 3.3 DeerFlow 对 artifact 交付链路更完整

DeerFlow 明确存在：

- uploads
- artifacts
- Gateway API
- 前端配套

这说明它把“最终生成物如何离开 agent runtime，进入产品层”作为正式能力处理。

而 Aelin 当前仍然缺少稳定的 artifact 产品闭环：

- 哪些文件是中间 scratch
- 哪些文件是最终交付物
- 交付物如何回收
- 回收后如何可点击、可预览、可下载

这也是你之前一直强调“最终交付物不会呈现出来”的根本背景。

## 3.4 DeerFlow 对长任务与 sub-tasking 的产品表达更完整

DeerFlow 官网和文档都把下面这些作为主卖点直接展示：

- Long Task Running
- Planning and Sub-tasking
- Skills and Tools
- Long / Short-term Memory

也就是说，DeerFlow 不仅做了这些能力，还把它们设计成用户可感知的产品特征。

而 Aelin 当前虽然部分底层能力在技术上存在，但产品表达层明显更弱：

- subagent 是否调用不清楚
- planning 过程不够可见
- 长任务中间状态缺乏强表达
- artifact 和状态切换对用户不够直观

## 3.5 DeerFlow 更像“完整 harness”，Aelin 目前更像“DeepAgents 接入中的产品集成态”

DeerFlow 当前的公开定位已经不是单纯 research agent，而是 super agent harness。

这个定位背后的实际含义是：

- 它关注的是一整套 agent 基础设施
- 而不仅是模型 + 工具调用

相比之下，Aelin 目前虽然已经完成了很多 DeepAgents 接入工作，但从工程成熟度看，更接近：

- DeepAgents 原生能力接进产品
- 但 backend / artifact / runtime observability / app-layer protocol 还没完全补齐

## 4. 差距形成原因

## 4.1 DeerFlow 从一开始就把 sandbox 和 artifact 当成核心能力建设

它不是后期才补“代码执行”或“文件交付”，而是从框架定位上就包含这些。

因此它的架构天然更容易统一：

- sandbox provider
- thread workspace
- artifact API
- 前端展示

而 Aelin 当前的执行能力更多是后接进来的桌面桥，因此天然更容易出现双轨语义。

## 4.2 DeerFlow 的产品边界更接近“Web Super Agent”，Aelin 还带有更强的桌面产品约束

DeerFlow 主要围绕：

- Web UI
- Gateway API
- sandbox runtime

来设计。

Aelin 还要兼顾：

- 桌面插件
- 本地环境
- 已有产品接口
- 历史 Aelin 交互语义

所以 Aelin 的兼容负担更重，导致系统更容易进入“局部补丁越来越多”的状态。

## 4.3 DeerFlow 对运行态可见性投入更足

从公开材料看，DeerFlow 很重视：

- 任务过程展示
- 子任务与规划表达
- 技能与环境可视化

而 Aelin 当前更偏“最终回答导向”，这让很多底层能力即使存在，也不容易形成用户信任感。

## 5. 可以从 DeerFlow 学什么

如果只提炼最值得借鉴的方向，我认为有五点：

- 把文件系统、代码执行、artifact 交付当成一个统一 runtime 问题，而不是三个零散功能
- 在 agent runtime 之外，单独建设正式的 Gateway / artifact API，而不是只靠聊天响应携带结果
- 让 subagent、planning、long-running 状态成为前端一等公民
- 明确 harness 与 app layer 的边界，降低定制逻辑与底层 runtime 的耦合
- 把“最终交付物可点击、可预览、可下载”做成正式产品能力，而不是聊天附带效果

## 6. 对 Aelin 的现实启示

对比 DeerFlow 之后，Aelin 当前最明显的不足不再只是“DeepAgents 官方差距”，而是：

> Aelin 还没有把自己提升成一个完整的 agent harness 产品。

更具体地说，Aelin 现在的问题不是“没有 agent”，而是“agent 工作完成之后，产品层如何承接这件事”。

因此，如果后续要继续演进，优先级应该更明确地转向：

- 统一 runtime 文件 / 执行语义
- 建正式 artifact pipeline
- 提升前端的运行态可见性
- 收敛 harness 与产品层边界

这四件事补上之后，Aelin 才会更接近 DeerFlow 这种“完整可交付的 super agent harness”，而不只是“已经接入 DeepAgents 的一个聊天产品”。
