# Remote Control + Agent Loop 收敛修复方案

## 目标

本次工作整合为一条 PR，但拆成多个清晰 commit，目标不是简单“把 remote control 搬进来”，而是完成以下四件事：

1. 统一消息入口层级：让 remote control 来源的消息与 chat UI 输入在系统内进入同一条 agent-loop 主链路。
2. 收敛设备原子能力：把 remote control 里证明有效的 device atomic actions 抽象成可复用能力，供 Aelin 在 agent loop 中调用，而不是保留一条独立的“命令解析 + 直连执行”旁路。
3. 体检 chat UI 链路：检查 chat UI 的 SSE / 网络错误 / 阻塞是否会影响消息发送、流式接收、状态恢复，并区分“前端显示异常”和“后端实际未执行”。
4. 排查额外集成风险：重点检查 API 契约漂移、desktop plugin 端点不对齐、共享资源争用、日志可观测性不足等问题。

本方案先产出设计和提交策略，不在本轮直接改代码。

## 现状判断

### 1. Chat UI 目前走的是完整 agent-loop 主链路

当前 chat UI 的主路径是：

- `frontend/src/features/chat/hooks/useChatStream.ts`
- `frontend/src/shared/api/sse.ts`
- `backend/app/routers/aelin_chat.py`
- `backend/app/services/aelin_core.py`
- `backend/app/services/aelin_agent_loop.py`
- `backend/app/services/aelin_loop_*`
- `backend/app/services/aelin_tools.py`

这条链路会进入完整的 preflight、tool policy、LLM round、tool dispatch、SSE 回传流程。

### 2. PR29 中的 remote control 不是同层接入

结合已合并的 PR29 设计判断，remote control 的思路是：

- Feishu / remote ingress
- command parse
- direct device execution

也就是说，它本质上是一条“远控命令链路”，不是“消息进入 agent loop 之后由 agent 自主规划并调度工具”的链路。

这意味着用户目前的判断是对的：

- chat UI 输入：直接进入 agent loop
- remote control：更像单独的 chat + device tools / direct command 执行链路

### 3. 当前分支并不包含 PR29 的完整远控子系统

当前工作区里没有看到 PR29 那套完整文件：

- `backend/app/routers/aelin_remote_control.py`
- `backend/app/services/remote_control.py`
- `backend/app/services/feishu_bot.py`

所以当前分支真实情况不是“remote subsystem 已完整在本地，只等接线”，而是：

- 当前分支已有 agent loop
- 当前分支已有一部分 device / desktop 能力
- PR29 引入过一套独立远控子系统思路

后续工作应当是“吸收其有效部分并统一架构”，而不是机械恢复其整条旁路。

### 4. 当前分支已有部分 device 能力，但接口并未完全收敛

当前分支已经存在的能力包括：

- `screen_get`
- `device.capabilities`
- `device.processes`
- `device.mode_apply`

相关实现位于：

- `backend/app/services/aelin_tools.py`
- `backend/app/services/device_center.py`
- `backend/app/routers/aelin_device.py`

这说明 remote control 所体现出的“原子设备动作”并不是从零开始，当前代码库已有可以复用的基础。

### 5. 当前分支存在明显的契约漂移风险

已经确认一个高风险点：

- `backend/app/services/aelin_tools.py` 中 `_tool_device` 把 `apply_device_mode(...)` 当成 dict 使用
- `backend/app/services/device_center.py` 中 `apply_device_mode(...)` 实际返回 tuple

这类漂移意味着：

- agent loop 侧 device 工具结果可能不稳定
- 远控原子动作如果继续直接叠加，反而会进一步放大接口分裂
- 在统一 remote 与 agent loop 前，必须先做 contract cleanup

### 6. desktop plugin 端点能力可能与 PR29 预期不一致

当前能确认的 desktop plugin 端点包括：

- `/v1/device/screen/capture`

但尚未确认 PR29 风格的端点是否已具备，例如：

- `/v1/desktop/url/open`
- `/v1/desktop/app/activate`

因此，PR29 中类似 `open_url`、`open_aelin` 的原子动作，不能直接假设在当前分支可用，必须先做端点能力对齐与降级策略设计。

## 设计原则

### 原则 1：统一入口，不统一外部协议

remote control 可以保留自己的外部来源形态，例如 Feishu、HTTP webhook、future mobile trigger；但一旦进入后端，就应该尽量尽早转换为统一的内部消息模型，再进入 agent loop。

换句话说：

- 外部入口可以不同
- 内部执行主链路应尽量一致

### 原则 2：保留原子动作，但不保留独立旁路

PR29 的价值不在于它有一条独立的“命令解析 + 直连执行”链路，而在于它沉淀出一组对用户很有价值、粒度合适、可靠性较高的 device atomic actions。

正确方向是：

- 抽出这些动作
- 统一动作 schema、返回结构、错误模型
- 让 agent loop 可调用这些动作

而不是：

- 继续维护两套长期并行的执行系统

### 原则 3：先清 API 契约，再做入口收敛

如果当前 device action 层本身存在 contract drift，那么把 remote control 接入 agent loop 只会把问题扩散到更多入口。

因此顺序必须是：

1. 先统一 device atomic action contract
2. 再让 chat UI / remote control 共用
3. 最后再优化 agent prompt / policy 去鼓励优先使用 atomic actions

### 原则 4：把“前端报错”和“后端未执行”分开诊断

chat UI 里的 `network error`、SSE 中断、callback 异常、状态未恢复，和 remote control 的消息传递不是一个层面的问题。要分别看：

- 前端是否真的没发出去
- 后端是否已执行但前端没显示好
- SSE 是否被中途断开
- 共享 backend 资源是否被拖慢

## 对用户意见 1 和 2 的审阅结论

### 1. “将 remote control 来的消息和 chat UI 前端输入的消息进行相同的处理，进入 agent loop”

结论：方向正确，应该做。

但建议不是“把 remote command parser 塞进 agent loop”，而是：

- remote ingress 先转换成统一的内部 `agent request`
- 再进入和 chat UI 一样的 agent-loop 主链路

这样做的好处：

- 推理逻辑一致
- 工具策略一致
- 观测日志一致
- 后续 skill / tool / policy 扩展只维护一套

### 2. “将 remote control 这个改动中引入的 device 原子工具，并鼓励 Aelin 使用原子工具”

结论：方向正确，但要先做工具层收敛。

建议不要直接把 PR29 的 command parser 概念搬进 agent loop，而是抽出真正稳定有价值的 atomic actions，例如：

- `status`
- `screenshot`
- `processes`
- `mode_apply`
- 可能的 `open_url`
- 可能的 `open_aelin`

然后：

- 统一 schema
- 统一返回结构
- 接入 `aelin_tools` / `aelin_tool_policy`
- 再通过 system prompt / tool policy / examples 鼓励优先调用这些原子动作

## 单 PR 多 Commit 方案

### Commit 1: 审计并统一 device atomic action contract

目标：

- 统一 device action 的入参与返回值
- 修复 `device_center` 与 `aelin_tools` 间的 contract drift
- 明确错误码、降级语义、字段命名

主要工作：

- 审核 `backend/app/services/device_center.py`
- 审核 `backend/app/services/aelin_tools.py`
- 审核 `backend/app/routers/aelin_device.py`
- 收敛 `mode_apply`、`processes`、`capabilities`、`screen capture` 的返回结构
- 对 `open_url` / `open_aelin` 这类动作先做能力探测，未支持则返回显式 `unsupported`

预期产物：

- 一套稳定的 atomic action contract
- 明确的 typed response / error model
- 对应测试补齐

这是整个 PR 的前置 commit，没有它，后续统一 remote 入口风险很高。

### Commit 2: 抽出统一的 remote ingress -> agent request 适配层

目标：

- 让 remote 来源的消息在内部转换为统一 `agent request`
- 不直接执行设备动作

主要工作：

- 设计 `remote ingress payload -> internal agent request` 的适配层
- 统一 remote / chat UI 的最小消息语义：
  - query
  - workspace
  - attachments / screenshots
  - source
  - session / correlation identifiers
- 保留 remote 来源 metadata，便于审计和回放

注意：

- 这一步不一定要求先把 Feishu 重新完整接回当前分支
- 更重要的是定义“远控消息进入 agent loop”的标准边界

### Commit 3: 将 remote control 接入 agent-loop 主链路

目标：

- remote 消息与 chat UI 消息进入同一后端执行主链路

主要工作：

- 新增或恢复 remote router/service，但只负责入口适配与认证
- 复用 `aelin_core` / `aelin_agent_loop`
- 统一 trace / request id / logging fields
- 确保 remote 请求也能产出完整 round / tool / final answer 日志

成功标准：

- remote 来源消息不再走“命令解析 + 直连 device execute”的独立主路径
- remote 来源与 chat UI 来源在日志上能对齐到同一类 agent loop 生命周期事件

### Commit 4: 将 remote 证明有效的 atomic actions 并入 agent tools/policy

目标：

- 把 remote control 的高价值 device actions 纳入 agent 可用工具面
- 引导 Aelin 优先调用原子动作，而不是写大而模糊的浏览器/设备请求

主要工作：

- 扩充 `aelin_tools` 中的原子工具暴露方式
- 更新 `aelin_tool_policy`
- 评估是否需要拆分 `device` 大工具为更清晰的 atomic tool surface
- 补充 prompt / description / examples，让模型更容易稳定命中正确动作

重点：

- 不是盲目增加工具数量
- 而是提高工具语义清晰度与命中率

### Commit 5: Chat UI SSE / network / blocking 体检与修复

目标：

- 排查并修复 chat UI 侧会导致“看起来像没发出去”或“network error 但后端其实跑了”的问题

重点检查点：

- `frontend/src/shared/api/sse.ts`
- `frontend/src/features/chat/hooks/useChatStream.ts`
- `frontend/src/features/chat/hooks/chatStreamHelpers.ts`
- `backend/app/routers/aelin_chat.py`

主要工作：

- 核查 abort 与新请求切换时是否会误伤正在进行的流
- 区分 callback exception 与 transport error
- 检查非 2xx 响应的可见性与用户提示
- 检查 SSE 心跳、done/final 事件、异常收尾的一致性
- 检查前端状态恢复是否会因流中断残留“正在思考”

产出目标：

- 前端报错更可解释
- UI 卡住概率下降
- 能明确判断“是后端慢”还是“是前端流状态处理异常”

### Commit 6: 共享资源与可观测性补强

目标：

- 确认 chat UI 与 remote 在共享 backend、desktop plugin、LLM、tool hub 时不会互相拖垮
- 把后续调试所需日志补齐

主要工作：

- 为 remote / chat 统一记录 source、request id、workspace、session id
- 记录 ingress latency、queue/preflight latency、round latency、tool latency
- 记录 shared resource errors：
  - desktop plugin unavailable
  - unknown_session_id
  - unsupported desktop endpoint
  - SSE disconnect
- 检查是否存在同步阻塞点导致所有入口一起变慢

这一步会极大降低后续排障成本。

## 需要重点排查的潜在问题

### 1. API 契约已经开始分叉

`device_center`、`aelin_tools`、未来 remote atomic actions 如果继续各自定义返回值，系统会越来越难统一。

### 2. desktop plugin 能力面可能不完整

如果 desktop 端并不支持 `open_url` / `activate_app`，那么 remote control 里看起来很好用的动作，接回 agent loop 后会直接变成伪能力。

### 3. 工具命名与粒度可能影响模型命中率

如果 agent 看到的还是一个过于泛化的 `device` 大工具，而不是清晰的 atomic actions，模型可能仍然更容易产生模糊调用或错误参数。

### 4. chat UI 的错误提示可能掩盖真实后端执行状态

前端一旦把 callback exception、SSE 断流、fetch 异常都归为 `network error`，用户会误以为消息没到后端，但实际上后端可能已经执行完成。

### 5. remote 与 chat 共享 backend 资源，异常会联动

虽然 chat UI 的前端错误通常不会直接影响 remote 消息传输，但以下共享资源问题会同时影响两者：

- backend 主线程阻塞
- LLM 请求慢或重试
- desktop plugin 不可用
- tool call 串行等待过长
- 数据库锁 / 事务拖延

### 6. 旧的 remote parser 逻辑可能与 agent autonomy 冲突

如果保留过重的命令解析前置逻辑，Aelin 的自主规划空间会被削弱，最终形成“两套智能”同时存在、彼此打架的局面。

## 为什么这条 PR 要按这个顺序做

因为真正的目标不是“把 remote control 合进来”，而是：

- 让所有入口共享一条主执行链路
- 让 Aelin 真正学会使用稳定的原子动作
- 让 UI 与 remote 的失败模式可解释、可观察、可定位

如果顺序反过来，先急着接入口，再补 contract，最后才查 SSE 和 observability，会很容易出现：

- 接上了但不稳定
- 出错了但不清楚是哪层错
- 后续每次排障都要重新读全链路

## 验证清单

### Remote / Chat 统一性验证

- chat UI 发消息，进入完整 agent loop，日志字段齐全
- remote 发消息，进入同一 agent loop，日志字段结构一致
- 两条入口都能看到统一的 round/tool/final 生命周期日志

### Atomic Action 验证

- `capabilities`
- `processes`
- `mode_apply`
- `screen capture`
- 若支持则验证 `open_url`
- 若支持则验证 `open_aelin`

每项都需要验证：

- success 返回结构
- unsupported 返回结构
- plugin unavailable 返回结构
- tool policy / agent 调用稳定性

### Chat UI 可靠性验证

- 正常流式回复
- SSE 中途断流
- 前端手动 stop
- 新消息打断旧消息
- 非 2xx 响应
- callback 内部异常不应被误报为 transport failure

### 共享资源验证

- chat UI 和 remote 并发压测时是否互相影响
- desktop plugin 不可用时是否只影响依赖它的动作
- LLM 慢时 UI 是否仍能维持正确状态

## 最终交付标准

当这条 PR 完成后，应达到以下状态：

1. remote control 不再是一个长期独立的“命令旁路”，而是统一进入 agent loop。
2. remote control 沉淀出的高价值 device atomic actions 成为 Aelin 可复用的标准能力。
3. chat UI 的网络错误、流式状态和阻塞问题被显式区分并得到修复或至少可观测。
4. 整个系统对“消息从哪里来”不敏感，但对“能力如何被可靠调用”足够敏感且统一。

## 本文档对后续实现的直接指导

后续真正动手时，建议严格按以下优先级推进：

1. 先修 contract drift 与 desktop capability parity
2. 再定义 remote ingress -> internal agent request 适配层
3. 再接入 agent loop
4. 再收敛 agent atomic tools / policy
5. 最后处理 chat UI SSE / network / observability 收尾

不要跳步骤，否则很容易把架构问题表面上“接通”，但内部复杂度继续升高。
