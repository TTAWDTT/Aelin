import { useLocaleStore } from '@/shared/stores/localeStore'

type Locale = 'zh' | 'en'

type ChatKeys =
  | 'status.thinking'
  | 'status.capture.fullscreen'
  | 'status.capture.region'
  | 'status.attach.processing'
  | 'status.tools.invoking'
  | 'status.tools.summary'
  | 'error.screenshot'
  | 'error.attach.process'
  | 'error.attach.send'
  | 'nav.title'
  | 'nav.subtitle'
  | 'empty.greeting'
  | 'empty.title'
  | 'empty.description'
  | 'composer.placeholder'
  | 'composer.attach.limit'
  | 'composer.attach.limit.withIgnored'
  | 'composer.attach.partialFail'
  | 'composer.capture.menu'
  | 'composer.capture.fullscreen'
  | 'composer.capture.region'
  | 'composer.capture.open'
  | 'composer.capture.close'
  | 'composer.capture.pendingAttachments'
  | 'composer.capture.capturing'
  | 'composer.attach.processing'
  | 'composer.attach.upload'
  | 'composer.send.stop'
  | 'composer.send.send'
  | 'timeline.generating'
  | 'trace.title'
  | 'trace.steps'
  | 'trace.status.running'
  | 'trace.status.completed'
  | 'trace.status.skipped'
  | 'trace.status.failed'
  | 'trace.status.unknown'
  | 'trace.executionPane.title'
  | 'trace.tab.aelin'
  | 'trace.tab.plane'
  | 'trace.tab.tools'
  | 'trace.executionPane.empty'
  | 'trace.executionPane.headerOpen'
  | 'trace.executionPane.headerClosed'
  | 'trace.executionPane.emptyDetail'
  | 'trace.plane.empty'
  | 'trace.plane.title'
  | 'trace.plane.state.running'
  | 'trace.plane.state.completed'
  | 'trace.plane.state.waiting'
  | 'trace.plane.state.failed'
  | 'trace.plane.state.unknown'
  | 'trace.plane.waitingUser'
  | 'trace.tools.empty'
  | 'trace.plane.tools.heading'
  | 'trace.plane.tools.showAll'
  | 'trace.tools.round'
  | 'trace.tools.count'
  | 'trace.tools.read'
  | 'trace.tools.write'
  | 'plane.chip.label'
  | 'plane.chip.status.running'
  | 'plane.chip.status.completed'
  | 'plane.chip.status.waiting'
  | 'plane.chip.status.failed'
  | 'plane.chip.status.unknown'
  | 'actions.heading'
  | 'actions.confirm.cta'
  | 'actions.confirm.pending'
  | 'actions.open'
  | 'session.new'
  | 'session.switch'
  | 'session.delete'
  | 'session.nav.prev'
  | 'session.nav.next'

const ZH: Record<ChatKeys, string> = {
  'status.thinking': '正在思考…',
  'status.capture.fullscreen': '正在全屏截图…',
  'status.capture.region': '等待框选截图…',
  'status.attach.processing': '附件处理中…',
  'status.tools.invoking': '正在调用工具… {tools}',
  'status.tools.summary': '本轮调用了 {count} 个工具（{tools}），详情见执行面板。',
  'error.screenshot': '截图失败，请稍后重试',
  'error.attach.process': '附件处理失败，请稍后重试',
  'error.attach.send': '附件发送失败，请稍后重试',
  'nav.title': 'Chat',
  'nav.subtitle': 'Aelin 在线中',
  'empty.greeting': '你好，欢迎回来',
  'empty.title': '需要我为你做些什么？',
  'empty.description': '输入消息后，Aelin 会继续在底部输入框中保持会话。',
  'composer.placeholder': '输入消息…',
  'composer.attach.limit': '最多可添加 {max} 个附件',
  'composer.attach.limit.withIgnored': '最多可添加 {max} 个附件，已忽略 {ignored} 个',
  'composer.attach.partialFail': '部分附件上传失败：{names}',
  'composer.capture.menu': '截图菜单',
  'composer.capture.fullscreen': '全屏截图',
  'composer.capture.region': '自定义截图',
  'composer.capture.open': '打开截图菜单',
  'composer.capture.close': '关闭截图菜单',
  'composer.capture.pendingAttachments': '请先发送待处理附件',
  'composer.capture.capturing': '正在截图',
  'composer.attach.processing': '正在处理附件',
  'composer.attach.upload': '上传附件',
  'composer.send.stop': '停止生成',
  'composer.send.send': '发送消息',
  'timeline.generating': '正在生成…',
  'trace.title': 'Agent 链路',
  'trace.steps': '{count} 步',
  'trace.status.running': '进行中',
  'trace.status.completed': '完成',
  'trace.status.skipped': '跳过',
  'trace.status.failed': '失败',
  'trace.status.unknown': '未知',
  'trace.executionPane.title': '执行面板',
  'trace.tab.aelin': 'Aelin 链路',
  'trace.tab.plane': 'Plane 链路',
  'trace.tab.tools': '工具调用',
  'trace.executionPane.empty': '暂无执行信息',
  'trace.executionPane.headerOpen': '执行面板',
  'trace.executionPane.headerClosed': '打开执行面板',
  'trace.executionPane.emptyDetail': '暂无可展示的工具调用或 plane 链路。当 Aelin 使用工具或 plane 处理你的请求时，这里会显示更详细的执行步骤。',
  'trace.plane.empty': '当前没有可展示的 plane 任务。',
  'trace.plane.title': '浏览器 plane（{plane}）',
  'trace.plane.state.running': '正在执行',
  'trace.plane.state.completed': '已完成',
  'trace.plane.state.waiting': '等待你的继续操作',
  'trace.plane.state.failed': '执行失败',
  'trace.plane.state.unknown': '状态未知',
  'trace.plane.waitingUser': '浏览器 plane 正在等待你在受控浏览器中完成登录或确认操作。完成后，可以在聊天中告诉我「已登录，继续」。',
  'trace.tools.empty': '本轮暂未调用任何原子工具。',
  'trace.plane.tools.heading': '本轮与浏览器 plane 相关的调用',
  'trace.plane.tools.showAll': '查看全部工具调用',
  'trace.tools.round': 'Round {round}',
  'trace.tools.count': '{count} 个调用',
  'trace.tools.read': 'READ',
  'trace.tools.write': 'WRITE',
  'plane.chip.label': 'Aelin → {plane} · {status}',
  'plane.chip.status.running': '进行中…',
  'plane.chip.status.completed': '已完成',
  'plane.chip.status.waiting': '等待登录/确认',
  'plane.chip.status.failed': '执行失败',
  'plane.chip.status.unknown': '状态未知',
  'actions.heading': '建议动作 ({count})',
  'actions.confirm.cta': '确认并继续',
  'actions.confirm.pending': '处理中…',
  'actions.open': '打开',
  'session.new': '新对话',
  'session.switch': '切换会话：{title}',
  'session.delete': '删除会话：{title}',
  'session.nav.prev': '向左查看会话',
  'session.nav.next': '向右查看会话',
}

const EN: Record<ChatKeys, string> = {
  'status.thinking': 'Thinking…',
  'status.capture.fullscreen': 'Capturing full screen…',
  'status.capture.region': 'Waiting for region selection…',
  'status.attach.processing': 'Processing attachments…',
  'status.tools.invoking': 'Calling tools… {tools}',
  'status.tools.summary': 'This turn invoked {count} tool(s) ({tools}). See execution panel for details.',
  'error.screenshot': 'Screenshot failed, please try again later.',
  'error.attach.process': 'Attachment processing failed, please try again later.',
  'error.attach.send': 'Attachment sending failed, please try again later.',
  'nav.title': 'Chat',
  'nav.subtitle': 'Aelin is online',
  'empty.greeting': 'Hi, welcome back',
  'empty.title': 'What can I help you with today?',
  'empty.description': 'Once you send a message, Aelin will keep the conversation going in the bottom input bar.',
  'composer.placeholder': 'Type a message…',
  'composer.attach.limit': 'You can add up to {max} attachments.',
  'composer.attach.limit.withIgnored':
    'You can add up to {max} attachments, ignored {ignored}.',
  'composer.attach.partialFail': 'Some attachments failed to upload: {names}',
  'composer.capture.menu': 'Screenshot menu',
  'composer.capture.fullscreen': 'Full screen screenshot',
  'composer.capture.region': 'Custom region screenshot',
  'composer.capture.open': 'Open capture menu',
  'composer.capture.close': 'Close capture menu',
  'composer.capture.pendingAttachments': 'Please send pending attachments first',
  'composer.capture.capturing': 'Capturing screenshot',
  'composer.attach.processing': 'Processing attachments',
  'composer.attach.upload': 'Upload attachments',
  'composer.send.stop': 'Stop generation',
  'composer.send.send': 'Send message',
  'timeline.generating': 'Generating…',
  'trace.title': 'Agent trace',
  'trace.steps': '{count} steps',
  'trace.status.running': 'running',
  'trace.status.completed': 'completed',
  'trace.status.skipped': 'skipped',
  'trace.status.failed': 'failed',
  'trace.status.unknown': 'unknown',
  'trace.executionPane.title': 'Execution panel',
  'trace.tab.aelin': 'Aelin chain',
  'trace.tab.plane': 'Plane chain',
  'trace.tab.tools': 'Tool calls',
  'trace.executionPane.empty': 'No execution info yet',
  'trace.executionPane.headerOpen': 'Execution panel',
  'trace.executionPane.headerClosed': 'Open execution panel',
  'trace.executionPane.emptyDetail':
    'No tool calls or plane traces to show yet. When Aelin uses tools or planes to handle your request, detailed steps will appear here.',
  'trace.plane.empty': 'No plane task to display for this turn.',
  'trace.plane.title': 'Browser plane ({plane})',
  'trace.plane.state.running': 'running',
  'trace.plane.state.completed': 'completed',
  'trace.plane.state.waiting': 'waiting for your action',
  'trace.plane.state.failed': 'failed',
  'trace.plane.state.unknown': 'state unknown',
  'trace.plane.waitingUser':
    'The browser plane is waiting for you to complete login or confirmation in the controlled browser window. Once done, tell me in chat so I can continue.',
  'trace.tools.empty': 'No atomic tools were invoked in this turn.',
  'trace.plane.tools.heading': 'Tool calls related to browser plane',
  'trace.plane.tools.showAll': 'Show all tool calls',
  'trace.tools.round': 'Round {round}',
  'trace.tools.count': '{count} call(s)',
  'trace.tools.read': 'READ',
  'trace.tools.write': 'WRITE',
  'plane.chip.label': 'Aelin → {plane} · {status}',
  'plane.chip.status.running': 'in progress',
  'plane.chip.status.completed': 'completed',
  'plane.chip.status.waiting': 'waiting for login/confirmation',
  'plane.chip.status.failed': 'failed',
  'plane.chip.status.unknown': 'unknown',
  'actions.heading': 'Suggested actions ({count})',
  'actions.confirm.cta': 'Confirm and continue',
  'actions.confirm.pending': 'Working…',
  'actions.open': 'Open',
  'session.new': 'New chat',
  'session.switch': 'Switch conversation: {title}',
  'session.delete': 'Delete conversation: {title}',
  'session.nav.prev': 'View previous conversations',
  'session.nav.next': 'View next conversations',
}

const TABLE: Record<Locale, Record<ChatKeys, string>> = {
  zh: ZH,
  en: EN,
}

export function useChatI18n() {
  const { locale } = useLocaleStore()
  const lang: Locale = locale === 'en' ? 'en' : 'zh'

  const t = (key: ChatKeys, vars?: Record<string, string | number>) => {
    const template = TABLE[lang][key] ?? key
    if (!vars) return template
    return Object.keys(vars).reduce(
      (acc, k) => acc.replace(new RegExp(`\\{${k}\\}`, 'g'), String(vars[k])),
      template
    )
  }

  return { t, locale: lang }
}
