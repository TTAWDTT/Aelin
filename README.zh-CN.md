# Aelin（中文）

Aelin 是一个面向“长期协作”的 AI 助手系统，支持聊天、工具调用、记忆、追踪与桌面运行。

## 1. 项目定位
- 不是一次性问答机器人，而是可持续协作的个人 AI 系统。
- 以 Agent Loop 为核心，支持按策略调用工具完成任务。
- 支持 Web 与 Desktop 两种运行方式。

## 2. 核心能力
- 聊天与多模态输入：文本、图片输入，支持流式输出。
- 工具调用：`context_get`、`diary`、`profile`、`tracking`、`device`、`web_search`、`screen_get`、`browser_state_get`、`browser_use`。
- Computer Use 基础链路：手动截图输入 + 自主 `screen_get` 读屏；受控/外部浏览器导航与状态读取。
- 长期记忆与追踪：OpenViking 兼容文件记忆结构，支持目标追踪与变更记录。

## 3. 仓库结构
- `backend/`: FastAPI、SQLAlchemy、Agent 服务与调度。
- `backend/tests/`: Pytest 测试。
- `frontend/`: React 19 + Vite + TypeScript。
- `desktop/`: Electron 桌面壳与打包脚本。
- `docs/`: 架构、方案与测试文档。
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

# Desktop（可选）
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
- 常用环境变量：
  - `MERCURYDESK_SECRET_KEY`
  - `MERCURYDESK_FERNET_KEY`
  - `MERCURYDESK_DATABASE_URL`
  - `MERCURYDESK_CORS_ORIGINS`
  - `MERCURYDESK_AELIN_AGENT_LOOP_ENABLED`
  - `MERCURYDESK_AELIN_AGENT_LOOP_MAX_ROUNDS`
  - `MERCURYDESK_BROWSER_TOOL_CDP_ENABLED`
  - `MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT`
  - `MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE`
- 不要提交 API Key、OAuth Secret、数据库文件等敏感内容。

## 7. 贡献规范
- 建议采用 Conventional Commits：`feat(scope): ...`、`fix(scope): ...`、`docs: ...`。
- 提交 PR 前至少执行 `pytest -q`，并根据改动运行前端/桌面构建验证。
- 协作规范见 [AGENTS.md](AGENTS.md)。

## 8. 参考文档
- [README.en.md](README.en.md)
- [backend/README.md](backend/README.md)
- [docs/INDEX.md](docs/INDEX.md)
- [docs/agent_loop_manual_test_cases.md](docs/agent_loop_manual_test_cases.md)

