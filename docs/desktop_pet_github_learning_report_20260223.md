# GitHub 桌宠项目学习报告（第一阶段）

日期：2026-02-23  
作者：Codex

## 1. 任务目标

本轮调研目标：

1. 在 GitHub 找到与你项目形态相近的桌宠实现。
2. 重点学习“透明窗口 + 点击穿透 + 拖拽 + 状态切换”相关代码，而不是只看 README。
3. 输出对 Aelin 当前问题（卡片显隐闪烁/位移感）的直接可用结论。

## 2. 调研样本与许可

已在本地克隆并阅读（路径：`.tmp/github-pet-study/`）：

1. `SeakMengs/WindowPet`  
   仓库：https://github.com/SeakMengs/WindowPet  
   许可：MIT（`.tmp/github-pet-study/WindowPet/LICENSE.md`）
2. `liwenka1/bongo-cat-next`  
   仓库：https://github.com/liwenka1/bongo-cat-next  
   许可：MIT（`.tmp/github-pet-study/bongo-cat-next/LICENSE`）
3. `tonybaloney/vscode-pets`  
   仓库：https://github.com/tonybaloney/vscode-pets  
   许可：MIT（`.tmp/github-pet-study/vscode-pets/LICENSE`）
4. `ExtraNick/Chatty_desktop_pet`  
   仓库：https://github.com/ExtraNick/Chatty_desktop_pet  
   许可：MIT（`.tmp/github-pet-study/Chatty_desktop_pet/LICENSE`）
5. `Chuck-Ray/pet-therapy`  
   仓库：https://github.com/Chuck-Ray/pet-therapy  
   许可：MIT（`.tmp/github-pet-study/pet-therapy/LICENSE.md`）
6. `not-elm/desktop_homunculus`  
   仓库：https://github.com/not-elm/desktop_homunculus  
   许可：LGPL-3.0-only（`.tmp/github-pet-study/desktop_homunculus/Cargo.toml` 的 `license = "LGPL-3.0-only"`）

## 3. 与 Aelin 最相关的实现结论

### 3.1 防闪烁的核心原则：窗口几何稳定，内容层动画化

最关键观察：成熟实现普遍避免高频“窗口尺寸/位置切换”。

1. `desktop_homunculus` 采用“每屏透明常驻窗口 + render layer + hit test 切换”  
   代码：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_windows/src/lib.rs`  
   结论：窗口长期稳定，交互变化主要靠内部渲染与 hit-test。
2. `WindowPet` 里点击穿透在边界切换时带节流延迟（50ms），而不是每帧抖动切换  
   代码：`.tmp/github-pet-study/WindowPet/src/scenes/manager.ts` (`IGNORE_CURSOR_EVENTS_DELAY`)
3. `pet-therapy` 使用固定透明窗口循环更新实体视图，不做高频窗口尺寸跳变  
   代码：`.tmp/github-pet-study/pet-therapy/Packages/Rendering/Sources/Rendering/WorldWindow.swift`

对 Aelin 的直接意义：

- 卡片显隐阶段应是 DOM/Canvas 层的 `opacity/transform`，不是主窗口 bounds 的来回重算。
- 任何 `setBounds`/`setSize` 都应尽量减少到“模式切换最终落点一次提交”。

### 3.2 点击穿透不是开关问题，而是状态机问题

1. `WindowPet`：有显式的开/关穿透切换函数 + 延迟保护，避免频繁调用底层 API 导致抖动/崩溃  
   代码：`.tmp/github-pet-study/WindowPet/src/scenes/manager.ts`
2. `desktop_homunculus`：hit test 根据“是否命中模型”改变，且非 develop 模式下按事件触发，减少不必要更新  
   代码：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_hit_test/src/lib.rs`

对 Aelin 的直接意义：

- 需要单独的 `PointerOwnershipStateMachine`（Idle/Hover/Drag/Settling）。
- “hover 结束后收起卡片”必须经过防抖窗口（如 120~200ms）和 pointer active 校验，而不是立即折叠。

### 3.3 原生输入与渲染层输入要分离

1. `WindowPet`：窗口开启 ignore cursor events 后，前端拿不到完整鼠标，需要 native 侧补采样  
   代码：`.tmp/github-pet-study/WindowPet/src-tauri/src/app/cmd.rs`
2. `bongo-cat-next`：系统级输入由 Rust 监听再发事件给前端  
   代码：`.tmp/github-pet-study/bongo-cat-next/src-tauri/src/core/device.rs`

对 Aelin 的直接意义：

- 若你当前 hover/drag/auto-collapse 混用 renderer 事件，且窗口穿透状态在变，会出现“短瞬态闪烁 + 状态误判”。
- 应保留“稳定输入源”（至少 drag 期间）并禁止并发提交 layout。

## 4. 单仓库学习摘要（代码级）

### 4.1 WindowPet（最贴近你的当前 Electron/Tauri 桌宠问题）

关键点：

1. 启动即设置窗口 ignore cursor events（`.tmp/github-pet-study/WindowPet/src-tauri/src/main.rs`）。
2. 在前端维护穿透切换器，且有 50ms 防抖（`.tmp/github-pet-study/WindowPet/src/scenes/manager.ts`）。
3. 通过 native command 获取鼠标位置弥补穿透状态下的前端事件缺失（`.tmp/github-pet-study/WindowPet/src-tauri/src/app/cmd.rs`）。

可借鉴价值：高。

### 4.2 desktop_homunculus（架构最完整，但许可更严格）

关键点：

1. 多窗口透明层在启动时创建，窗口稳定且默认 click-through（`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_windows/src/lib.rs`）。
2. 3D hit-test 决定窗口是否可交互（`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_hit_test/src/lib.rs`）。
3. 有独立 HTTP API、MOD、WebView 扩展体系（`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_http_server/src/lib.rs`、`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_mod/src/lib.rs`）。

可借鉴价值：高（偏架构思想）。  
注意：LGPL-3.0-only，不建议直接搬实现代码到闭源核心。

### 4.3 pet-therapy（macOS 2D 桌宠，窗口模型简洁）

关键点：

1. 每屏 world + window，透明无边框，固定循环更新（`.tmp/github-pet-study/pet-therapy/Sources/OnScreen/Rendering/OnScreen.swift`、`.tmp/github-pet-study/pet-therapy/Packages/Rendering/Sources/Rendering/WorldWindow.swift`）。
2. 拖拽状态是 capability（`MouseDraggable`），行为切换集中（`.tmp/github-pet-study/pet-therapy/Sources/OnScreen/Interactions/MouseDraggable.swift`）。
3. 窗口障碍检测服务化（`.tmp/github-pet-study/pet-therapy/Sources/OnScreen/Interactions/DesktopObstaclesService.swift`）。

可借鉴价值：中高（交互拆分方式很好）。

### 4.4 bongo-cat-next（现代前端+Tauri）

关键点：

1. `useWindowEffects` 集中处理穿透/置顶/显隐（`.tmp/github-pet-study/bongo-cat-next/src/hooks/use-window-effects.ts`）。
2. `useWindowScaling` 内频繁 `setSize` 和延时重定位（`.tmp/github-pet-study/bongo-cat-next/src/hooks/use-window-scaling.ts`）。

结论：它展示了“setSize 频繁触发时容易产生视觉不稳定”的反例价值。

### 4.5 vscode-pets 与 Chatty_desktop_pet

1. `vscode-pets`：状态机设计成熟，适合借鉴行为层（`.tmp/github-pet-study/vscode-pets/src/panel/states.ts`、`.tmp/github-pet-study/vscode-pets/src/panel/basepettype.ts`）。
2. `Chatty_desktop_pet`：Godot 窗口参数与拖拽/投掷描述详细，README 和场景脚本可提供交互思路（`.tmp/github-pet-study/Chatty_desktop_pet/README.md`、`.tmp/github-pet-study/Chatty_desktop_pet/Main.tscn`）。

## 5. 给 Aelin 的直接落地建议（针对你当前闪烁）

按优先级：

1. P0：把“卡片显隐”彻底降级为渲染层动画，不触发窗口几何变化。
2. P0：穿透切换增加最小切换间隔（50~100ms）和状态机守卫，禁止 drag 中收起。
3. P0：合并 layout 提交通道，确保同一帧最多一次“最终几何提交”。
4. P1：建立 `hover/drag/settle/collapse` 时序日志统一格式，避免 renderer/main 两边时序漂移。
5. P1：引入 `expanded footprint`（窗口固定更大），compact 仅做内部层隐藏。

## 6. 复用与“可小幅借鉴”边界

1. MIT 项目可参考实现并小范围借鉴，但必须保留原许可声明与署名。
2. `desktop_homunculus` 为 LGPL-3.0-only，建议借鉴思路，不直接复制核心实现。
3. 优先复制“模式与接口设计”，少复制“具体业务代码”。

## 7. 结论

你当前看到的“显隐瞬间闪烁/位移感”，从同类项目经验看，本质不是动画参数问题，而是“窗口几何、穿透状态、输入源”三者耦合导致的瞬态竞争。  
要根治，必须让窗口层稳定，把变化压到内容层，并用状态机管理穿透与收起时序。

