# Aelin（中文）

Aelin 现在是一个以 DeepAgents 为唯一 Agent 内核的 AI 工作台，提供聊天、工具调用、文件记忆、技能挂载与桌面运行能力。

## 1. 项目定位

- Aelin 是产品壳，DeepAgents 是唯一 agent loop。
- 运行时强调“真实工具结果优先”，避免壳层再发明一套语义状态机。
- 支持 Web 与 Desktop 两种运行方式。
- 后端 = 一层很薄的 HTTP 壳（`/api/v1/deepagents/chat/stream` + 兼容的 `/api/v1/aelin/*`）+ DeepAgents graph + 少量领域服务（web_search / attachments / device / Google Workspace / skills）；二次开发时建议优先参考 DeepAgents 官方文档与本仓库的 `docs/deepagents_arch.md`，在 DeepAgents 的 graph/skills 层扩展能力。

## 2. 核心能力

- 聊天与流式输出：支持常规多轮对话。
- DeepAgents 工具：`web_search`、`attachment_search`、`google_workspace`、`device`、`screen_get`。
- 文件化长期记忆：当前长期记忆统一来自 `/memory/AGENTS.md`。
- Skills：内置 skills 位于 `backend/deepagents_skills/`，也支持额外挂载目录。
- 桌面能力：通过 Electron 与本地 desktop plugin 提供截图、打开链接等能力。

## 3. 仓库结构

- `backend/`: FastAPI、DeepAgents glue、工具实现、测试。
- `frontend/`: React 19 + Vite + TypeScript。
- `desktop/`: Electron 桌面壳与打包脚本。
- `docs/`: 架构文档、说明文档、历史整理文档。
- `data/`: 本地运行数据与文件记忆目录。

## 4. 快速启动

```powershell
# Backend
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Frontend（新终端）
cd frontend
npm install
npm run dev

# Desktop
cd desktop
npm install
npm run dev
```

## 5. 常用开发命令

```powershell
# 后端测试
cd backend
pytest -q

# 前端构建
cd frontend
npm run build

# 桌面端打包
cd desktop
npm run dist
```

## 6. 配置与安全

- 推荐环境变量前缀：`AELIN_*`
- 兼容旧前缀：`MERCURYDESK_*`
- 常用配置项：
  - `AELIN_SECRET_KEY`
  - `AELIN_FERNET_KEY`
  - `AELIN_DATABASE_URL`
  - `AELIN_CORS_ORIGINS`
  - `AELIN_LLM_REQUEST_TIMEOUT_SECONDS`
  - `AELIN_LLM_VERIFY_SSL`
  - `AELIN_DEEPAGENTS_EXTRA_SKILLS_DIR`
  - `AELIN_DESKTOP_PLUGIN_BASE_URL`
  - `AELIN_GOOGLE_WORKSPACE_CLI_BIN`

不要提交 API Key、OAuth Secret、数据库文件等敏感内容。

## 7. 贡献规范

- 建议采用 Conventional Commits：`feat(scope): ...`、`fix(scope): ...`、`docs: ...`。
- 提交 PR 前至少执行 `pytest -q`，并根据改动运行前端/桌面构建验证。
- 协作规范见 [AGENTS.md](AGENTS.md)。

## 8. 参考文档

- [README.en.md](README.en.md)
- [docs/INDEX.md](docs/INDEX.md)
- [docs/deepagents_arch.md](docs/deepagents_arch.md)
- [docs/deepagents_skills_guide.md](docs/deepagents_skills_guide.md)
- [docs/gws.md](docs/gws.md)
