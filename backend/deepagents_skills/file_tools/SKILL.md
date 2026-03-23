---
name: file-tools
description: 使用 Aelin 的附件检索与文件类工具，围绕用户上传内容进行上下文感知回答。
license: MIT
---

# File Tools Skill for DeepAgents

本技能用于说明如何通过 Aelin 的文件类工具处理本地或附件内容。

## 能力概览

- 通过 `attachment_search` 等工具检索用户上传的文件内容。
- 在后续版本中，通过统一的 file 工具读取或写入本地文件。

## 使用约定

1. 使用 `attachment_search` 工具可以：
   - 按 `query` 在附件中检索相关片段。
   - 通过 `top_k` 控制返回条数。
   - 通过 `mode`（如 `hybrid`）使用多种检索策略。

2. 推荐工作流：
   - 当用户问题与附件明显相关（如「总结这个 PDF」），优先调用 `attachment_search` 获取摘要或重点段落。
   - 将检索到的内容与用户问题一起作为上下文回答，而不是直接要求模型「凭空回答」。

3. 如果检索失败或没有结果：
   - 向用户说明未在附件中找到相关内容。
   - 视情况直接回答或让用户提供更具体的问题或附件。

