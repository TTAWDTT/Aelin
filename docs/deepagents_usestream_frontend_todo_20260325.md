# DeepAgents useStream / LangGraph Frontend 化 TODO（2026-03-25）

> 目标：继续把 Aelin 从“自定义 SSE + 前端二次建模”推进到“更贴近官方 DeepAgents / LangGraph Frontend 运行时”的形态。
>
> 这一轮不追求一步到位接成完整官方平台，而是优先做对后续 `useStream` 迁移最有价值的收口。

---

## 1. 先清掉当前前端构建噪音

- [x] 1.1 修复 `SettingsPage` 同时动态/静态导入导致的 Vite chunk 提示
- [x] 1.2 保持设置页仍可在路由与侧边栏弹窗中正常打开

## 2. 前端运行态先改成更原生的 DeepAgents 形状

- [x] 2.1 不再只在消息里存扁平 `executionEvents`
- [x] 2.2 改为保留原始 `stream parts` / `runState`
- [x] 2.3 从 `runState.parts` 派生 `executionEvents`，而不是把派生结果当单一真相
- [x] 2.4 保留 `latestValues` / `final` 这类更贴近官方流模型的状态入口

## 3. Execution Pane 继续往官方运行态结构收

- [x] 3.1 让 Execution Pane 直接消费 `runState`，而不是只吃 `executionEvents[]`
- [x] 3.2 补出 `values.todos`、`values.messages`、`values` 快照的可视化入口
- [x] 3.3 为 `tasks` 事件增加更稳定的分组/状态展示，而不是纯平铺列表
- [x] 3.4 为后续 `subagents` 展示预留 UI 结构

## 4. 后端协议继续向 LangGraph Frontend 靠拢

- [x] 4.1 审查当前 `/api/v1/deepagents/chat/stream` 事件包结构
- [x] 4.2 确保 `messages / updates / tasks / values / final / error` 的 envelope 足够稳定、足够薄
- [x] 4.3 检查是否还存在只为 Aelin 前端定制的字段拼装
- [x] 4.4 评估是否需要补稳定的 run id / node id / task id 透出

## 5. 为官方 `useStream` 铺路

- [x] 5.1 对照官方 DeepAgents / LangGraph Front端文档，确认 `useStream` 直接接入所需最小契约
- [x] 5.2 评估当前 Aelin 后端是否能直接接官方 hook；如果不能，明确缺的协议层
- [x] 5.3 若短期不能直连官方 hook，则把当前自定义 hook 收成“极薄 useStream-compatible adapter”
- [ ] 5.4 若可以直连，则开始替换当前 `streamChat + useChatStream` 主链

## 6. 最终验证

- [x] 6.1 前端 `npm run build`
- [x] 6.2 一轮真实聊天测试：普通对话
- [x] 6.3 一轮真实工具测试：web search
- [x] 6.4 一轮真实附件测试：attachment grounding
- [x] 6.5 一轮真实外围测试：remote control

---

## 本轮完成标准

- [x] R1 前端运行态不再以 `executionEvents[]` 作为唯一真相
- [x] R2 Execution Pane 更贴近 `stream.values / tasks / subagents` 官方概念
- [x] R3 后端协议继续变薄，减少 Aelin 专属前端胶水
- [x] R4 为下一步真正接 `useStream` 做好结构准备

---

## 当前判断

- 当前后端已经收成稳定的 `type + run_id + seq + ts + ns + data` 薄 envelope，前端也已经以 `runState.parts` 作为运行时单一真相。
- 离官方 `useStream` 还差的核心不是前端面板，而是后端仍然是 FastAPI 自定义 SSE 入口，不是 LangGraph 官方前端直接对接的运行时端点。
- 因此下一轮最合适的动作是完成 `5.1 ~ 5.3`：把当前 `streamChat` 收成极薄 adapter，并明确列出和官方 hook 直连还差的协议层。

## 本轮实测记录

- 普通聊天：真实返回正常，能够稳定生成最终答复。
- web search：真实触发了 `web_search` 工具，但模型对“今天”与搜索结果日期的约束仍不够强，答案质量还有优化空间。
- attachment grounding：真实上传文本附件后，能够正确回答“项目代号 ORBIT，截止日期 2026-04-03”。
- remote control：`status` 与 `execute` 都能真实返回；当前桌面插件配置存在，但 `desktop_plugin_reachable=false`，说明能力链路正常、插件侧未连通。
