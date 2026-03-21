---
name: PinchTab Browser Plane
slug: pinchtab
version: 2.0.0
applies_to_tools: plane
trigger_keywords: 网页,浏览器,上网,链接,网站,X,Twitter,登录,关注列表,pinchtab
---

# Purpose

PinchTab 在 Aelin 里应被理解为 `browser plane`，不是普通原子工具。

它的职责是承接整类复杂浏览器任务：

- 打开网站并持续导航
- 维持登录后的网页会话
- 执行多步网页流程
- 在需要时滚动、翻页、继续加载
- 提取页面文本与阶段性结果

Aelin 不应该自己微操浏览器内部步骤，而应该把高层目标委派给 browser plane，再监督进度与验收结果。

---

# Positioning

请把 PinchTab 当作：

- 浏览器领域的完整执行子系统
- browser plane 的底层执行后端
- 适合接“整件活”的系统

而不是：

- 一个点击按钮工具
- 一个让 Aelin 自己逐步调用的浏览器 API 集合

---

# Aelin Integration

当前 Aelin 对 PinchTab 的正确入口是 `plane` 工具。

## 委派方式

1. `plane.action=delegate`
   - 当用户提出复杂浏览器目标时使用
   - `plane="browser"`
   - `goal` 写整件任务的高层目标

2. `plane.action=status`
   - 当需要查看当前 browser plane task 的最新状态时使用

3. `plane.action=continue`
   - 当已有 browser plane task，需要继续推进时使用
   - 优先复用同一个 `task_id`

4. `plane.action=close`
   - 当任务结束或明确放弃时关闭

## 关键原则

- 优先复用已有 `task_id`
- 不要重复 delegate 相同网页任务
- 不要自己拆成低层浏览器动作去微操
- 只把“下一步要达成的子目标”告诉 browser plane

---

# Usage Patterns

## 适合交给 browser plane 的任务

- “帮我总结我的 X 关注列表”
- “登录某网站后，找到订单页并整理近 30 天记录”
- “打开后台，多步导航到报表页，再提取关键数字”
- “继续刚才那个网页登录后的任务”

## 不适合交给 browser plane 的任务

- 纯搜索型问题
  - 这类优先 `web_search`
- 纯公开网页内容采集
  - 更适合 `Crawl4AI`
- 电脑状态、进程、截图
  - 更适合 `device` / `screen_get`

---

# User Coordination

如果 browser plane 返回需要用户配合，尤其是登录、验证码、2FA：

- Aelin 应该把阻塞点转达给用户
- 等用户回复“已登录，继续”之类确认后，再调用 `plane.action=continue`
- 不要在阻塞状态下盲目反复重试

---

# Limits & Gotchas

- PinchTab 不会绕过网站本身的登录限制、风控或验证码
- 遇到站点错误时，Aelin 应明确告诉用户是网站侧限制，不要假装任务已经完成
- 对于复杂网页任务，关键不是“多调用几次工具”，而是“保持同一个 plane task 持续推进”

---

# Output Expectations

当 browser plane 返回结果后，Aelin 应重点关注：

- `state`
- `summary`
- `last_url`
- `last_text`
- `requires_user_input`
- `user_prompt`

然后决定：

- 继续委派
- 请求用户配合
- 结束任务并整理最终回复
