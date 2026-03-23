# DeepAgents Skills 接入指南

> 本文档说明在 Aelin 的 DeepAgents 版本中如何新增 / 维护 skills，**完全围绕 DeepAgents 官方 SkillsMiddleware 模型**，避免再手搓第二套 agent 级技能注入。

## 1. 目录结构与虚拟路径

- DeepAgents 运行时的技能根目录统一为：
  - 物理目录：`backend/deepagents_skills/`
  - 虚拟根路径：`/skills/aelin/`
- 该目录下的每个子目录表示一个技能主题（slug），例如：
  - `backend/deepagents_skills/google_workspace/` → `/skills/aelin/google-workspace/`
  - `backend/deepagents_skills/file_tools/` → `/skills/aelin/file-tools/`
- 子目录中所有 `.md` 文件会被挂载为虚拟文件，并在创建 DeepAgents agent 时通过：
  - `files["/skills/aelin/<slug>/<file>.md"]` 暴露给 DeepAgents 后端（StateBackend）。
  - `skills=["/skills/aelin/"]` 作为 skill 源目录列表传给 `create_deep_agent(...)`，由 `SkillsMiddleware` 自动发现子目录并解析其中的 `SKILL.md`。

> 注意：子目录名中的下划线会被规范化为连字符，例如 `google_workspace` → `google-workspace`，以满足 Agent Skills 规范对 `name` 的约束（仅允许小写字母、数字和 `-`）。

## 2. DeepAgents skill 的标准结构

1. 在 `backend/deepagents_skills/` 下创建子目录（以 slug 命名）：
   - 例如：`backend/deepagents_skills/google_workspace/`、`backend/deepagents_skills/file_tools/`。
2. 在该目录中添加一个 `SKILL.md` 文件（可额外保留 `README.md` 等人类文档）：
   - Frontmatter 至少包含：
     ```md
     ---
     name: google-workspace
     description: 使用 `google_workspace` 工具安全地访问和操作 Gmail、Drive、Calendar 与 Docs 等 Google Workspace 资源。
     license: MIT
     ---
     ```
   - 正文部分建议包含：
     - 能力范围说明（该 skill 针对哪些工具或场景）。
     - 推荐调用模式与注意事项（例如先调用 `auth_status`，再调用写操作）。
     - 少量示例对话 / 工具调用片段（可读即可，无需严格 JSON）。
3. 不需要在 Python 代码中做额外注册：
   - `backend/app/services/deepagents_graph.py` 会自动遍历 `deepagents_skills/` 下的子目录，
     - 将 `SKILL.md` 及其他 `.md` 文件挂载到 `/skills/aelin/<slug>/...`。
     - 将 `/skills/aelin/` 作为唯一 skills 根路径传入 `create_deep_agent(..., skills=["/skills/aelin/"], ...)`。
   - `SkillsMiddleware` 会在运行时列出所有子目录、下载 `SKILL.md`，并把技能元数据注入到 system prompt 的 skills 区块。

## 3. 与工具的协同方式

- 当 skill 与某个具体工具紧密相关时（例如 gws）：
  - 在 `SKILL.md` 中明确写出：
    - 对应的工具名（如 `google_workspace`）。
    - 建议何时优先使用该工具、何时退回 `web_search` 或纯对话。
    - 关键参数的含义和边界（如 `max_results` / `fetch_top_k` / 写操作前必须先调用 `auth_status` 等）。
  - DeepAgents 在读取 skill 文本后，会通过自身的规划逻辑决定是否、如何调用该工具，Aelin 不再通过 Python 代码层面对“优先使用哪个工具”做硬编码。

## 4. 与旧 skills 的关系（backend/skills）

- `backend/skills/*/SKILL.md` 及 `skill_loader.py` / `tools_skill.py` 目前只承担**遗留的 skill catalog 能力**：
  - 通过 `skill` 工具按 slug 列出 / 读取旧 skill 的正文。
  - 用于前端或非 DeepAgents 流程按需展示“技能说明书”。
- DeepAgents agent loop 本身只依赖 `/skills/aelin/` + `SkillsMiddleware` 获取技能知识，**不会再从旧 skill loader 注入任何 system prompt 内容**。
- 后续如果不再需要旧技能系统，可以逐步：
  - 将重要的 SKILL 内容迁移到 `backend/deepagents_skills/<slug>/SKILL.md`。
  - 下线 `backend/skills` 目录以及 `skill_loader` / `tools_skill` 的相关路由与 UI 按钮。

## 5. 验证与调试

- 新增 / 修改 DeepAgents skill 后，建议：
  - 启动 backend，发起几条实际对话，观察 system prompt 中的 skills 列表是否包含新技能（可通过日志或调试输出查看）。
  - 在对应该技能的典型场景下，确认 DeepAgents 会遵循 `SKILL.md` 中的约定（例如先检查 GWS 认证状态，再尝试写操作）。
- 如需彻底下线某类 skill（例如 plane/pinchtab 相关）：
  - 删除或归档对应的 `backend/deepagents_skills/*` 子目录。
  - 同时清理旧的 `backend/skills/*` 与任何显式依赖这些 skills 的代码。

