# DeepAgents Harness Gap Todo (2026-03-30)

> 这份 TODO 不是“优化清单”，而是 Aelin 从“已接入 DeepAgents 的产品”继续演进成“完整可交付的 agent harness”所需要的执行路线图。
>
> 背景分析见：
> - [docs/aelin-docs-foundation/reference/deepagents-official-gap-analysis.md](/D:/Github/Aelin/docs/aelin-docs-foundation/reference/deepagents-official-gap-analysis.md)

## Goal

把 Aelin 当前的 DeepAgents 接入，从下面这种状态：

- 官方中间件仍在
- 自定义工具和补丁层很多
- 文件、执行、artifact、subagent 观测彼此割裂

收敛成下面这种状态：

- 文件语义清晰且统一
- 执行语义清晰且统一
- artifact 有正式交付链路
- subagent / planning / long-running 状态前端可见
- tool history / tool_call_id 协议稳定
- 复杂任务不再主要表现为“看起来在做事，但最终没有交付”

## Progress Update (2026-03-30)

- [x] 已选择当前短期路线：`StateBackend` 继续作为 scratch/runtime state，逐步补齐 artifact export / visibility bridge，而不是本轮直接切到统一 sandbox/backend。
- [x] 前端已经直接消费官方 runtime 数据：`subagents`、`todos`、`values`、`tool calls`、`messages metadata`。
- [x] 聊天区和右侧执行区都已能展示运行时交付物卡片。
- [x] `state/files` 中的运行时文件已可直接预览与下载。
- [x] `execute` 产物已开始回流为可见 artifact：桌面插件会采集本次命令新增/修改的常见输出文件，并通过 tool result 传回前端展示。
- [x] 常见类型预览已打通：`png/jpg/webp`、`pdf`、`md/txt/json/html/svg`。
- [x] 对不可原生预览但可交付的二进制文件，已经提供下载占位能力（如 execute 产出的 `zip/docx/pptx/xlsx`）。
- [x] 已补一条可复用的真实 LangGraph query smoke 脚本：`backend/scripts/run_langgraph_query_smoke.py`。
- [x] DeepAgents system prompt 已改成按真实 tool list 动态生成，不再无条件宣称存在 `execute`。
- [x] 模型超时日志已补充真实 tool 名称预览与最后一条用户消息长度，便于判断是否卡在首个 tool call 前。
- [x] 已修复 runtime agent correctness bug：`agent_server/graph.py` 不再复用带有闭包运行时状态的 DeepAgents agent，避免 `ToolPolicyUsage` / `tool_runs` 跨 run 泄漏。
- [x] 已确认桌面 execute 真实路由问题来自“旧打包桌面端仍在运行”，不是后端 wrapper 错接；当前使用新 pack 的桌面 runtime 后，`POST /v1/desktop/command/execute` 已真实可用。
- [x] 桌面 execute 允许根目录已增强：当前源码 checkout / unpacked 包运行时可自动识别 workspace root，允许在 repo 工作区内使用 `cwd`。
- [x] 桌面 execute 已增加命令归一化：当模型已提供 `cwd` 却又重复拼 `cd <same-cwd> && ...` 时，会自动剥离冗余前缀，减少 Windows 命令失败。
- [x] Windows execute shell 语义已补强：`execute` 现支持显式 `shell` 参数；桌面 runtime 在 Windows 下也会自动识别 PowerShell cmdlet 并切到 `powershell`，减少 `cmd.exe` 误执行。
- [x] 前端 artifact 交付入口已统一：blob 预览、下载、本地文件打开现在走同一套 `artifactActions` 流程；对具备宿主绝对路径的 execute 产物会额外提供 `Open file / Open local`。
- [x] 桌面插件已增加本地文件打开端点：`POST /v1/desktop/path/open`，后端同步暴露 `POST /api/v1/aelin/device/path/open`。
- [x] 当前分支完整后端测试已通过：`pytest -q` => `113 passed`。
- [ ] 尚未完成正式后端 artifact registry / download endpoint。
- [ ] 尚未完成 `write_file` / `execute` / sandbox 统一文件世界。
- [ ] 尚未完成真实任务 smoke matrix 的全量覆盖。

## Latest Real Smoke Evidence (2026-03-30)

- [x] 直接桌面插件 execute 真实链路已成功：
  - 真实调用 `POST http://127.0.0.1:21914/v1/desktop/command/execute`
  - 成功生成 `aelin_execute_smoke.md` + `aelin_execute_smoke.png`
  - 插件返回 `artifact_count=2`
- [x] LangGraph 真正聊天链路中的“纯文本 query”已成功：
  - Query: `请只回复 ok。`
  - 结果：约 5 秒完成，最终 assistant 消息为 `ok`
- [x] LangGraph 真正聊天链路中的“带工具意图 query”已复现失败：
  - Query A：要求使用 `execute` 生成 `smoke.md + pixel.png`
  - Query B：要求使用 `execute` 仅生成一个 `smoke.md`
  - 结果：两次都在 `75s` 处返回“模型生成超时”
  - 共同特征：最终 state 里没有 `files`，真实落盘目录没有交付物，stream 中没有任何 `tool_calls`
- [x] 更细一层的 live probe 已完成：
  - Query C：`请读取 /runtime/capabilities.json，并只返回其中 tools 数组的 JSON。`
  - 结果：`read_file` 已真实调用成功，并成功读到了 `tools=[web_search, attachment_search, google_workspace, device, screen_get, execute]`
  - 但在读完能力文件后，后续模型阶段仍然在 `75s` 超时
- [x] 当前结论已经再次收敛：
  - `execute` 工具已经真实挂载到 live run 中，不是“工具没接上”
  - artifact bridge 也不是主要故障点
  - 主瓶颈是“真实聊天链路中的模型在工具选择 / 工具后续响应阶段不稳定”，而不是 `execute` 本身不可用
  - 具体表现有两种：
    - 一部分 query 在首个 tool call 前直接超时
    - 另一部分 query 能发出 `read_file` 等 tool call，但会在后续模型阶段继续超时或幻觉出“没有 execute 工具”

这意味着接下来的优先级应调整为：

- [ ] 强化“模型首个 tool call 前”的可观测性：明确记录 prompt 规模、skills 暴露量、memory 注入量、是否在首个 tool call 前超时。
- [ ] 缩小真实聊天链路下的 tool-calling 负担：减少不必要的 skills / prompt 负担，验证是否能恢复首个工具调用。
- [ ] 建立一组固定真实 query smoke：
  - no-tool 对照组
  - 单 `execute` 文件生成
  - 单 `write_file` 文件生成
  - 至少一个多交付物任务

## Latest Real Smoke Evidence (Post Fixes, 2026-03-30)

- [x] 已修复“新 run 首个 execute 直接继承 stalled / no_progress”的 correctness 问题：
  - 原因是 `agent_server/graph.py` 复用完整 DeepAgents agent，导致闭包内的 `ToolPolicyUsage` / `tool_runs` 跨 run 共享。
  - 修复后，同一上下文下 runtime agent 每次 run 都会重新构建。
  - 回归测试：`backend/tests/test_agent_server_graph.py`
- [x] 已确认 execute live chain 真实可用：
  - 真实 smoke query 成功用 `execute` 在本地目录创建 `smoke.md`
  - `fs_changes.created = ["smoke.md"]`
  - 最终结果文件：
    - `D:\Github\Aelin\output\langgraph-query-smoke\watch-execute-cache-fix-live3-20260330-232818\smoke.md`
  - 证据 JSON：
    - `D:\Github\Aelin\output\langgraph-query-smoke\final-execute-after-cache-fix-8002\11fba1e3-9036-4bbf-9bbb-643b718b867b.json`
- [x] 已确认 execute 多交付物链路可用：
  - 真实 smoke query 成功创建两个文件：`summary.md` + `meta.json`
  - `fs_changes.created = ["meta.json", "summary.md"]`
  - 最终结果文件：
    - `D:\Github\Aelin\output\langgraph-query-smoke\watch-execute-multi4-20260330-233436\summary.md`
    - `D:\Github\Aelin\output\langgraph-query-smoke\watch-execute-multi4-20260330-233436\meta.json`
  - 证据 JSON：
    - `D:\Github\Aelin\output\langgraph-query-smoke\final-multi-artifact-after-cache-fix-8002\e5e1b84d-bae7-4658-a697-4dfb3e43010b.json`
- [x] 当前 execute 的主要剩余问题已从“工具不可用 / 路由不存在 / 状态泄漏”收敛为“Windows 命令 shaping 仍有残余不稳定”：
  - 例如模型仍可能先尝试 `Set-Content ...`（在 `cmd.exe` 语义下失败），随后再退到 `echo ...`
  - 或在多行文本场景里生成对 Windows cmd 不友好的单条命令
  - 这已经是 prompt / command-shaping 问题，而不是 execute capability 缺失
- [x] 另一个已明确识别的测试噪声源：
  - `langgraph dev` 的 watch reload 会中断正在跑的 smoke run
  - 因此后续真实 smoke 证据应优先取“无 reload 干扰”的 run id / JSON 文件

## Latest Validation Update (2026-03-31)

- [x] 直连桌面插件的本地文件打开已成功：
  - `POST http://127.0.0.1:21914/v1/desktop/path/open`
  - 成功打开：`D:/Github/Aelin/README.md`
- [x] 直连桌面插件的显式 PowerShell execute 已成功：
  - 请求包含：`shell='powershell'`
  - 成功生成：
    - `D:\Github\Aelin\output\execute-shell-proof\shell-proof.txt`
  - 插件返回：
    - `artifact_count=1`
    - `shell='powershell'`
- [x] 直连桌面插件的 Windows PowerShell 自动识别 execute 已成功：
  - 请求未显式提供 `shell`
  - 命令体使用 `Set-Content`
  - runtime 自动归类为 `shell='powershell'`
  - 成功生成：
    - `D:\Github\Aelin\output\execute-shell-proof\auto-shell.txt`
- [x] 前端真实加载 smoke 已成功：
  - 通过 Playwright 真实打开：`http://127.0.0.1:5173/`
  - 页面标题：`Aelin`
  - 快照证据：
    - `D:\Github\Aelin\.playwright-cli\page-2026-03-30T16-21-23-383Z.yml`
  - 截图证据：
    - `D:\Github\Aelin\.playwright-cli\page-2026-03-30T16-21-52-237Z.png`
- [ ] LangGraph 真实 smoke matrix 已发起但本轮未完成：
  - 覆盖 case：
    - `matrix-md-json-20260331`
    - `matrix-html-20260331`
    - `matrix-svg-20260331`
  - 当前共同失败特征：
    - stream 中只有 `metadata/values/updates/error`
    - 没有 `tool_calls`
    - 没有最终 assistant content
    - backend 日志明确显示：`openai.APIConnectionError: Connection error.`
  - 这说明本轮阻塞点不是 execute / artifact bridge，而是上游模型连接在首个 model step 前后失败。
  - 证据 JSON：
    - `D:\Github\Aelin\output\langgraph-query-smoke\final-matrix-md-json-20260331\39e70c4d-277f-422f-9419-6acbedffe746.json`
    - `D:\Github\Aelin\output\langgraph-query-smoke\final-matrix-html-20260331\8e12673b-6453-441c-9253-9aafddf7a852.json`
    - `D:\Github\Aelin\output\langgraph-query-smoke\final-matrix-svg-20260331\38d6db2d-eef5-493a-8528-f320009f6f50.json`
    - `D:\Github\Aelin\output\langgraph-query-smoke\final-connectivity-retry-20260331\6bf48c1d-2310-4798-9bf7-4bd4389c2ccf.json`

## Success Criteria

- [ ] 用户发起“生成文件/海报/项目/文档”类任务时，系统能稳定输出真实交付物，而不是只输出一段文本说明。
- [ ] `write_file`、`execute`、`read_file`、artifact 呈现之间形成明确闭环。
- [ ] 用户能够在前端确认 subagent 是否被创建、做了什么、是否完成。
- [ ] 前端能稳定显示最终交付物，并支持点击、预览、下载。
- [ ] `Invalid tool_call_id` 类协议错误被压到接近 0。
- [ ] 复杂 skill 任务的失败原因从“模糊超时”转成“明确的能力边界/真实错误”。

## Guiding Principles

- [ ] 不先从“调大超时”入手，先解决运行时语义不一致。
- [ ] 不再继续堆叠临时补丁去掩盖 backend / artifact / protocol 的根问题。
- [ ] 把“最终交付物”当成正式产品能力，而不是聊天输出的附属品。
- [ ] 优先让系统行为可观测，再做模型侧优化。
- [ ] 优先收敛 runtime 与 app layer 边界，避免继续把产品 glue 写进 DeepAgents 语义层。

## Phase 0: 定架构目标

### 0.1 明确目标形态

- [ ] 在文档中明确 Aelin 目标是：
  - 方案 A：`StateBackend` 作为 scratch space，另建 artifact export pipeline
  - 方案 B：统一 sandbox/backend，让文件读写执行共用同一运行时文件世界
- [ ] 给出两种方案的安全、复杂度、开发量、用户体验对比。
- [x] 明确短期采用哪条路线，避免后续任务一半按 A、一半按 B 做。

当前短期路线说明：

- 先沿用方案 A：`StateBackend` 负责 scratch/runtime state。
- 对 `write_file` 产物，继续通过 `values.files` 暴露给前端。
- 对 `execute` 产物，先通过 desktop plugin + tool result artifact bridge 回流到前端。
- 等 artifact registry、下载入口、thread/run 级工作目录语义稳定后，再评估是否切到统一 sandbox/backend。

### 0.2 明确文件分层

- [ ] 定义三类文件概念：
  - scratch files：agent 内部临时文件
  - runtime files：对当前 thread 有意义但未必是最终交付物
  - deliverables / artifacts：最终要呈现给用户的文件
- [ ] 给每类文件定义生命周期、存储位置、可见范围和回收方式。

### 0.3 明确系统边界

- [ ] 定义 harness layer 职责：
  - backend
  - tools
  - sandbox / execution
  - memory
  - artifacts
  - runtime protocol
- [ ] 定义 app layer 职责：
  - auth
  - workspace / user scoping
  - product API
  - desktop integration
  - UI rendering
- [ ] 把“哪些逻辑不应再继续写进 DeepAgents glue 层”写清楚。

## Phase 1: 统一文件语义与执行语义

### 1.1 做一次运行时能力审计

- [ ] 列出当前所有和文件/执行相关的入口：
  - 官方 `read_file`
  - 官方 `write_file`
  - 官方 `edit_file`
  - 官方 `task`
  - Aelin 自定义 `execute`
  - 技能文件挂载
  - `/runtime/capabilities.json`
- [ ] 对每个入口标明：
  - 实际作用在哪个 backend / 环境
  - 是否落盘
  - 是否用户可见
  - 是否可被后续工具继续消费

### 1.2 收敛为单一文件世界，或显式桥接双文件世界

- [ ] 如果继续保留 `StateBackend`：
  - 明确其仅用于 scratch / runtime state
  - 禁止让模型误以为这里的文件就是宿主机真实文件
  - 增加从 state files 导出到 artifact 的正式桥
- [ ] 如果引入统一 sandbox/backend：
  - 让 `write_file`、`edit_file`、`read_file`、`execute` 基于同一 backend
  - 确保 thread / run 级工作目录稳定可复用
  - 明确清理与持久化策略

### 1.3 收敛 execute 设计

- [ ] 决定是否继续保留当前桌面插件 `execute` 为主通道。
- [ ] 如果保留：
  - 明确它与 DeepAgents 官方 execute 的差异
  - 明确它与 state files 的桥接方式
  - 明确 cwd 与允许路径范围
- [ ] 如果替换：
  - 评估切换到更接近官方 `SandboxBackendProtocol` 的实现
  - 补足本地 / 桌面场景需要的安全控制

### 1.4 收敛 capability 宣告

- [ ] 让 `/runtime/capabilities.json` 反映真实能力面，而不是只列自定义工具。
- [ ] 能力文件中明确区分：
  - 官方 middleware 工具
  - Aelin 自定义工具
  - 真实写入能力
  - 真实执行能力
  - artifact 输出能力

## Phase 2: 建立正式 artifact pipeline

### 2.1 定义 artifact 数据模型

- [ ] 定义 artifact 的最小元数据结构：
  - id
  - file_name
  - mime_type
  - size
  - source_run_id / thread_id
  - source_path
  - previewability
  - downloadability
  - created_at
- [ ] 定义 artifact 与 scratch/runtime files 的转换条件。

### 2.2 后端 artifact 服务

- [ ] 增加 artifact registry / service，负责：
  - 识别生成结果
  - 存储元数据
  - 提供下载/预览入口
  - 处理清理策略
- [ ] 明确 artifact 内容来源：
  - state file 导出
  - sandbox file 回收
  - execute 产物采集
  - 外部工具生成物

### 2.3 agent 到 artifact 的桥接

- [ ] 定义 agent 如何显式声明“这不是 scratch，而是最终交付物”。
- [ ] 设计自动识别规则：
  - 常见扩展名
  - 明确输出目录
  - tool result 标记
  - post-run artifact collector
- [ ] 让海报、PPT、PDF、DOCX、XLSX、项目模板这些典型任务都能走同一套交付链路。

### 2.4 前端 artifact 呈现

- [x] 在聊天区或右侧执行区展示 artifact 卡片。
- [x] 支持最基本的：
  - 点击打开
  - 预览
  - 下载
- [x] 对常见类型做原生预览：
  - `png/jpg/webp`
  - `pdf`
  - `md/txt/json`
  - 可选：`docx/pptx/xlsx` 先走下载占位
- [x] `docx/pptx/xlsx/zip` 等二进制交付物在 execute artifact 场景下可先走下载占位。
- [ ] 统一“所有文件都应可点击可预览”的产品体验。

## Phase 3: 提升 subagent / planning / long-running 可观测性

### 3.1 官方 runtime data 原生透传

- [x] 确保前端直接消费官方运行态：
  - subagents
  - todos
  - values
  - tool calls
  - messages metadata
- [ ] 减少“最后只拿一个 answer”的退化路径。

### 3.2 task / subagent 可见化

- [ ] 显示某次 run 是否调用了 `task`。
- [ ] 显示调用了哪个 subagent type。
- [ ] 显示 subagent 的开始、进行中、完成、失败状态。
- [ ] 显示 subagent 最终摘要，而不只是把它吞进最终 answer。

### 3.3 官方文件工具调用可见化

- [ ] 不只追踪自定义工具，也要让官方 `read_file/write_file/edit_file/task` 可观测。
- [ ] 在右侧执行面板里明确显示：
  - 读了哪些文件
  - 写了哪些文件
  - 是否写入成功
  - 是否导出为 artifact

### 3.4 长任务状态表达

- [ ] 在 UI 中区分：
  - planning
  - tool execution
  - subagent delegation
  - artifact generation
  - final delivery
- [ ] 避免用户看到“长时间无反馈，只剩一个超时提示”。

## Phase 4: 收敛协议补丁，修稳 tool history

### 4.1 清查现有补丁层

- [ ] 梳理当前所有影响消息协议的层：
  - 官方 `PatchToolCallsMiddleware`
  - Aelin 自定义 `DeepAgentsToolMessageSanitizerMiddleware`
  - 模型超时中间件
  - 其他 message transform / history cleanup 逻辑

### 4.2 修正 orphan tool message 策略

- [ ] 确认是否还需要当前 sanitizer 的“伪造 AI tool call”逻辑。
- [ ] 如果保留，补严格的 provider 兼容测试。
- [ ] 如果不保留，收敛到官方 patch 机制，减少双重修补。

### 4.3 收紧 tool_call_id 协议测试

- [ ] 增加以下场景测试：
  - 正常单工具调用
  - 多工具并发调用
  - 取消中的 dangling tool call
  - orphan tool message
  - subagent + tool 混合历史
  - OpenAI-compatible provider 严格校验场景

## Phase 5: 优化模型负担与任务规划

> 这一阶段应在前面几阶段完成后再做。否则只是把根问题包起来。

### 5.1 收敛系统提示与能力认知

- [ ] 精简系统提示中与实际能力不一致的表达。
- [ ] 避免模型误以为某些文件写入等于真实交付。
- [ ] 明确告诉模型：
  - scratch files 与 deliverables 的差异
  - 什么时候该导出 artifact
  - 什么时候该调用 subagent

### 5.2 优化复杂任务默认路径

- [ ] 对典型复杂任务设计推荐执行路径：
  - 海报生成
  - 项目脚手架生成
  - 研究报告生成
  - 多文件文档导出
- [ ] 减少模型在“先 write_file 超大 blob 还是先 subagent 还是先 execute”之间反复试探。

### 5.3 调整 timeout 策略

- [ ] 在语义对齐后，再重新评估：
  - 模型生成超时
  - 工具超时
  - execute 超时
  - subagent 超时
- [ ] 把“粗暴统一 75s”拆成更可诊断的超时分类。

## Phase 6: 测试矩阵与真实链路验证

### 6.1 单元与集成测试

- [ ] 为 backend 语义新增测试：
  - state write
  - artifact export
  - sandbox/local execute
  - file visibility after execute
  - execute visibility after write
- [ ] 为 protocol 层新增测试：
  - tool_call_id
  - cancellation
  - subagent state handoff

### 6.2 真实任务 smoke tests

- [ ] 做固定 query 的真实链路 smoke test：
  - “生成一张 PNG 海报并交付”
  - “生成一个可运行 Python 项目并交付 zip 或目录”
  - “生成 PDF 报告并交付”
  - “读取附件 -> 分析 -> 输出文档”
- [ ] 每个 smoke case 都要验证：
  - run 未卡死
  - 若使用 subagent，前端可见
  - 最终 artifact 可点击
  - artifact 可预览/下载

### 6.3 回归面板

- [ ] 建立一组 dashboard / checklist，至少持续追踪：
  - artifact 生成成功率
  - subagent 调用成功率
  - tool_call_id 协议错误数
  - 模型超时率
  - 用户最终拿到交付物的成功率

## Phase 7: 前端体验打磨

> 这一阶段不是不重要，而是应该建立在语义对齐后做。

### 7.1 图和执行态视觉升级

- [ ] 让 LangGraph / execution pane 更接近“运行时视图”，而不是摘要视图。
- [ ] 提升：
  - 高亮
  - 状态区分
  - 深浅模式
  - 可读性
  - 长任务下的稳定渲染

### 7.2 文件与 artifact 的统一交互

- [ ] 让所有交付类文件在 UI 中都有一致的点击行为。
- [ ] 将“预览”和“下载”做成明确动作，而不是藏在聊天文本里。

### 7.3 长任务用户心智

- [ ] 在 UI 中用更明确的文案区分：
  - 正在规划
  - 正在执行
  - 正在生成交付物
  - 正在导出
  - 已完成
- [ ] 避免用户把“模型在组织参数”误读为“系统卡死”。

## Phase 8: 文档与迁移治理

### 8.1 收敛旧文档与旧心智

- [ ] 标记哪些旧 TODO / 旧设计文档已经被这份路线图取代。
- [ ] 避免团队继续沿用“只要接上 DeepAgents 就自然会有完整 harness”的错误预期。

### 8.2 输出正式架构文档

- [ ] 在 Phase 0 和 Phase 1 结束后，补一份正式架构文档：
  - 文件语义
  - 执行语义
  - artifact 流转
  - frontend runtime contract

### 8.3 对外/对内表述统一

- [ ] 明确 Aelin 当前定位到底是：
  - DeepAgents 接入态产品
  - 还是完整 harness
- [ ] 在定位未补齐前，不要默认宣传“复杂多步交付链路已经稳定”。

## Recommended Execution Order

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 6
7. Phase 5
8. Phase 7
9. Phase 8

## What Not To Do First

- [ ] 不要先调大模型超时。
- [ ] 不要先只修 graph 视觉样式。
- [ ] 不要先只加更多自定义补丁来掩盖 tool history 问题。
- [ ] 不要先为单个 skill 写特判。
- [ ] 不要在没有 artifact pipeline 的前提下继续承诺“最终文件一定可交付”。

## Short Version

如果只保留最关键的五件事，应该先做：

- [ ] 先定：Aelin 的文件与执行到底走统一 sandbox，还是走 `StateBackend + artifact export`
- [ ] 补 artifact pipeline，让最终交付物成为正式产品能力
- [ ] 把 subagent / planning / file operations 真正透给前端
- [ ] 收敛 tool history 补丁，修稳 `tool_call_id`
- [ ] 再做 timeout、UI、图样式和复杂 skill 成功率优化
