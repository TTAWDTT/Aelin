---
title: Known Issues
slug: /reference/known-issues
description: 当前版本已知限制与规避建议。
---

# Known Issues

## 1. 外部网站抽取不稳定
部分站点会触发反爬或动态渲染限制，导致正文抽取质量波动。

## 2. 设备控制平台差异
设备模式控制在 Windows 上能力更完整，其他系统可能只更新状态。

## 3. 移动端网络配置敏感
安卓模拟器/真机必须配置可访问的后端地址，否则会出现 `failed to fetch`。

## 4. 桌面打包依赖环境
首次打包依赖较多，网络代理或证书策略可能影响依赖下载。
