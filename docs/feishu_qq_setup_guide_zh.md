# Aelin 飞书与 QQ 配置教程

本文面向第一次接入 Aelin 移动消息通道的同事，目标是让你在不了解底层代码的情况下，也能把飞书和 QQ 两条通道配置起来，并完成最基本的联调。

当前这两条通道的定位是一样的：

- 你在手机端发消息
- Aelin 后端收到消息并处理
- Aelin 把结果再发回原来的聊天窗口

两者的区别只在“消息入口”不同：

- 飞书：通过飞书机器人和长连接接入
- QQ：通过 NapCatQQ + OneBot WebSocket 接入

## 1. 使用前先理解的事

### 1.1 这两条通道各自负责什么

飞书和 QQ 都只是“消息入口”，不是业务逻辑本身。

真正处理消息的是本地运行的 Aelin 后端。也就是说：

- 机器人显示在飞书或 QQ 里
- 回复内容来自 Aelin
- 如果涉及本地电脑动作，例如截图、打开网址、唤起 Aelin 窗口，还需要桌面端插件在线

### 1.2 哪些功能不需要桌面端

以下能力通常只需要后端在线：

- 普通问答
- 让 Aelin 总结、解释、规划
- 设备状态查询

### 1.3 哪些功能需要桌面端

以下能力依赖 Electron 桌面插件在线：

- 截图
- 打开网址
- 打开 Aelin 窗口

如果桌面插件没启动，这类能力会失败或提示不可用。

## 2. 通用准备工作

无论你接飞书还是 QQ，都建议先准备好下面这些东西。

### 2.1 代码和依赖

后端安装依赖：

```powershell
cd backend
python -m pip install -r requirements.txt
```

如果后面要测桌面能力，再安装桌面端依赖：

```powershell
cd desktop
npm install
```

### 2.2 后端启动方式

只验证消息通道时，后端单独启动即可：

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果还要测截图、打开网址、打开 Aelin 等桌面能力，建议启动桌面端：

```powershell
cd desktop
npm run dev
```

### 2.3 本地环境变量文件

推荐把本地配置写在：

- `backend/.env`

不要把真实密钥、真实 token 提交到 Git。

## 3. 飞书配置教程

## 3.1 飞书适合什么场景

飞书更适合内部协作场景：

- 企业内测试
- 团队成员快速联调
- 需要相对标准、稳定的机器人接入方式

## 3.2 飞书开放平台侧要做什么

### 第一步：创建自建应用

去飞书开放平台创建一个企业自建应用，然后：

1. 填应用名称、描述、图标
2. 开启“机器人”能力
3. 记录 `App ID`
4. 记录 `App Secret`

### 第二步：开启长连接

进入应用后台的“事件与回调”页面：

1. 选择“长连接”
2. 注意：飞书要求先检测到你的本地程序已经成功建立长连接，才能保存这个配置
3. 所以这一步前，Aelin 后端通常需要已经启动

当前 Aelin 的飞书接入使用的是“长连接”，不是公网 Webhook。

### 第三步：添加消息事件

添加以下事件：

- `im.message.receive_v1`

这表示机器人收到消息时，飞书会把事件发给 Aelin。

### 第四步：开权限

最少要开这两个：

- `im:message:p2p_msg:readonly`
  作用：读取用户发给机器人的单聊消息
- `im:message:send_as_bot`
  作用：让机器人把消息回复回去

如果后面要支持群聊，再额外打开群聊相关的消息读取权限。

### 第五步：发布应用

配置好事件和权限之后，还要：

1. 创建版本
2. 发布到企业内部

如果不发布，经常会出现“后台看起来都配好了，但机器人实际不生效”的情况。

### 第六步：把机器人加到聊天里

推荐先做私聊测试：

1. 搜索机器人
2. 打开私聊窗口
3. 发一条简单消息，例如 `你好`

群聊建议后面再测。

## 3.3 飞书在 Aelin 后端里的配置

把下面这些写到 `backend/.env`：

```dotenv
MERCURYDESK_FEISHU_BOT_ENABLED=true
MERCURYDESK_FEISHU_APP_ID=你的AppID
MERCURYDESK_FEISHU_APP_SECRET=你的AppSecret
MERCURYDESK_FEISHU_BOT_WORKSPACE=default
MERCURYDESK_FEISHU_BOT_COMMAND_PREFIX=/aelin
MERCURYDESK_FEISHU_BOT_GROUP_REQUIRE_PREFIX=true
MERCURYDESK_FEISHU_BOT_ALLOWED_OPEN_IDS_CSV=
MERCURYDESK_FEISHU_BOT_ALLOWED_CHAT_IDS_CSV=
MERCURYDESK_FEISHU_BOT_BIND_USER_EMAIL=
```

### 这些字段怎么理解

- `MERCURYDESK_FEISHU_BOT_ENABLED`
  是否启用飞书通道
- `MERCURYDESK_FEISHU_APP_ID`
  飞书应用的 App ID
- `MERCURYDESK_FEISHU_APP_SECRET`
  飞书应用的 App Secret
- `MERCURYDESK_FEISHU_BOT_WORKSPACE`
  默认工作空间，通常先用 `default`
- `MERCURYDESK_FEISHU_BOT_COMMAND_PREFIX`
  群聊命令前缀，默认 `/aelin`
- `MERCURYDESK_FEISHU_BOT_GROUP_REQUIRE_PREFIX`
  群聊里是否必须带前缀，默认 `true`
- `MERCURYDESK_FEISHU_BOT_ALLOWED_OPEN_IDS_CSV`
  飞书用户白名单，可选
- `MERCURYDESK_FEISHU_BOT_ALLOWED_CHAT_IDS_CSV`
  飞书会话白名单，可选
- `MERCURYDESK_FEISHU_BOT_BIND_USER_EMAIL`
  把机器人消息绑定到某个本地 Aelin 用户，可选

## 3.4 飞书测试顺序

推荐按这个顺序测：

### 第一步：测消息通道

私聊机器人发送：

```text
你好
```

预期结果：

- 机器人有回复
- 回复显示在同一个飞书聊天窗口里

### 第二步：测状态查询

发送：

```text
状态
```

预期结果：

- 能看到当前设备状态
- 如果桌面插件已启动，应显示插件在线

### 第三步：测桌面能力

在桌面端已启动时，再尝试：

```text
截图
打开网址 https://example.com
打开 Aelin
```

## 3.5 飞书常见问题

### 问题 1：长连接保存不了

常见原因：

- 后端没启动
- `App ID` 或 `App Secret` 配错
- `lark-oapi` 没安装
- 飞书后台还没检测到活跃长连接

### 问题 2：机器人不回消息

常见原因：

- 应用没发布
- 没加 `im.message.receive_v1`
- 没开 `im:message:send_as_bot`
- 没把机器人加进聊天

### 问题 3：状态里显示桌面插件不可用

先检查：

- 桌面端是否已经启动
- `desktop` 进程是否在线
- 本机 `127.0.0.1:21914` 是否能访问

如果你开着 VPN，旧版本里可能会把本地插件误判成离线；当前分支已经修复了这个问题，本地插件请求会绕过环境代理。

## 4. QQ 配置教程

## 4.1 QQ 方案当前怎么实现

当前 QQ 接入不是官方普通 QQ 机器人开放平台路线，而是：

- NapCatQQ
- OneBot WebSocket
- Aelin 作为 OneBot 客户端接入

这是一条适合 PoC 和内测的路径，优点是快，缺点是你要自己维护本地机器人号和 NapCat 运行状态。

## 4.2 QQ 侧准备什么

### 第一步：准备一个专门的 QQ 号

建议使用专门的测试号：

- 不要直接拿主号长期做机器人号
- 电脑上登录机器人 QQ 号
- 手机上用另一个 QQ 账号去私聊它

### 第二步：安装并运行 NapCatQQ

保证 NapCat WebUI 可以正常打开，例如：

- `http://127.0.0.1:6099/webui?...`

这说明 NapCat 本体已经启动。

### 第三步：登录机器人 QQ 号

先确认：

- QQ 已经登录
- NapCat 处于在线状态
- 你在手机上给这个机器人号发消息时，NapCat 能收到事件

## 4.3 NapCat 网络配置怎么填

进入 NapCat WebUI 的“网络配置”页面，新建：

- `Websocket服务器`

推荐配置如下：

- 名称：自定义，例如 `Aelin`
- 启用：开
- Host：`127.0.0.1`
- Port：`6700`
- 消息格式：`Array`
- 上报自身消息：关
- 强制推送事件：开
- Token：设置一个新的长随机串
- 心跳间隔：默认 `30000` 即可

为什么选 `Websocket服务器`：

- NapCat 当服务端
- Aelin 后端去连接它
- 这是当前最简单、最稳的方式

保存之后，确认：

- `127.0.0.1:6700` 已经监听
- 给机器人号发私聊消息时，NapCat 能看到事件

## 4.4 QQ 在 Aelin 后端里的配置

把下面这些写到 `backend/.env`：

```dotenv
MERCURYDESK_QQ_BOT_ENABLED=true
MERCURYDESK_QQ_BOT_WS_URL=ws://127.0.0.1:6700
MERCURYDESK_QQ_BOT_TOKEN=你在NapCat里设置的Token
MERCURYDESK_QQ_BOT_WORKSPACE=default
MERCURYDESK_QQ_BOT_BIND_USER_EMAIL=
MERCURYDESK_QQ_BOT_ALLOWED_USER_IDS_CSV=
MERCURYDESK_QQ_BOT_ALLOWED_GROUP_IDS_CSV=
MERCURYDESK_QQ_BOT_COMMAND_PREFIX=/aelin
MERCURYDESK_QQ_BOT_GROUP_REQUIRE_PREFIX=true
```

### 这些字段怎么理解

- `MERCURYDESK_QQ_BOT_ENABLED`
  是否启用 QQ 通道
- `MERCURYDESK_QQ_BOT_WS_URL`
  NapCat OneBot WebSocket 地址
- `MERCURYDESK_QQ_BOT_TOKEN`
  NapCat 的 OneBot token
- `MERCURYDESK_QQ_BOT_WORKSPACE`
  默认工作空间，通常先用 `default`
- `MERCURYDESK_QQ_BOT_BIND_USER_EMAIL`
  绑定到某个本地 Aelin 用户，可选
- `MERCURYDESK_QQ_BOT_ALLOWED_USER_IDS_CSV`
  QQ 用户白名单，可选
- `MERCURYDESK_QQ_BOT_ALLOWED_GROUP_IDS_CSV`
  QQ 群白名单，可选
- `MERCURYDESK_QQ_BOT_COMMAND_PREFIX`
  群聊前缀，默认 `/aelin`
- `MERCURYDESK_QQ_BOT_GROUP_REQUIRE_PREFIX`
  群聊是否必须带前缀，默认 `true`

## 4.5 QQ 测试顺序

推荐按这个顺序测：

### 第一步：测私聊

用另一个 QQ 号私聊机器人 QQ 号，发送：

```text
你好
```

预期结果：

- Aelin 的回复直接出现在这个 QQ 私聊窗口里

### 第二步：测设备状态

发送：

```text
状态
```

预期结果：

- 能返回当前设备状态
- 如果桌面插件在线，会看到插件可用

### 第三步：测群聊

如果要在群聊里测试，默认需要带前缀：

```text
/aelin 你好
```

如果不带前缀，当前实现默认不会处理。

## 4.6 QQ 常见问题

### 问题 1：NapCat 收到消息了，但 QQ 没有回复

检查：

- Aelin 后端是否已启动
- `MERCURYDESK_QQ_BOT_ENABLED=true`
- `MERCURYDESK_QQ_BOT_WS_URL` 是否写对
- `MERCURYDESK_QQ_BOT_TOKEN` 是否和 NapCat 配置一致

### 问题 2：Aelin 后端没连上 NapCat

检查：

- NapCat 的 `6700` 端口是否监听
- 是否确实配置成了 `Websocket服务器`
- Host 是否写成 `127.0.0.1`

### 问题 3：群里发消息没反应

当前默认群聊要带前缀：

```text
/aelin 你好
```

如果你就是想让群聊里不带前缀也触发，可以把：

- `MERCURYDESK_QQ_BOT_GROUP_REQUIRE_PREFIX=false`

但不建议一开始就这么配，容易误触。

## 5. 桌面能力如何启动

如果你只想测试“聊天回复”，后端在线就够了。

如果你想测试：

- 截图
- 打开网址
- 打开 Aelin

还需要启动桌面端：

```powershell
cd desktop
npm install
npm run dev
```

桌面端起来后，本地插件会监听默认端口：

- `http://127.0.0.1:21914`

## 6. 推荐测试顺序

如果你是第一次接入，建议按下面顺序来，不要一开始就测复杂能力。

### 第一步：只起后端

先验证飞书或 QQ 的纯聊天回复。

### 第二步：测 `你好`

这一步只确认消息通道通不通。

### 第三步：测 `状态`

这一步确认 Aelin 能不能拿到本地设备状态。

### 第四步：再起桌面端

然后再测截图、打开网址、打开 Aelin。

## 7. 安全建议

### 7.1 不要提交真实密钥

不要把这些信息提交到仓库：

- 飞书 `App Secret`
- NapCat OneBot `Token`
- 本地 `.env`

### 7.2 如果密钥或 token 发到聊天截图里

一旦发出来，就当作已经泄露：

- 飞书 `App Secret` 立即轮换
- NapCat OneBot `Token` 立即重置

### 7.3 建议开启白名单

如果准备给别人用，建议至少配置一层白名单：

- 飞书：`MERCURYDESK_FEISHU_BOT_ALLOWED_OPEN_IDS_CSV`
- QQ：`MERCURYDESK_QQ_BOT_ALLOWED_USER_IDS_CSV`

### 7.4 QQ 建议用测试号

NapCat 路线适合内测和验证，不建议直接拿主账号长期跑机器人。

## 8. 一份最小可用配置示例

如果你要同时启用飞书和 QQ，可以参考下面这份最小本地配置。

```dotenv
MERCURYDESK_FEISHU_BOT_ENABLED=true
MERCURYDESK_FEISHU_APP_ID=你的飞书AppID
MERCURYDESK_FEISHU_APP_SECRET=你的飞书Secret
MERCURYDESK_FEISHU_BOT_WORKSPACE=default
MERCURYDESK_FEISHU_BOT_COMMAND_PREFIX=/aelin
MERCURYDESK_FEISHU_BOT_GROUP_REQUIRE_PREFIX=true

MERCURYDESK_QQ_BOT_ENABLED=true
MERCURYDESK_QQ_BOT_WS_URL=ws://127.0.0.1:6700
MERCURYDESK_QQ_BOT_TOKEN=你的NapCatToken
MERCURYDESK_QQ_BOT_WORKSPACE=default
MERCURYDESK_QQ_BOT_COMMAND_PREFIX=/aelin
MERCURYDESK_QQ_BOT_GROUP_REQUIRE_PREFIX=true
```

## 9. 建议阅读顺序

如果你是第一次接入，建议按这个顺序读：

1. 先看本文的第 1、2 节，理解整体结构
2. 只选一个通道，先配飞书或先配 QQ
3. 先通“聊天回复”
4. 最后再补桌面能力联调

如果你只想配飞书，也可以继续看：

- `docs/feishu_remote_control_v1.md`
