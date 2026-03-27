---
title: API Overview
slug: /reference/api
description: Aelin 当前实际可用的核心 API 一览。
---

# API Overview

## Chat / DeepAgents

- `GET /assistants`
- `POST /threads`
- `GET /threads/:thread_id`
- `POST /threads/:thread_id/runs/stream`

说明：

- 这是聊天 UI 的主入口。
- 前端通过 LangGraph SDK / `useStream` 直接消费官方 run stream。
- 旧 `POST /api/v1/deepagents/chat/stream`、`POST /api/v1/aelin/chat` 与 `POST /api/v1/aelin/chat/stream` 都不再是当前主链。

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
