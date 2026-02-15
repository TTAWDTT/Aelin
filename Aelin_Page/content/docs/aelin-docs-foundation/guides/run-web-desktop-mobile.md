---
title: Run on Web / Desktop / Mobile
slug: /guides/run-multi-platform
description: Aelin 在 Web、桌面、移动端的运行方式与差异。
---

# Run on Web / Desktop / Mobile

## Web

- 前端 + 后端分离运行
- 适合开发和调试

## Desktop

- 桌面壳负责拉起前后端
- 目标是开箱即用

## Mobile

- 使用 Capacitor 容器
- 需要确保移动设备能访问后端地址

## 排障核心

- 登录 `failed to fetch`：通常是 API 地址不可达
- 安装失败：优先检查设备存储空间与 SDK 环境
- 编码乱码：检查终端编码与子进程输出编码设置
