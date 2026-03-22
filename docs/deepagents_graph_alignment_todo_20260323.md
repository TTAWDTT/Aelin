# DeepAgents Graph Alignment TODO

## 1. Skills 挂载标准化

- [x] 1.1 调整 `deepagents_graph.py` 的 skills 挂载逻辑，保留完整 skill 目录结构，而不是只挂载 `*.md`
- [x] 1.2 保留 skill 内部相对路径，确保 `scripts/`、`references/`、配置文件等辅助资源可被正常读取
- [x] 1.3 校验 `chrome-cdp` 等 skill 在虚拟文件系统中的路径是否与 `SKILL.md` 中的引用方式一致

## 2. Tool Wrapper 收敛

- [x] 2.1 合并 `_make_tool`、`_make_device_tool`、`_make_screen_get_tool` 为统一包装器
- [x] 2.2 为所有 DeepAgents 工具统一补齐异常保护，避免单个工具抛异常导致整条 run 失败
- [x] 2.3 统一工具调用的参数规整、policy 判定、耗时统计与 trace 记录逻辑

## 3. 调用索引语义修正

- [x] 3.1 移除当前伪造的 `round_index=1` 语义
- [x] 3.2 将 `round_calls` / `max_calls_per_round` 调整为真实且诚实的调用统计语义，或改为 `call_index` / 总调用限制模型
- [x] 3.3 同步检查前端 Execution Pane 与后端 trace 字段，避免继续展示伪轮次信息

## 4. DeepAgents 工具注册纯化

- [x] 4.1 在 `deepagents_graph.py` 中显式注册当前真正提供给 DeepAgents 的工具集合
- [x] 4.2 切断 `deepagents_graph.py` 对 `AelinToolHub.tool_definitions()` 的依赖
- [x] 4.3 确认 `web_search`、`attachment_search`、`google_workspace`、`device`、`screen_get` 的 schema 与说明均收敛到 DeepAgents 友好的最小必要形式

## 5. 旧式 Tool Schema 残留删除

- [x] 5.1 检查并删除 `AelinToolHub.tool_definitions()` 中仅为旧链路保留的 schema
- [x] 5.2 检查并删除 `AelinToolHub` 中不再被 DeepAgents 主链使用的 `execute()` 或其他旧式字符串分发逻辑
- [x] 5.3 删除 `aelin_tool_policy.py` 中对 `context_get`、`profile` 等已退出主链工具的残留分支

## 6. Prompt 与装配层瘦身

- [x] 6.1 缩短 `deepagents_graph.py` 中的 `system_prompt`，仅保留必要行为原则与关键契约
- [x] 6.2 精简过长的 tool description，把能放进 schema 的约束尽量下沉到 schema
- [x] 6.3 复审 `deepagents_graph.py` 与 `aelin_tools.py`，删除本轮重构后多余的辅助代码与注释

## 7. 验证与收尾

- [x] 7.1 为 skills 挂载、工具异常保护、调用索引语义补充或更新测试
- [x] 7.2 运行后端测试，确认 DeepAgents 主链未被破坏
- [x] 7.3 进行至少一轮真实链路验证，确认 skills、memory、tools 三条链都正常工作
- [x] 7.4 清理冗余后提交 commit
