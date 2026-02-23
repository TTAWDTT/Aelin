from __future__ import annotations

import re

_SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass", ".ssa", ".ttml", ".srv1", ".srv2", ".srv3"}
_TIMECODE_RE = re.compile(
    r"^\s*(\d+:)?\d{2}:\d{2}(?:[.,]\d{1,3})?\s*-->\s*(\d+:)?\d{2}:\d{2}(?:[.,]\d{1,3})?(?:\s+.*)?$"
)
_SRT_INDEX_RE = re.compile(r"^\s*\d+\s*$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BRACE_TAG_RE = re.compile(r"\{\\[^}]+\}")
_MULTISPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"(?:^|\s)#[A-Za-z0-9_\-\u4e00-\u9fff]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")
_PROMO_PHRASE_RE = re.compile(
    r"(?i)\b(subscribe|follow|like|share|click here|link in bio|learn more|download app|check out)\b"
)
_DOUYIN_NOISE_FRAGMENT_RE = re.compile(
    r"(?i)(开启读屏标签|读屏标签已关闭|下载抖音|京ICP备|公网安备|版权所有|反馈|举报|隐私|用户协议|营业执照|广告投放|抖音精选|推荐|关注|朋友|直播|放映厅|小游戏)"
)
_DOUYIN_AUTH_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_tt",
    "sid_guard",
}
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".flv", ".m4v"}
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_PLATFORM_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("youtube", ("youtube.com", "youtu.be")),
    ("bilibili", ("bilibili.com", "b23.tv")),
    ("douyin", ("douyin.com", "iesdouyin.com")),
    ("tiktok", ("tiktok.com", "vt.tiktok.com")),
    ("x", ("x.com", "twitter.com", "t.co")),
    ("instagram", ("instagram.com",)),
    ("facebook", ("facebook.com", "fb.watch")),
    ("youku", ("youku.com", "v.youku.com")),
]

_DEFAULT_LANGUAGE_PREFERENCES = ["zh-Hans", "zh-CN", "zh", "en"]
