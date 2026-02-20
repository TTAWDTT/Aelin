

## 1.测试结果

| 测试内容 | 设置页是否接通（是/否） | 接通后前端是否呈现对应内容（是/否） | 备注 |
| -------- | ----------------------- | ----------------------------------- | ---- |
| 转发接入 | 否                      |                                     |      |
| IMAP     | 否                      |                                     |      |
| bilibili | 否                      |                                     |      |
| DS       | 是                      |                                     |      |
| QWEN     | 是                      |                                     |      |
| OPENAI   | 否                      |                                     |      |
| CLAUDE   | 否                      |                                     |      |
| RSS/BLOG | 是                      | 否                                  |      |

## 2.issues

1、设置界面邮箱转发接入输入邮箱后，显示“请输入有效的邮箱地址"

2、设置界面邮箱IMAP输入邮箱和授权码后点击连接与同步，显示“邮箱已连接，首次同步失败（IMAP sync failed: command: LOGOUT => socket error: EOF）。可稍后手动点“同步”重试。”，然后点击上方邮箱右侧刷新按钮，出现“IMAP sync failed: command: LOGOUT => socket error: EOF”

3、设置界面哔哩哔哩UP动态，输入UID后，点击链接，出现“Bilibili已连接，首次同步失败（订阅源抓取失败: Client error '403 Forbidden' for url 'https://rsshub.app/bilibili/user/dynamic/174501086' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403）。可稍后手动点“同步”重试。”，然后点击上方UID右侧刷新按钮，出现“订阅源抓取失败: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1028)”

4、DeepSeek链接无问题

5、阿里巴巴（Qwen）链接无问题

6、OpenAI（黑胡子）用不了，配置好后（base_url:https://code.heihuzi.ai/v1，mdel:gpt-5.2-codex）显示“Expecting value: line 1 column 1 (char 0)”

7、Claude同理

8、RSS/Blog无问题，但是前端我点击同步，显示可以同步完成，但是看不到这个网站的具体内容显示

![1770393088824](image/test1-易潇/1770393088824.png)
