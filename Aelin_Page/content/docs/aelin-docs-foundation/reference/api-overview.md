---
title: API Overview
slug: /reference/api
description: Aelin 与 Agent 核心接口一览。
---

# API Overview

## Aelin 核心

- `POST /api/v1/aelin/chat`
- `POST /api/v1/aelin/chat/stream`
- `GET /api/v1/aelin/context`
- `GET /api/v1/aelin/proactive/poll`
- `GET /api/v1/aelin/tracking`
- `POST /api/v1/aelin/track/confirm`

## 设备能力

- `GET /api/v1/aelin/device/processes`
- `POST /api/v1/aelin/device/processes/{pid}/action`
- `POST /api/v1/aelin/device/processes/optimize`
- `GET /api/v1/aelin/device/capabilities`
- `POST /api/v1/aelin/device/mode/apply`

## Agent / Memory

- `GET /api/v1/agent/config`
- `PATCH /api/v1/agent/config`
- `GET /api/v1/agent/memory`
- `POST /api/v1/agent/memory/layout`
- `GET /api/v1/agent/daily-brief`
- `POST /api/v1/agent/search/advanced`
