---
title: API Overview
slug: /reference/api
description: Aelin 当前实际可用的核心 API 一览。
---

# API Overview

## Chat / DeepAgents

- `POST /api/v1/deepagents/chat/stream`

说明：

- 这是聊天 UI 的主入口。
- SSE 主事件为 `start / messages / updates / tasks / values / final / error / done / ping`。
- 旧 `POST /api/v1/aelin/chat` 与 `POST /api/v1/aelin/chat/stream` 不再是当前主链。

## Aelin Product APIs

- `GET /api/v1/aelin/context`
- `POST /api/v1/aelin/attachments/upload`
- `GET /api/v1/aelin/memory/file-memory/content`
- `GET /api/v1/aelin/device/capabilities`
- `POST /api/v1/aelin/device/screen/capture`
- `GET /api/v1/aelin/remote-control/status`
- `POST /api/v1/aelin/remote-control/execute`

## Agent Config

- `GET /api/v1/agent/catalog`
- `GET /api/v1/agent/config`
- `PATCH /api/v1/agent/config`
- `POST /api/v1/agent/test`

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
