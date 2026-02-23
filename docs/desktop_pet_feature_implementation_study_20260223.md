# 桌宠特色功能实现研究（第二阶段）

日期：2026-02-23  
作者：Codex

## 1. 研究范围

在第一阶段“项目级学习”基础上，本阶段聚焦“功能如何实现”：

1. 特色功能拆解。
2. 实现机制与关键代码入口。
3. 哪些可以迁移到 Aelin，迁移成本与风险。

研究样本（同第一阶段）：

1. WindowPet
2. desktop_homunculus
3. pet-therapy
4. bongo-cat-next
5. vscode-pets
6. Chatty_desktop_pet

## 2. 功能实现地图

## 2.1 功能 A：透明窗口与点击穿透

### 实现方式

1. 启动时设透明、置顶、无边框、默认穿透。
2. 仅在命中宠物可交互区域时关闭穿透。
3. 命中离开后恢复穿透，且带防抖/节流。

### 代码证据

1. WindowPet  
   `set_ignore_cursor_events(true)`：`.tmp/github-pet-study/WindowPet/src-tauri/src/main.rs`  
   防抖延迟常量：`.tmp/github-pet-study/WindowPet/src/scenes/manager.ts`
2. desktop_homunculus  
   窗口默认 `cursor_options.hit_test = false`：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_windows/src/lib.rs`  
   通过 ray cast 更新 hit-test：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_hit_test/src/lib.rs`
3. Chatty_desktop_pet  
   Godot 侧透明/穿透窗口设置与 passthrough 逻辑：`.tmp/github-pet-study/Chatty_desktop_pet/project.godot`、`.tmp/github-pet-study/Chatty_desktop_pet/Main.tscn`

### 对 Aelin 的迁移建议

1. 建立独立 `windowInteractionManager`，不要让业务组件直接调用穿透 API。
2. 穿透切换必须有最小切换间隔。
3. drag 状态期间冻结“自动收起”。

## 2.2 功能 B：拖拽、投掷、落地状态

### 实现方式

1. Pointer drag start 时切到 drag state，禁用常规移动。
2. drag move 只更新实体位置，不触发布局级重排。
3. drag end 进入 throw/tween，落地后回归随机状态机。

### 代码证据

1. WindowPet  
   drag/dragend + tween throw：`.tmp/github-pet-study/WindowPet/src/scenes/Pets.ts`
2. desktop_homunculus  
   `on_drag_start/on_drag_move/on_drag_end`，并与坐姿/窗口停靠联动：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_drag/src/lib.rs`
3. pet-therapy  
   `MouseDraggable` capability：`.tmp/github-pet-study/pet-therapy/Sources/OnScreen/Interactions/MouseDraggable.swift`
4. Chatty_desktop_pet  
   拖拽采样数组 + fling 状态 + falling：`.tmp/github-pet-study/Chatty_desktop_pet/Main.tscn`

### 对 Aelin 的迁移建议

1. drag 生命周期从 hover lifecycle 解耦。
2. drag 中屏蔽卡片显隐。
3. drag-end 过渡结束后再评估 hover/auto-collapse。

## 2.3 功能 C：障碍物/窗口停靠/桌面感知

### 实现方式

1. 定时采样用户窗口矩形。
2. 将窗口边界转成“可碰撞障碍”。
3. 宠物路径规划或碰撞系统读取障碍结果。

### 代码证据

1. pet-therapy  
   `WindowsDetector().started(pollInterval: 1)` + obstacle 几何更新：`.tmp/github-pet-study/pet-therapy/Sources/OnScreen/Interactions/DesktopObstaclesService.swift`
2. desktop_homunculus  
   drop 到 window 后生成坐姿状态：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_drag/src/lib.rs`

### 对 Aelin 的迁移建议

1. 先做“轻量障碍层”（仅主窗口顶边）再扩展完整窗口障碍。
2. 将障碍更新频率限制在低频（500ms~1s），避免 UI 抖动。

## 2.4 功能 D：行为状态机与动画系统

### 实现方式

1. 用状态枚举 + transition 规则，不直接在 UI 事件中写行为。
2. 每帧执行 `nextFrame`，返回 `stateContinue/stateComplete/stateCancel`。
3. 随机行为只在允许状态触发（防互相打断）。

### 代码证据

1. vscode-pets  
   `States`、`resolveState`、`FrameResult`：`.tmp/github-pet-study/vscode-pets/src/panel/states.ts`  
   基类状态推进 `nextFrame`：`.tmp/github-pet-study/vscode-pets/src/panel/basepettype.ts`
2. WindowPet  
   随机状态、爬墙、跳跃、边界切换：`.tmp/github-pet-study/WindowPet/src/scenes/Pets.ts`

### 对 Aelin 的迁移建议

1. 把“卡片显示状态”并入 pet UI 状态机，而不是临时布尔值。
2. 禁止多个异步来源同时改 UI 模式（例如 drag-end 与 hover-leave）。

## 2.5 功能 E：插件化、脚本扩展、外部控制 API

### 实现方式

1. 本地 mod 目录 + `mod.json` 描述。
2. 启动脚本与菜单挂载。
3. 对外提供 HTTP API 和事件流（SSE）。

### 代码证据

1. desktop_homunculus  
   Mod 插件入口：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_mod/src/lib.rs`  
   HTTP 路由总入口：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_http_server/src/lib.rs`  
   VRM 事件 SSE：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_http_server/src/route/vrm/events.rs`  
   WebView 动态打开：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_api/src/webview/open.rs`

### 对 Aelin 的迁移建议

1. 你后续若要做“外部脚本驱动桌宠”，优先设计统一事件总线与最小 API 集。
2. 先做 read-only API（状态查询）再做命令 API（动作触发），降低失控风险。

## 2.6 功能 F：性能与功耗控制

### 实现方式

1. 帧率上限可配置。
2. 资源加载阶段特殊状态管理。
3. 某些情况进入低功耗更新模式。

### 代码证据

1. desktop_homunculus  
   `FramepaceSettings` + `RequestUpdateFrameRate`：`.tmp/github-pet-study/desktop_homunculus/crates/homunculus_power_saver/src/lib.rs`

### 对 Aelin 的迁移建议

1. 给桌宠 overlay 添加 `max_fps` 配置，空闲时降帧。
2. 动画不卡顿优先于高帧率，先保稳定再保极限流畅。

## 3. 针对 Aelin 闪烁问题的“可直接迁移方案”

## 3.1 P0 方案（必须先做）

1. 固定窗口外框，卡片显隐只做内容层动画（opacity/transform）。
2. 主进程几何提交收敛为单通道单帧一次。
3. 穿透切换状态机化并设置冷却时间（50~100ms）。
4. drag 期间禁止 auto-collapse，drag 结束后延迟再评估。

## 3.2 P1 方案（稳定后做）

1. 增加统一时序日志：`state-intent`、`state-commit`、`layout-apply`、`panel-anim-start/end`。
2. 增加闪烁检测工具：记录 500ms 内 bounds 变化次数和位移累计。

## 3.3 P2 方案（功能增强）

1. 引入行为状态机，减少条件分支扩散。
2. 增加插件化动作脚本入口（先内部 API）。

## 4. 许可与“可小幅借鉴”结论

1. 可直接参考并小幅借鉴的候选优先级：MIT 项目  
   `WindowPet`、`bongo-cat-next`、`vscode-pets`、`pet-therapy`、`Chatty_desktop_pet`
2. `desktop_homunculus` 为 LGPL-3.0-only，建议借鉴架构与思路，不直接复制核心实现。
3. 无论借鉴多少，都建议在项目文档中加“来源与改写说明”。

## 5. 最终结论

你这类“卡片显隐瞬闪”问题，最有效的解法不是继续微调动画参数，而是先把架构切到：

1. 稳定窗口几何。
2. 状态机管理输入与穿透。
3. 内容层动画承担视觉变化。

这是这批成熟项目里最一致、也最能复现稳定性的共识。

