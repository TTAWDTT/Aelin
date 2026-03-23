function normalizeProcessToken(raw) {
  return String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/\.exe$/i, "");
}

function parseProcessTokenList(raw, fallback) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  const values = text
    .split(/[,\n;|]/)
    .map((item) => normalizeProcessToken(item))
    .filter(Boolean);
  return values.length ? values : fallback;
}

const DEFAULT_WORK_PROCESS_TOKENS = [
  "codex",
  "codex-cli",
  "claude",
  "claude-code",
  "aider",
  "gemini",
  "gemini-cli",
  "qwen-code",
  "roo",
  "roo-code",
  "cline",
  "code",
  "code-insiders",
  "cursor",
  "windsurf",
  "trae",
  "idea64",
  "webstorm64",
  "pycharm64",
  "clion64",
  "devenv",
  "winword",
  "excel",
  "powerpnt",
  "onenote",
  "outlook",
  "wps",
  "wpp",
  "et",
];

const DEFAULT_MUSIC_PROCESS_TOKENS = [
  "spotify",
  "qqmusic",
  "cloudmusic",
  "kugou",
  "kwmusic",
  "itunes",
  "foobar2000",
  "vlc",
  "potplayer",
  "aimp",
  "music",
];

const WORK_PROCESS_TOKENS = parseProcessTokenList(process.env.AELIN_WORK_PROCESSES, DEFAULT_WORK_PROCESS_TOKENS);
const MUSIC_PROCESS_TOKENS = parseProcessTokenList(process.env.AELIN_MUSIC_PROCESSES, DEFAULT_MUSIC_PROCESS_TOKENS);

const PROCESS_DISPLAY_NAMES = {
  code: "VS Code",
  "code-insiders": "VS Code Insiders",
  cursor: "Cursor",
  windsurf: "Windsurf",
  trae: "Trae",
  codex: "Codex",
  "codex-cli": "Codex CLI",
  claude: "Claude",
  "claude-code": "Claude Code",
  aider: "Aider",
  gemini: "Gemini",
  "gemini-cli": "Gemini CLI",
  "qwen-code": "Qwen Code",
  roo: "Roo",
  "roo-code": "Roo Code",
  cline: "Cline",
  idea64: "IntelliJ IDEA",
  webstorm64: "WebStorm",
  pycharm64: "PyCharm",
  clion64: "CLion",
  devenv: "Visual Studio",
  winword: "Word",
  excel: "Excel",
  powerpnt: "PowerPoint",
  onenote: "OneNote",
  outlook: "Outlook",
  wps: "WPS",
  wpp: "WPS 演示",
  et: "WPS 表格",
  spotify: "Spotify",
  qqmusic: "QQ 音乐",
  cloudmusic: "网易云音乐",
  kugou: "酷狗音乐",
  kwmusic: "酷我音乐",
  itunes: "iTunes",
  foobar2000: "Foobar2000",
  vlc: "VLC",
  potplayer: "PotPlayer",
  aimp: "AIMP",
  music: "音乐播放器",
};

function displayProcessName(rawName) {
  const normalized = normalizeProcessToken(rawName);
  return PROCESS_DISPLAY_NAMES[normalized] || String(rawName || "").trim() || "unknown";
}

function uniqueDisplayNames(names, maxItems = 3) {
  const seen = new Set();
  const out = [];
  for (const name of names || []) {
    const display = displayProcessName(name);
    const key = display.toLowerCase();
    if (!display || seen.has(key)) continue;
    seen.add(key);
    out.push(display);
    if (out.length >= maxItems) break;
  }
  return out;
}

function classifyWorkMode(processNames) {
  const values = Array.isArray(processNames) ? processNames.map((item) => normalizeProcessToken(item)) : [];
  const hasCoding = values.some((name) => [
    "code",
    "code-insiders",
    "cursor",
    "windsurf",
    "trae",
    "codex",
    "codex-cli",
    "claude",
    "claude-code",
    "aider",
    "gemini",
    "gemini-cli",
    "qwen-code",
    "roo",
    "roo-code",
    "cline",
    "idea64",
    "webstorm64",
    "pycharm64",
    "clion64",
    "devenv",
  ].includes(name));
  if (hasCoding) return "coding";
  const hasOffice = values.some((name) => [
    "winword",
    "excel",
    "powerpnt",
    "onenote",
    "outlook",
    "wps",
    "wpp",
    "et",
  ].includes(name));
  if (hasOffice) return "office";
  return "generic";
}

function buildWorkNarration(workMatches, workDisplayNames, workDurationMin) {
  const names = Array.isArray(workDisplayNames) ? workDisplayNames.filter(Boolean) : [];
  if (!names.length) {
    return "当前没有检测到工作进程哦主人~";
  }
  const focusedFor = Number(workDurationMin || 0) > 0 ? `，已专注 ${Math.floor(workDurationMin)} 分钟` : "";
  const target = names.join("、");
  const mode = classifyWorkMode(workMatches);
  if (mode === "coding") {
    return `正在使用${target}写代码呢主人${focusedFor}！`;
  }
  if (mode === "office") {
    return `正在使用${target}处理工作文档呢主人${focusedFor}！`;
  }
  return `主人正在忙${target}${focusedFor}，Aelin会继续守着你~`;
}

module.exports = {
  MUSIC_PROCESS_TOKENS,
  WORK_PROCESS_TOKENS,
  buildWorkNarration,
  displayProcessName,
  normalizeProcessToken,
  uniqueDisplayNames,
};
