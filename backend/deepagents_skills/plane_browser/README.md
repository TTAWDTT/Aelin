# Browser Plane Skill for DeepAgents

本技能描述如何通过 `plane` 工具委派浏览任务给浏览器 plane（如 pinchtab）。

## 能力概览

- 打开指定 URL，并在可见浏览器中进行交互。
- 读取页面内容，总结要点或提取结构化信息。
- 在需要验证码 / 登录时，通过用户在本地浏览器完成操作后继续任务。

## 使用约定

1. 使用 `plane` 工具并设置：
   - `plane = "browser"`
   - `action` 之一：
     - `delegate`：创建新的浏览任务。
     - `status`：查询任务状态。
     - `continue`：在任务仍在运行时继续执行。

2. 创建任务时应提供清晰的 `goal`，例如：
   - 「打开 https://www.baidu.com 并总结首页要闻」
   - 「登录某网站并检查账户余额」

3. 当 `status` 返回：
   - `state = "running"`：继续轮询或调用 `continue`。
   - `state = "waiting_user"`：说明需要用户在可见浏览器中完成登录/验证码等步骤，此时应提示用户操作，并等待用户回复「已登录，继续」再继续委派。
   - `state = "completed"`：可以从 `summary` 中获取结果，为用户生成最终回答。

4. 不要在没有必要时频繁创建新的浏览任务：
   - 如果已有同一 `task_id` 的活跃任务，应优先使用 `status` / `continue` 来续上。

