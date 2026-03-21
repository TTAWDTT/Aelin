# DeepAgents Skills 接入指南

> 本文档说明在 Aelin 的 DeepAgents 版本中如何新增 / 维护 skills，使其既能被 DeepAgents 读取，又能通过 `skill` 工具暴露给模型参考。

## 1. 目录结构与入口

- DeepAgents 运行时的 **唯一技能入口目录** 为：
  - `backend/deepagents_skills/`
- 该目录下的每个子目录表示一个技能主题（slug），例如：
  - `backend/deepagents_skills/google_workspace/`
  - `backend/deepagents_skills/file_tools/`
- 子目录中所有 `.md` 文件会被挂载为虚拟文件，并在创建 DeepAgents agent 时通过：
  - `files[/<skill_slug>/<file>.md]` 暴露给模型；
  - `skills=["/<skill_slug>/"]` 作为 skill 源目录列表传给 DeepAgents。

> 旧的 `backend/skills/*/SKILL.md` 仍然存在，但仅作为 `skill` 工具的后端数据源，用于按需阅读 skill 正文，不再直接注入 Agent Loop 的 system prompt。

## 2. 新增一个 DeepAgents skill 的步骤

1. 在 `backend/deepagents_skills/` 下创建子目录（以 slug 命名）：
   - 例如：`backend/deepagents_skills/google_workspace/`
2. 在该目录中添加一个或多个 markdown 文件：
   - 推荐以 `README.md` 或功能清晰的文件名命名，例如：`usage.md`、`patterns.md`。
   - 内容建议包含：
     - 能力范围说明（该 skill 针对哪些工具或场景）
     - 推荐的调用模式与常见 pitfalls
     - 少量示例对话 / 工具调用片段（无需严格 JSON，可读即可）。
3. 不需要在 Python 代码中做任何注册：
   - `app/services/deepagents_graph.py` 会自动遍历 `deepagents_skills/` 下的子目录，
     - 将每个子目录挂载为一个 skill source（`skills=["/<slug>/", ...]`）。
     - 将该目录中的所有 `.md` 文件挂载为虚拟文件供 DeepAgents 读取。

## 3. 与工具的协同方式

- 当 skill 与某个具体工具紧密相关时（例如 gws）：
  - 建议在 skill 文档中明确写出：
    - 对应的工具名（如 `google_workspace`）。
    - 建议何时优先使用该工具、何时退回 `web_search` 或纯对话。
    - 关键参数的含义和边界（如 `max_results` / `fetch_top_k` / 写操作前必须先解释等）。
  - DeepAgents 会在阅读 skill 文本后，通过自身的规划逻辑决定是否、如何调用该工具，Aelin 不再在 Python 里硬编码“优先调用哪个工具”。

## 4. 与旧 skills 的关系（backend/skills）

- `backend/skills/*/SKILL.md` 仍然用于：
  - 通过 `skill` 工具（`tools_skill.py` + `skill_loader.py`）按 slug 列出 / 读取 skill 正文；
  - 提供更细粒度的「工具使用规范」或「场景指南」，供模型在需要时主动查阅。
- 这些旧 skills 不再自动注入 Agent Loop 的系统 prompt：
  - DeepAgents 只通过 `deepagents_skills/` + 文件挂载获取技能知识；
  - 你可以按需逐步将重要的 SKILL 内容迁移或复制到对应的 `deepagents_skills/<slug>/` 下。

## 5. 验证与调试

- 新增 / 修改 skill 后，建议：
  - 启动 backend，发起几条实际对话，观察 DeepAgents 是否在适当场景下引用了新的 skill 内容；
  - 使用 `skill` 工具读取对应 slug，确认旧 skill 系统仍能正常列出和返回正文（若仍在使用）。
- 如需彻底下线某类 skill（例如 plane/pinchtab 相关）：
  - 删除或归档对应的 `backend/skills/*` 子目录；
  - 同时清理 `deepagents_skills/` 下 plane 相关 skill（见 DeepAgents 终态清理 TODO 第 4 部分）。

