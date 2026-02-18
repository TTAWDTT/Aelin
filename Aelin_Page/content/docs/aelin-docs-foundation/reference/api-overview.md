---
title: API Overview
slug: /reference/api
description: Aelin 与 Agent 核心接口总览，帮助你快速定位能力边界与调用入口。
---

# API Overview

这一页不是完整 API 文档，而是接口地图。

它的目的，是让你先知道“能力分组在哪里”，再进入更细的实现或调试。

## Aelin 核心

- `POST /api/v1/aelin/chat`
- `POST /api/v1/aelin/chat/stream`
- `GET /api/v1/aelin/context`
- `GET /api/v1/aelin/proactive/poll`
- `GET /api/v1/aelin/tracking`
- `POST /api/v1/aelin/track/confirm`

这组接口覆盖了对话、上下文、主动提醒和跟踪确认等核心流程。

## 设备能力

- `GET /api/v1/aelin/device/processes`
- `POST /api/v1/aelin/device/processes/{pid}/action`
- `POST /api/v1/aelin/device/processes/optimize`
- `GET /api/v1/aelin/device/capabilities`
- `POST /api/v1/aelin/device/mode/apply`

这组接口围绕设备状态感知和可控动作，适合性能辅助与场景模式切换。

## Agent / Memory

- `GET /api/v1/agent/config`
- `PATCH /api/v1/agent/config`
- `GET /api/v1/agent/memory`
- `POST /api/v1/agent/memory/layout`
- `GET /api/v1/agent/daily-brief`
- `POST /api/v1/agent/search/advanced`

这组接口支撑配置管理、记忆读取与高级检索，是长期能力稳定运行的基础层。

## 使用建议

- 先从分组理解接口，再看单接口细节。
- 调试时按“输入参数 → 返回结构 → 状态码”三步记录。
- 对关键链路建立最小可复现请求，便于回归测试。

## 说明

后续版本会在这组总览基础上补充更细粒度示例（请求体、响应体、异常码和推荐重试策略）。
