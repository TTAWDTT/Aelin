# 3-13 Plan

> 状态说明：本文件只用于跟踪后续 plane 体系改造进度。当前仅建立待办与验收标准，暂不开始实际实现。

## 1. 将 plane 提升为 agent loop 的正式监督主线

- [x] 实现：一旦 `plane.delegate` 成功，agent loop 进入 plane 监督态，而不是把结果当作普通工具输出处理
- [x] 验收：存在活跃 plane task 时，后续回合默认优先围绕该 task 进行推进
- [x] 验收：plane task 未进入终态前，agent loop 不会轻易直接生成最终结论
- [x] 验收：相关测试覆盖 `delegate -> status/continue -> terminal` 的主监督流程

## 2. 强化 active plane task 的复用机制

- [x] 实现：当 workspace 中已有活跃 plane task 时，优先复用而不是重新 `delegate`
- [x] 验收：同一类连续网页任务默认续跑已有 task，而不是创建第二个 task
- [x] 验收：仅在明确需要时才重新新建 plane task
- [x] 验收：测试覆盖“已有 active task 时继续任务”的行为

## 3. 将 waiting_user 做成正式暂停协议

- [x] 实现：当 plane 返回 `waiting_user` 时，agent loop 本轮停止继续推进该任务之外的动作
- [x] 实现：用户下一次回复时，默认视为继续当前 waiting task
- [x] 验收：Aelin 能清晰向用户说明所需配合事项
- [x] 验收：登录、验证码、人工确认等场景可以从 `waiting_user` 平滑恢复
- [x] 验收：测试覆盖 `waiting_user -> 用户补充输入 -> continue/status` 的恢复流程

## 4. 为 plane supervision 分离独立预算

- [x] 实现：将 plane 监督调用预算与普通 tool 调用预算分离
- [x] 验收：复杂 plane 任务不会因为普通工具预算过紧而被过早截断
- [x] 验收：plane 相关预算具备可配置性，并保持默认值合理
- [x] 验收：测试覆盖 plane 连续监督调用在预算内可稳定完成

## 5. 让最终总结建立在 plane runtime 产物之上

- [x] 实现：最终回答优先基于 plane 的 `events`、`artifacts`、`state` 等 runtime 数据
- [x] 验收：plane 未完成时，Aelin 不会将阶段性进展误当作最终结论
- [x] 验收：plane 完成后，Aelin 的总结能反映最近的产物与状态变化
- [x] 验收：测试覆盖“有 artifacts/events 时优先基于其总结”的行为

## 6. 将 browser plane 继续上提为通用 plane runtime

- [x] 实现：抽象出更统一的 plane runtime、registry、adapter 协议
- [x] 实现：降低当前 browser/PinchTab 路径中的特化逻辑占比
- [x] 验收：新增一个 plane 时，无需重写整套监督、持久化与恢复机制
- [x] 验收：browser plane 仍保持现有行为不回退
- [x] 验收：测试覆盖 registry/adapter 的基本通用能力

## 7. 明确 plane metadata 与 skill 的分工

- [ ] 实现：为 plane 建立清晰的 metadata 结构，用于描述能力、适用场景、动作与边界
- [ ] 实现：保留 skill 作为“如何更好使用该 plane”的增强说明层
- [ ] 验收：Aelin 可以同时获得 plane 的能力信息与使用策略信息
- [ ] 验收：代码结构上能明确区分 plane metadata 与 skill prompt 的职责
- [ ] 验收：至少 browser plane 完成这一分层落地

## 8. 将 skill 从直接注入逐步演进为目录式资源

- [ ] 实现：先提供 skill catalog 级别的信息，而不是只把 skill 正文直接注入
- [ ] 实现：支持按需展开 skill 正文，而不是始终整段注入
- [ ] 验收：Aelin 可以先看到 skill 摘要/元数据，再决定是否深入使用
- [ ] 验收：skill 与 tool、plane 在资源层级上更统一
- [ ] 验收：测试覆盖 skill catalog、按需展开与筛选逻辑
