# Chat Execution Pane 优化待办清单（右侧工具/Plane 展示）

> 目标：让右侧 Execution Pane 更清晰地呈现 Aelin 的工具调用链路与 plane 状态，适配当前黑白灰极简风格，同时与现有 plane + tool 架构对齐。

---

- [ ] 1. 丰富 `ToolCallMeta` 结构与提取逻辑（traceUtils）
  - [ ] 1.1 `ToolCallMeta` 新增字段：`round`、`isWrite`、`latencyMs`、`kind`
  - [ ] 1.2 `extractToolCalls` 能从 `AelinToolStep.detail` 中解析轮次与耗时（若日志中存在相关片段）
  - [ ] 1.3 `isWrite` 与后端工具语义一致：`google_workspace` 写操作（如 `docs_create`）与 `device.open_url` 等被标为写，其余标为读
  - [ ] 1.4 `kind` 能区分至少：`llm_tool` / `plane_tool` / `gws` / `device` / `web` / `core`
  - [ ] 1.5 未能解析出的字段有稳健默认值（例如 `round=1`、`latencyMs=0`、`kind='core'`），不会导致前端崩溃

- [ ] 2. 重构 Tools 页签 UI：按轮次与工具分组的时间轴展示
  - [ ] 2.1 Tools 页签按 `round` 分组显示，每组有清晰的分组头（例如 “Round 1 / Round 2”）
  - [ ] 2.2 每条工具调用以卡片形式展示：包含工具名、provider、status、READ/WRITE 标签、耗时（若有）
  - [ ] 2.3 provider 图标/缩写有固定映射：如 Google / Device / Plane / Web / Core 等，视觉上易区分
  - [ ] 2.4 卡片默认展示简短摘要：从 `detail` 中抽取一段有用信息（如 `docs_create: 创建文档 "xxx"`、`web_search: total=5` 等）
  - [ ] 2.5 卡片可展开/收起，展开后能看到完整 `detail` 文本（自动换行，保持当前字体风格）
  - [ ] 2.6 对 `google_workspace` 文档创建等调用，若 `detail` 中包含可推断出的链接信息（如 `document_id` / `web_url`），展开区显示可点击链接
  - [ ] 2.7 空列表时有友好的占位提示（沿用或更新 `trace.tools.empty` 文案），不会出现空白区域

- [ ] 3. Plane 页签与 Tools 数据联动
  - [ ] 3.1 `PlaneTraceView` 除现有 plane 状态卡片外，新增 “相关工具调用” 小节，仅展示与 plane 相关的工具（如 plane/pinchtab 族）
  - [ ] 3.2 “相关工具调用” 小节展示 2–3 条最近调用，样式与 Tools 卡片简化版保持一致（同一风格）
  - [ ] 3.3 在 Plane 小节中提供 “查看全部工具调用” 操作，点击后切换到 Tools 页签，并滚动到对应轮次/调用区域
  - [ ] 3.4 当没有 plane 相关调用时，小节不显示或有简短提示，避免空容器

- [ ] 4. ExecutionPane 展开/收起行为与布局微调
  - [ ] 4.1 桌面模式下，当某轮对话产生了至少一条工具调用时，ExecutionPane 自动展开（与当前 `isStreaming` 逻辑兼容/整合）
  - [ ] 4.2 没有任何工具调用与 plane 信息的对话轮次中，ExecutionPane 可以保持收起或仅展示一行“无工具调用”的提示，不占用大块空间
  - [ ] 4.3 右侧 pane 的宽高在内容较多时仍保持舒适：默认高度/宽度稍作提升但不破坏整体布局（如 max-w 维持在当前范围内）
  - [ ] 4.4 收起/展开动画保持现在的丝滑风格，与左侧侧边栏展开/收起一致，不出现跳动或闪烁

- [ ] 5. i18n & 文案与风格统一
  - [ ] 5.1 所有新文案（分组标题、READ/WRITE 标签、provider 名、空状态提示）都通过 `chatI18n` 管理，提供中/英双语
  - [ ] 5.2 中英文切换后，ExecutionPane 内全部文本可以正确切换，无残留中文/英文混杂
  - [ ] 5.3 新增/调整的文案与当前黑白灰极简风格一致，不引入多余的颜色与边框

- [ ] 6. 行为验证与回归测试
  - [ ] 6.1 本地起后端 + 前端，模拟至少三类真实链路：
    - [ ] 6.1.1 只走 LLM、完全无工具调用的简单问答
    - [ ] 6.1.2 只使用 google_workspace（读 + 写）、无 plane 的场景（如查看邮件/创建 Docs）
    - [ ] 6.1.3 触发 plane（pinchtab/browser）和多个工具组合调用的复杂场景
  - [ ] 6.2 在上述三类场景中，ExecutionPane 都能正常展示，不会出现空白、布局错乱或报错
  - [ ] 6.3 切换主题（深色/浅色）、切换语言、调整窗口宽度（包含窄屏/小窗口）时，ExecutionPane 布局与滚动行为稳定
  - [ ] 6.4 确认新的 trace 展示逻辑不会导致已有 chat 体验退步：例如不影响消息流渲染、不影响输入框与底栏交互

