export const QUICK_PROMPTS = [
  "今天最值得我看三条更新是什么？",
  "帮我梳理最近7天这个话题的变化？",
  "我现在最该优先关注什么？",
  "给我一个10分钟的信息阅读计划？",
];

export const PROACTIVE_POLL_MS = 45_000;

export const AELIN_CHAT_STORAGE_KEY = "aelin:chat:v1";
export const AELIN_SESSIONS_STORAGE_KEY = "aelin:sessions:v1";
export const AELIN_LAST_SESSION_KEY = "aelin:last-session-id:v1";
export const AELIN_LAST_DESK_BRIDGE_KEY = "aelin:last-desk-bridge:v1";
export const MAX_PERSISTED_MESSAGES = 180;
export const MAX_PERSISTED_IMAGE_DATA_URL = 320_000;
export const MAX_PERSISTED_SESSIONS = 20;
export const AELIN_LOGO_SRC = "/logo.png";
export const CUSTOM_PROVIDER_OPTION = "__custom__";

export const AELIN_EXPRESSION_IDS = [
  "exp-01",
  "exp-02",
  "exp-03",
  "exp-04",
  "exp-05",
  "exp-06",
  "exp-07",
  "exp-08",
  "exp-09",
  "exp-10",
  "exp-11",
] as const;

export type AelinExpressionId = (typeof AELIN_EXPRESSION_IDS)[number];

export const AELIN_EXPRESSION_SRC: Record<AelinExpressionId, string> = AELIN_EXPRESSION_IDS.reduce(
  (acc, id) => {
    acc[id] = `/expressions/${id}.png`;
    return acc;
  },
  {} as Record<AelinExpressionId, string>
);

export const AELIN_EXPRESSION_META: Record<AelinExpressionId, { label: string; usage: string }> = {
  "exp-01": { label: "捂嘴惊喜", usage: "害羞、惊喜、被夸时的可爱反馈" },
  "exp-02": { label: "热情出击", usage: "开场打招呼、推进执行、强积极反馈" },
  "exp-03": { label: "温柔赞同", usage: "支持、认可、安抚、温和鼓励" },
  "exp-04": { label: "托腮思考", usage: "解释、分析、答疑、默认交流" },
  "exp-05": { label: "轻声提醒", usage: "注意事项、风险提示、保守建议" },
  "exp-06": { label: "偷看观察", usage: "围观进展、持续关注、等待更多线索" },
  "exp-07": { label: "低落求助", usage: "失败、遗憾、道歉、需要帮助" },
  "exp-08": { label: "不满委屈", usage: "吐槽、不爽、抗议、情绪性反馈" },
  "exp-09": { label: "指着大笑", usage: "玩梗、幽默、轻松调侃" },
  "exp-10": { label: "发财得意", usage: "成果突出、搞定任务、高价值收获" },
  "exp-11": { label: "趴桌躺平", usage: "困倦、过载、精力不足、需要休息" },
};

export type PlatformKey =
  | "bilibili"
  | "douyin"
  | "xiaohongshu"
  | "weibo"
  | "x"
  | "github"
  | "rss"
  | "web"
  | "email"
  | "generic";

export const PLATFORM_META: Record<PlatformKey, { label: string; color: string; bg: string; border: string }> = {
  bilibili: { label: "Bilibili", color: "#00A1D6", bg: "rgba(0,161,214,0.14)", border: "rgba(0,161,214,0.38)" },
  douyin: { label: "抖音", color: "#12D6CC", bg: "rgba(18,214,204,0.14)", border: "rgba(18,214,204,0.36)" },
  xiaohongshu: { label: "小红书", color: "#FF2442", bg: "rgba(255,36,66,0.12)", border: "rgba(255,36,66,0.36)" },
  weibo: { label: "微博", color: "#E6162D", bg: "rgba(230,22,45,0.11)", border: "rgba(230,22,45,0.32)" },
  x: { label: "X", color: "#121212", bg: "rgba(18,18,18,0.10)", border: "rgba(18,18,18,0.28)" },
  github: { label: "GitHub", color: "#24292E", bg: "rgba(36,41,46,0.10)", border: "rgba(36,41,46,0.28)" },
  rss: { label: "RSS", color: "#F26522", bg: "rgba(242,101,34,0.11)", border: "rgba(242,101,34,0.33)" },
  web: { label: "Web", color: "#2563EB", bg: "rgba(37,99,235,0.11)", border: "rgba(37,99,235,0.34)" },
  email: { label: "Email", color: "#6A9BCC", bg: "rgba(106,155,204,0.13)", border: "rgba(106,155,204,0.35)" },
  generic: { label: "Source", color: "#7A786F", bg: "rgba(122,120,111,0.11)", border: "rgba(122,120,111,0.26)" },
};

export const PLATFORM_ALIASES: Record<string, PlatformKey> = {
  bilibili: "bilibili",
  bili: "bilibili",
  douyin: "douyin",
  抖音: "douyin",
  xiaohongshu: "xiaohongshu",
  小红书: "xiaohongshu",
  xhs: "xiaohongshu",
  weibo: "weibo",
  微博: "weibo",
  x: "x",
  twitter: "x",
  推特: "x",
  web: "web",
  搜索: "web",
  github: "github",
  rss: "rss",
  imap: "email",
  email: "email",
  邮件: "email",
};

export const TRACKING_SOURCE_LABEL: Record<string, string> = {
  auto: "自动",
  web: "Web",
  rss: "RSS",
  x: "X",
  douyin: "抖音",
  xiaohongshu: "小红书",
  weibo: "微博",
  bilibili: "Bilibili",
  email: "邮箱",
};

export const TRACKING_STATUS_META: Record<
  string,
  { label: string; color: "success" | "info" | "warning" | "error" | "default" }
> = {
  active: { label: "进行中", color: "success" },
  paused: { label: "已暂停", color: "warning" },
  error: { label: "异常", color: "error" },
  deleted: { label: "已删除", color: "default" },
  created: { label: "已创建", color: "info" },
  seeded: { label: "已预热", color: "info" },
  sync_started: { label: "同步中", color: "success" },
  tracking_enabled: { label: "已开启", color: "success" },
  needs_config: { label: "需配置", color: "warning" },
  failed: { label: "失败", color: "error" },
};

export type DeviceMode = "meeting" | "focus" | "sleep" | "normal";
export type DeviceSortBy = "cpu" | "memory";

export const DEVICE_MODE_META: Record<DeviceMode, { label: string; detail: string }> = {
  meeting: { label: "开会模式", detail: "静音场景优先，限制通知横幅，降低打扰。" },
  focus: { label: "专注模式", detail: "压制弹窗并弱化 WeChat 干扰。" },
  sleep: { label: "睡眠模式", detail: "降低亮度并进入低打扰状态。" },
  normal: { label: "恢复模式", detail: "恢复通知策略，回到日常状态。" },
};
