import { useLocaleStore } from '@/shared/stores/localeStore'

type Locale = 'zh' | 'en'

type ChatKeys =
  | 'status.thinking'
  | 'status.execution.available'
  | 'status.capture.fullscreen'
  | 'status.capture.region'
  | 'status.attach.processing'
  | 'status.tools.invoking'
  | 'status.tools.summary'
  | 'error.screenshot'
  | 'error.attach.process'
  | 'error.attach.send'
  | 'error.llm.notConfigured'
  | 'error.llm.generic'
  | 'status.cancelled'
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
  | 'trace.executionPane.title'
  | 'trace.tab.tools'
  | 'trace.executionPane.empty'
  | 'trace.executionPane.headerOpen'
  | 'trace.executionPane.emptyDetail'
  | 'trace.files.heading'
  | 'trace.files.empty'
  | 'trace.files.helper'
  | 'trace.tools.empty'
  | 'trace.tools.count'
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
  'status.execution.available': '可查看本轮执行详情。',
  'status.capture.fullscreen': '正在全屏截图…',
  'status.capture.region': '等待框选截图…',
  'status.attach.processing': '附件处理中…',
  'status.tools.invoking': '正在调用工具… {tools}',
  'status.tools.summary': '本轮调用了 {count} 个工具（{tools}），详情见执行面板。',
  'error.screenshot': '截图失败，请稍后重试',
  'error.attach.process': '附件处理失败，请稍后重试',
  'error.attach.send': '附件发送失败，请稍后重试',
  'error.llm.notConfigured': '当前会话未配置可用模型，请在设置中先完成模型配置。',
  'error.llm.generic': '本轮对话发生错误，请稍后重试。',
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
  'status.cancelled': '已停止本轮对话。',
  'trace.executionPane.title': '执行面板',
  'trace.tab.tools': '工具调用',
  'trace.executionPane.empty': '暂无执行信息',
  'trace.executionPane.headerOpen': '执行面板',
  'trace.executionPane.emptyDetail': '暂无可展示的执行信息。当本轮运行产生工具、状态或子代理数据时，这里会直接展示。',
  'trace.files.heading': '运行时文件',
  'trace.files.empty': '当前状态里还没有可预览的文件。',
  'trace.files.helper': '这些文件直接来自本轮运行的 state/files，可点击预览或下载。',
  'trace.tools.empty': '本轮暂未调用任何原子工具。',
  'trace.tools.count': '{count} 个调用',
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
  'status.execution.available': 'Execution details are available.',
  'status.capture.fullscreen': 'Capturing full screen…',
  'status.capture.region': 'Waiting for region selection…',
  'status.attach.processing': 'Processing attachments…',
  'status.tools.invoking': 'Calling tools… {tools}',
  'status.tools.summary': 'This turn invoked {count} tool(s) ({tools}). See execution panel for details.',
  'error.screenshot': 'Screenshot failed, please try again later.',
  'error.attach.process': 'Attachment processing failed, please try again later.',
  'error.attach.send': 'Attachment sending failed, please try again later.',
  'error.llm.notConfigured': 'No model is configured for this workspace. Please configure a model in Settings first.',
  'error.llm.generic': 'Something went wrong in this turn. Please try again.',
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
  'status.cancelled': 'This turn has been cancelled.',
  'trace.executionPane.title': 'Execution panel',
  'trace.tab.tools': 'Tool calls',
  'trace.executionPane.empty': 'No execution info yet',
  'trace.executionPane.headerOpen': 'Execution panel',
  'trace.executionPane.emptyDetail':
    'No execution data to show yet. Tool calls, state snapshots, and subagent activity will appear here when available.',
  'trace.files.heading': 'Runtime files',
  'trace.files.empty': 'No previewable files have been materialized in state yet.',
  'trace.files.helper': 'These files come directly from the current run state and can be previewed or downloaded.',
  'trace.tools.empty': 'No atomic tools were invoked in this turn.',
  'trace.tools.count': '{count} call(s)',
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
