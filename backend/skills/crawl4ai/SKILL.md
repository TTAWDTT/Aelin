---
name: Crawl4AI Web Ingestion
slug: crawl4ai
version: 1.0.0
applies_to_tools: crawl4ai_fetch,crawl4ai_extract,crawl4ai_deep_crawl
trigger_keywords: 抓取,采集,爬取,网页内容,文档站,知识库,markdown,结构化提取,深度爬取,crawl4ai
---

# Purpose

Crawl4AI 是一个面向 LLM 的网页采集与内容提取引擎，用来把网页内容转换成**更适合模型消费的结构化文本**：

- 抓取公开网页和文档站
- 将页面转换为 markdown / fit markdown
- 从页面中提取结构化字段、表格和链接
- 对站点进行深度爬取，为后续总结、问答和知识摄取提供素材

在 Aelin 里，它应该被当作**网页采集 / 内容抽取层**，而不是浏览器交互层。

---

# Capabilities

- **单页抓取**
  - 获取网页正文、标题、链接、媒体资源等
- **Markdown 转换**
  - 将网页内容转成 markdown，便于 LLM 阅读与总结
  - 支持更精简、对 LLM 更友好的 `fit markdown`
- **结构化提取**
  - 提取标题、时间、作者、价格、字段列表等结构化信息
  - 适合对页面做 schema 化抽取
- **深度爬取**
  - 从根 URL 出发，按深度或规则批量采集站点内容
- **动态网页抓取**
  - 底层可配合浏览器加载动态页面，再对内容做提取

> Crawl4AI 的主价值是“把网页吃下来并整理好”，不是“像人一样逐步点网页”。

---

# Core Concepts

- **Fetch**
  - 抓取一个 URL 的主要内容，并返回 markdown / metadata / links。
- **Extract**
  - 在已有网页内容之上做结构化字段抽取。
- **Deep Crawl**
  - 从一个入口页面开始，递归获取更多相关页面。
- **Markdown / Fit Markdown**
  - Markdown 是页面的文本化表示；
  - Fit Markdown 是为 LLM 压缩过、去掉噪音后的版本，更适合总结与问答。

在 Aelin 里，Crawl4AI 的输出应被视为“知识素材”，而不是“浏览器状态”。

---

# Aelin Integration

在 Aelin 中，推荐把 Crawl4AI 暴露为三类工具：

1. `crawl4ai_fetch`
   - 适合：
     - “抓这个网页并总结”
     - “把这个文档页面转成 markdown”
     - “读取这个博客文章的正文”
   - 目标是拿到**页面内容本身**。

2. `crawl4ai_extract`
   - 适合：
     - “从这个页面提取价格、标题、作者、发布时间”
     - “把这个产品列表提取成结构化字段”
   - 目标是拿到**结构化结果**，不是整页阅读。

3. `crawl4ai_deep_crawl`
   - 适合：
     - “把这个文档站相关章节抓下来整理”
     - “把这个知识库最近内容抓取后总结”
   - 目标是做**多页面采集**。

**推荐使用边界：**

- 如果用户目标是“获取网页内容、整理网页知识、批量摄取站点内容”，优先考虑 Crawl4AI。
- 如果用户目标是“操作网页流程、点击按钮、输入内容、登录网站、继续刚才浏览器任务”，优先考虑 PinchTab，而不是 Crawl4AI。

---

# Usage Patterns

1. **单页知识提取**

- query 示例：
  - “帮我抓取这个文档页面并总结核心要点”
  - “把这个网页转成 markdown 再给我 5 点摘要”
- 推荐：
  - 优先 `crawl4ai_fetch`
  - 先拿正文，再让 LLM 总结

2. **批量摄取文档站 / 博客 / 帮助中心**

- query 示例：
  - “把这个文档站关于认证的内容抓下来整理”
  - “抓取这个博客栏目最近 20 篇文章并总结主题”
- 推荐：
  - 先 `crawl4ai_deep_crawl`
  - 再对结果做聚合总结

3. **从页面中提取结构化字段**

- query 示例：
  - “提取这个商品页的价格、品牌、评分”
  - “把这个列表页的标题和链接整理出来”
- 推荐：
  - 使用 `crawl4ai_extract`

4. **与 PinchTab 协作**

- 如果一个任务先需要**浏览器交互**，后需要**内容摄取**：
  - 先用 PinchTab 完成点击 / 导航 / 登录；
  - 当已经到达稳定内容页后，再交给 Crawl4AI 读取和提取页面内容。
- 不要让 Crawl4AI 负责“持续点网页直到完成任务”。

---

# Limits & Gotchas

- Crawl4AI 不是细粒度浏览器代理：
  - 不适合作为登录流程、验证码流程、强交互流程的主工具
  - 不应替代 PinchTab 的 `session start -> step -> status -> close` 模式
- 对于需要用户手动协作的任务：
  - 仍然应该回到 PinchTab headed 模式，让用户在真实浏览器窗口里配合
- 对于纯公共网页、文档站、博客、帮助中心：
  - Crawl4AI 通常比 PinchTab 更适合，因为它的输出天然更偏 markdown / extraction，适合后续 LLM 处理
- 若未来通过 MCP 或独立服务方式接入：
  - Aelin 仍然可以复用这份 skill，不需要重写能力边界说明

