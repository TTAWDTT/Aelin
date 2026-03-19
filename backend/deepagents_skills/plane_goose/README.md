# Goose Plane Skill for DeepAgents

本技能为后续接入 goose 类 plane 预留，介绍其基本使用模式。

## 能力概览

- 作为针对特定站点或 API 的浏览 / 交互 plane。
- 适合需要多步调用、复杂导航的长链路任务。

## 使用约定

1. 与 browser plane 一样，通过 `plane` 工具调用，区别在于：
   - `plane = "goose"`（或后续约定的具体名字）。
   - `action` 仍为 `delegate` / `status` / `continue`。

2. 在构造 `goal` 时，应尽量清晰：
   - 具体说明要访问的资源、需要获取的信息或需要完成的操作。

3. 避免在 goose plane 中重复执行大语言模型可以直接完成的纯文本推理任务：
   - goose plane 更适合需要真实网络交互、复杂状态管理的任务。

