---
title: Storage and Memory
slug: /reference/storage
description: Aelin 的本地存储、数据库持久化与记忆分层。
---

# Storage and Memory

## 持久化层

- 数据库：用户、账号、消息、记忆、配置
- 本地存储：会话草稿、当前会话、界面桥接状态

## 记忆分层

- `facts`：相对稳定的事实
- `preferences`：用户偏好
- `in_progress`：进行中事项（如跟踪状态）

## Workspace 隔离

布局、记忆和主动提醒状态都携带 workspace，以减少主题污染。

## 重装影响

- 本地 localStorage 会随应用清理而丢失
- 数据库是否保留取决于你安装与数据目录策略
