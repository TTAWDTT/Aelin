## DeepAgents Skills Alignment TODO (2026-03-22)

> 目标：让 Aelin 的 skill 体系完全对齐 DeepAgents 官方模型（SkillsMiddleware + Backend + `/skills/**/SKILL.md`），不再手搓额外一层；做到“纯 DeepAgents 壳”。

### 1. 统一 skill 存储结构（Backend 视角）

- [x] 1.1 明确 DeepAgents backend 下的标准 skill 根路径
  - 约定一个或多个 POSIX 路径，比如：
    - `/skills/aelin/`（项目内技能）
    - `/skills/user/`（用户级技能，可选）
  - 在 docs 中写清楚这些路径将如何映射到实际文件系统目录。

- [x] 1.2 在 DeepAgents backend 初始化处挂载这些 skill 目录
  - 对 `StateBackend`：在 `agent.invoke(files={...})` 的构造里，把 `backend` 上看到的 `/skills/**/SKILL.md` 路径填充进去。
  - 对 `FilesystemBackend`（若使用）：保证 `root_dir` 下存在 `skills/aelin/**/SKILL.md` 等目录结构。

### 2. 让 chat agent 显式使用 DeepAgents skills 参数

- [x] 2.1 在 `deepagents_graph.build_chat_agent` / `create_deep_agent` 调用处，传入 `skills=[...]`
  - 使用第 1 步约定好的 skill root 列表，例如：
    - `skills=["/skills/aelin/"]`（起步版本，只挂一层）
  - 确认主 agent 和 general-purpose subagent 都能拿到同一套 `SkillsMiddleware`。

- [x] 2.2 为 skill backend 提供统一入口
  - 在 `deepagents_loop.py` 或专门的 helper 中集中构建 `backend: BackendProtocol | BackendFactory`，避免在多处手动注入 skill files。
  - 确保后续如果要挂 user/project 级 skills，只需改这一处配置。

### 3. 收敛/删除 Aelin 自己手搓的 “skill tool” 逻辑

- [x] 3.1 审查 backend 中现有的 skill 相关工具与路由
  - 在 `backend/app/services` 和 `backend/app/routers` 下搜索 `skill`, `skills`，列出：
    - 自定义的 `skill` 工具（如果仍存在）
    - 任何直接读取 `SKILL.md` 并拼接到 prompt 的逻辑。

- [x] 3.2 删除/改写这些自定义 skill 代码，改为完全依赖 DeepAgents SkillsMiddleware
  - 保留的唯一入口是：用户通过 DeepAgents 暴露的文件工具（`ls`, `read_file` 等）去读取 `SKILL.md`。
  - 如果前端有“skill 列表”展示需求，可以从 server 端调用 DeepAgents backend 的 `list_dir` / `download_files` 来读取技能元信息，而不是在 agent prompt 中重复一份逻辑。

- [ ] 3.3 更新/添加测试，确认不再依赖旧的 skill tool
  - 增加一个集成测试用例：
    - 准备一个简单的 `/skills/aelin/demo-skill/SKILL.md`（可以只在 `StateBackend` files 中虚拟提供）。
    - 启动 deepagents chat agent，并检查：
      - system prompt 中出现 demo-skill 的名称与描述。
      - agent 可以用 `ls` + `read_file` 访问该 SKILL.md 路径。

### 4. 为外部技能（如 chrome-cdp-skill）预留/落地接入方式

- [x] 4.1 设计 chrome-cdp-skill 的 DeepAgents 接入方案（文档级）
  - 在 docs 中描述：
    - 如何把一个 GitHub skills 仓库（如 `chrome-cdp-skill`）放到 Aelin 的 `/skills/aelin/` 下面。
    - 如何在 `SKILL.md` frontmatter 的 `allowed_tools` 中声明需要的 DeepAgents 工具（例如自定义的 `browser_cdp` tool）。

- [x] 4.2 若需要，增加一个最小样例 skill 目录到仓库中（可选）
  - 示例：`backend/deepagents_skills/google_workspace/`、`backend/deepagents_skills/file_tools/` → 在启动时由 backend 映射为 `/skills/aelin/google-workspace/` 等。
  - 用于测试 DeepAgents SkillsMiddleware 的加载流程，帮助后续用户添加技能时对照。

### 5. 清理与文档同步

- [x] 5.1 清理与 skill 有关的旧文档/注释
  - 在 `docs/` 中搜索 `skill` / `skills`：
    - 标记或归档已经与 plane/pinchtab 或旧 agent loop 相关的说明。
    - 把仍然有效的部分整合到一个新的 “DeepAgents Skills Guide” 中。

- [x] 5.2 更新 `deepagents_skills_guide.md` 与架构文档
  - 明确写出：
    - Aelin 现在只使用 DeepAgents SkillsMiddleware。
    - 标准技能目录结构和文件命名规范。
    - 如何本地添加/移除/调试技能。

- [x] 5.3 在完成所有步骤后，运行完整后端测试 & 一次真实链路验证
  - `cd backend && pytest -q`
  - 启动 Aelin，发起一个请求：“列出所有可用技能并告诉我各自的作用；然后选择一个最适合当前任务的技能，按其中步骤执行第一步”。
  - 确认：
    - SSE 返回中包含 `agent_loop: completed`。
    - system prompt 中有技能列表。
    - 没有再出现旧 skill tool/plane/pinchtab 相关的调用痕迹。
