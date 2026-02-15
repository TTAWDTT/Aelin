---
title: Configure LLM Provider
slug: /guides/configure-llm
description: 配置内置或自定义 LLM 提供商，让 Aelin 具备稳定对话能力。
---

# Configure LLM Provider

## 基本配置项

- Provider 名称（可自定义）
- Base URL
- Model
- API Key
- Temperature

## 建议流程

1. 在设置页填入提供商参数
2. 点击连通性测试
3. 测试通过后再进行正式对话

## 常见问题

- 只返回模板话术：通常是 API key / base URL 无效
- 响应慢：优先切换模型或降低温度
- 移动端失败：确认 `VITE_MOBILE_API_BASE_URL` 指向可访问后端
