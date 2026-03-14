# Aelin Skills

`backend/skills/*/SKILL.md` 是 Aelin 的本地 skill 目录。这里的 skill 不是“可执行工具”，而是会在特定 query 和工具集合命中时，被注入到 Agent Loop system prompt 里的**可复用使用规范**。

这些规范既可以指导：

- 如何正确使用某个原子工具
- 也可以指导如何把任务委派给某个 plane

## 目标

- 把第三方项目的官方能力边界、最佳实践、集成注意事项沉淀成稳定上下文
- 让 Aelin 在调用工具前，先获得针对该工具的“操作说明书”
- 让后续接入新项目时，遵循统一格式，而不是每次临时写 prompt

## 目录约定

每个 skill 一个文件夹：

```text
backend/skills/
  pinchtab/
    SKILL.md
  crawl4ai/
    SKILL.md
```

## Frontmatter 约定

当前 Aelin skill loader 支持一个轻量 frontmatter：

```md
---
name: PinchTab Browser Control
slug: pinchtab
version: 1.0.0
applies_to_tools: pinchtab,pinchtab_agent,pinchtab_session
trigger_keywords: 网页,浏览器,登录,网站
---
```

字段说明：

- `name`: 展示名，注入 prompt 时会保留
- `slug`: 稳定标识；未填写时默认使用文件夹名
- `version`: 可选，便于后续演进
- `applies_to_tools`: 该 skill 作用于哪些 Aelin tool
- `trigger_keywords`: 可选；若存在，query 需命中任一关键字才会注入

## 正文建议结构

推荐正文覆盖这几块：

1. `Purpose`
   这个项目在 Aelin 架构里的角色是什么
2. `Capabilities`
   它真正能做什么
3. `Core Concepts`
   它内部的重要对象或抽象
4. `Aelin Integration`
   Aelin 应该如何使用它，对应哪些 tool
5. `Usage Patterns`
   常见 query 下的推荐调用方式
6. `Limits & Gotchas`
   能力边界、失败模式、不要误用的地方

## 注入链路

当前链路如下：

1. `AelinToolHub.tool_definitions()` 产出当前可用 tool 名称
2. `app.services.skill_loader.get_skill_prompts_for_query_and_tools()` 根据 `query + tool_names` 选择 skill
3. `app.services.aelin_loop_message.build_initial_messages()` 把命中的 skill 注入为额外 `system` 消息
4. `AelinAgentLoop` 再基于这些消息决定如何调用工具

## 适用边界

- skill 适合承载“如何使用某个项目/工具”的知识
- skill 不替代真实 tool 实现
- skill 也不等于 MCP server

可以把它理解成：

- `tool` 决定“能不能做”
- `plane` 决定“能不能把整件事托管出去”
- `skill` 决定“该怎么做更对”

## 当前样例

- `pinchtab`: browser plane 的委派规范，负责复杂浏览器任务的交付与续办
- `crawl4ai`: 网页摄取层，负责抓取、markdown 化、结构化提取、深度爬取

这两个样例刻意分属不同能力面，方便后面继续扩展 Aelin 的 skill 生态。
