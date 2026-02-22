from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.services.llm import LLMService
from app.services.summarizer import RuleBasedSummarizer
from app.settings import settings

_LOG = logging.getLogger(__name__)

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


class MediaIngestError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class MediaIngestOutput:
    platform: str
    url: str
    canonical_url: str
    title: str
    source_type: str
    source_language: str
    summary: str
    insight_title: str
    insight_markdown: str
    confidence: float
    reason: str
    limitations: list[str]
    summary_overview: str = ""
    information_note: str = ""
    quality_score: float = 1.0
    quality_reason: str = "quality_not_evaluated"
    quality_usable: bool = True
    needs_review: bool = False
    quality_flags: list[str] = field(default_factory=list)


class MediaIngestService:
    def __init__(self) -> None:
        self._fallback = RuleBasedSummarizer()
        self._subtitle_min_chars = 120
        self._description_min_chars = 80
        self._description_min_sentences = 2
        self._description_min_quality = 0.64
        self._subtitle_auto_min_quality = 0.52
        self._subtitle_manual_min_quality = 0.46
        self._max_model_input_chars = 12000
        self._run_timeout_seconds = 140
        self._cookie_mode = str(getattr(settings, "media_ingest_cookie_mode", "off") or "off").strip().lower()
        self._cookie_browser = str(getattr(settings, "media_ingest_cookie_browser", "chrome") or "chrome").strip()
        self._cookie_browser_profile = str(getattr(settings, "media_ingest_cookie_browser_profile", "") or "").strip()
        self._cookie_file = str(getattr(settings, "media_ingest_cookie_file", "") or "").strip()
        self._proxy_url = str(getattr(settings, "media_ingest_proxy_url", "") or "").strip()

    def ingest(
        self,
        *,
        user_id: int,
        workspace: str,
        url: str,
        service: LLMService,
        provider: str,
        languages: list[str] | None = None,
    ) -> MediaIngestOutput:
        _ = user_id
        _ = workspace
        canonical_url = self._normalize_url(url)
        platform = self.detect_platform(canonical_url)
        if platform == "unsupported":
            raise MediaIngestError("unsupported_platform", "当前仅支持 YouTube/Bilibili/抖音/TikTok/X/Instagram/Facebook/Youku URL")

        ytdlp_cmd = self._resolve_ytdlp_command()
        if not ytdlp_cmd:
            raise MediaIngestError("tool_missing", "未检测到 yt-dlp，请先安装后重试")

        language_preferences = self._normalize_languages(languages)
        metadata = self._fetch_metadata(ytdlp_cmd=ytdlp_cmd, url=canonical_url)
        title = str(metadata.get("title") or "").strip()[:220] or f"{platform} content"
        description = str(metadata.get("description") or "").strip()

        extracted_text, source_type, source_language = self._extract_best_text(
            ytdlp_cmd=ytdlp_cmd,
            url=canonical_url,
            description=description,
            language_preferences=language_preferences,
        )

        if source_type.startswith("subtitle") and len(extracted_text) < self._subtitle_min_chars:
            raise MediaIngestError("subtitle_too_short", "字幕内容过短，无法生成可靠摘要")
        if source_type == "description" and len(extracted_text) < self._description_min_chars:
            raise MediaIngestError("description_too_short", "可用描述文本不足，无法生成摘要")

        summary_struct = self._summarize_structured(
            service=service,
            provider=provider,
            platform=platform,
            title=title,
            source_type=source_type,
            source_language=source_language,
            text=extracted_text,
            canonical_url=canonical_url,
        )

        confidence = self._confidence_score(
            model_score=summary_struct.get("confidence"),
            source_type=source_type,
            content_length=len(extracted_text),
        )
        limitations = ["摘要主要基于字幕/文本，不覆盖纯视觉镜头语义。"]
        if source_type == "description":
            limitations.append("当前未提取到字幕，改用描述文本生成，置信度较低。")
        if source_type == "subtitle_auto":
            limitations.append("当前使用自动字幕，可能存在识别误差。")

        insight_title = str(summary_struct.get("title") or title).strip()[:180] or title
        overview = self._normalize_paragraph(str(summary_struct.get("overview") or ""), max_len=500)
        information_note = self._normalize_paragraph(str(summary_struct.get("information_note") or ""), max_len=1400)
        key_points = self._normalize_string_list(summary_struct.get("key_points"), max_items=6)
        evidence = self._normalize_string_list(summary_struct.get("evidence"), max_items=5)
        actions = self._normalize_string_list(summary_struct.get("actions"), max_items=4)
        if not overview:
            overview = self._normalize_paragraph(self._fallback.summarize(extracted_text), max_len=500)
        if not key_points:
            key_points = self._split_sentences(extracted_text)[:4]
        if not evidence:
            evidence = self._split_sentences(extracted_text)[4:7]
            if not evidence:
                evidence = key_points[:2]
        if not actions:
            actions = ["如需用于决策，请结合原视频或原帖再核对一次关键信息。"]
        if not information_note:
            information_note = self._compose_information_note(
                title=insight_title,
                overview=overview,
                key_points=key_points,
                evidence=evidence,
                actions=actions,
                source_type=source_type,
            )

        quality = self._assess_summary_quality(
            source_type=source_type,
            extracted_text=extracted_text,
            overview=overview,
            information_note=information_note,
            key_points=key_points,
            evidence=evidence,
            actions=actions,
            confidence=confidence,
        )
        quality_score = float(quality["score"])
        quality_reason = str(quality["reason"])
        quality_usable = bool(quality["usable"])
        needs_review = bool(quality["needs_review"])
        quality_flags = [str(item) for item in quality.get("flags", []) if str(item).strip()]
        if not quality_usable:
            limitations.append(f"质量门禁未通过：{quality_reason}")

        summary_text = self._render_summary_text(
            overview=overview,
            information_note=information_note,
            confidence=confidence,
            source_type=source_type,
            quality_score=quality_score,
            quality_usable=quality_usable,
        )
        insight_markdown = self._render_insight_markdown(
            title=insight_title,
            overview=overview,
            information_note=information_note,
            key_points=key_points,
            evidence=evidence,
            actions=actions,
            platform=platform,
            canonical_url=canonical_url,
            source_type=source_type,
            source_language=source_language,
            confidence=confidence,
            limitations=limitations,
            quality_score=quality_score,
            quality_reason=quality_reason,
            quality_usable=quality_usable,
            needs_review=needs_review,
            quality_flags=quality_flags,
        )

        reason = str(summary_struct.get("reason") or "").strip()[:280]
        if not reason:
            reason = "media_ingest_completed"
        return MediaIngestOutput(
            platform=platform,
            url=url,
            canonical_url=canonical_url,
            title=title,
            source_type=source_type,
            source_language=source_language,
            summary=summary_text,
            insight_title=insight_title,
            insight_markdown=insight_markdown,
            confidence=confidence,
            reason=reason,
            limitations=limitations,
            summary_overview=overview,
            information_note=information_note,
            quality_score=quality_score,
            quality_reason=quality_reason,
            quality_usable=quality_usable,
            needs_review=needs_review,
            quality_flags=quality_flags,
        )

    def detect_platform(self, url: str) -> str:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return "unsupported"
        if host.startswith("www."):
            host = host[4:]
        for platform, suffixes in _PLATFORM_RULES:
            if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
                return platform
        return "unsupported"

    def _normalize_url(self, url: str) -> str:
        raw = str(url or "").strip()
        if not raw:
            raise MediaIngestError("invalid_url", "URL 不能为空")
        try:
            parsed = urlparse(raw)
        except Exception as exc:
            raise MediaIngestError("invalid_url", f"URL 解析失败: {str(exc)[:80]}") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MediaIngestError("invalid_url", "仅支持 http/https URL")
        normalized = parsed._replace(fragment="", params="")
        return urlunparse(normalized).strip()[:3000]

    def _normalize_languages(self, raw_languages: list[str] | None) -> list[str]:
        source = raw_languages if isinstance(raw_languages, list) and raw_languages else _DEFAULT_LANGUAGE_PREFERENCES
        out: list[str] = []
        seen: set[str] = set()
        for item in source:
            val = str(item or "").strip()
            if not val:
                continue
            lowered = val.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(val[:20])
            if len(out) >= 8:
                break
        return out or list(_DEFAULT_LANGUAGE_PREFERENCES)

    def _resolve_ytdlp_command(self) -> list[str] | None:
        if shutil.which("yt-dlp"):
            return ["yt-dlp"]
        if shutil.which("yt_dlp"):
            return ["yt_dlp"]
        try:
            import importlib.util

            if importlib.util.find_spec("yt_dlp") is not None:
                return [sys.executable, "-m", "yt_dlp"]
        except Exception:
            return None
        return None

    def _run_ytdlp(
        self,
        *,
        ytdlp_cmd: list[str],
        args: list[str],
        url: str,
        cwd: Path,
        network_args: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [*ytdlp_cmd, *args, *(network_args if network_args is not None else self._build_network_args()), "--", url]
        try:
            return subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._run_timeout_seconds,
                encoding="utf-8",
                errors="ignore",
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaIngestError("extract_timeout", "内容提取超时，请稍后重试或更换链接") from exc

    @staticmethod
    def _is_cookie_bootstrap_error(stderr: str, stdout: str) -> bool:
        text = f"{stderr}\n{stdout}".lower()
        return (
            "could not copy chrome cookie database" in text
            or "could not find edge cookies database" in text
            or "could not extract cookies from browser" in text
        )

    def _build_network_args(self) -> list[str]:
        out: list[str] = []
        mode = self._cookie_mode
        if mode == "browser" and self._cookie_browser:
            browser_token = self._cookie_browser
            if self._cookie_browser_profile:
                browser_token = f"{browser_token}:{self._cookie_browser_profile}"
            out.extend(["--cookies-from-browser", browser_token])
        elif mode == "file" and self._cookie_file:
            out.extend(["--cookies", self._cookie_file])
        if self._proxy_url and self._proxy_url.lower() != "off":
            out.extend(["--proxy", self._proxy_url])
        return out

    def _classify_ytdlp_error(self, *, stderr: str, stdout: str) -> tuple[str, str]:
        joined = f"{stderr}\n{stdout}".strip()
        lowered = joined.lower()
        if "fresh cookies" in lowered or ("cookies" in lowered and "required" in lowered):
            return (
                "auth_required",
                "目标平台要求新鲜 cookies（当前常见于抖音/Instagram/Facebook/X）。请配置浏览器 cookies 后重试。",
            )
        if "could not copy chrome cookie database" in lowered or "could not find edge cookies database" in lowered:
            return (
                "cookie_unavailable",
                "当前配置为浏览器 cookies，但本机未能读取浏览器 cookie 库。请关闭浏览器后重试，或改用 cookie 文件模式。",
            )
        if "login required" in lowered or "sign in" in lowered:
            return ("auth_required", "目标内容需要登录态（cookies）才能抓取。")
        if "private video" in lowered or "private content" in lowered:
            return ("private_content", "目标内容是私密资源，当前账号权限不足。")
        if "unsupported url" in lowered or "unsupported webpage" in lowered:
            return ("unsupported_url", "当前链接不被 yt-dlp 支持或链接格式无效。")
        if "geo" in lowered and "blocked" in lowered:
            return ("geo_blocked", "目标内容受地区限制，当前网络环境无法抓取。")
        snippet = joined[:220] if joined else "yt-dlp failed"
        return ("extract_failed", f"获取媒体信息失败: {snippet}")

    def _fetch_metadata(self, *, ytdlp_cmd: list[str], url: str) -> dict[str, Any]:
        network_args = self._build_network_args()
        with tempfile.TemporaryDirectory(prefix="aelin-media-meta-") as tmpdir:
            proc = self._run_ytdlp(
                ytdlp_cmd=ytdlp_cmd,
                args=[
                    "--skip-download",
                    "--no-playlist",
                    "--no-warnings",
                    "--dump-single-json",
                ],
                url=url,
                cwd=Path(tmpdir),
                network_args=network_args,
            )

            if proc.returncode != 0 and network_args and self._is_cookie_bootstrap_error(proc.stderr or "", proc.stdout or ""):
                # Fallback: browser cookie loading failed on this host; retry without auth args.
                proc = self._run_ytdlp(
                    ytdlp_cmd=ytdlp_cmd,
                    args=[
                        "--skip-download",
                        "--no-playlist",
                        "--no-warnings",
                        "--dump-single-json",
                    ],
                    url=url,
                    cwd=Path(tmpdir),
                    network_args=[],
                )
        if proc.returncode != 0:
            code, msg = self._classify_ytdlp_error(stderr=(proc.stderr or ""), stdout=(proc.stdout or ""))
            raise MediaIngestError(code, msg)
        payload = self._extract_first_json_object(proc.stdout or "")
        if not payload:
            payload = self._extract_first_json_object(proc.stderr or "")
        if not payload:
            code, msg = self._classify_ytdlp_error(stderr=(proc.stderr or ""), stdout=(proc.stdout or ""))
            raise MediaIngestError(code, msg if msg else "未获取到可解析的媒体元数据")
        entries = payload.get("entries")
        if isinstance(entries, list) and entries:
            first_entry = entries[0]
            if isinstance(first_entry, dict):
                return first_entry
        return payload

    def _extract_best_text(
        self,
        *,
        ytdlp_cmd: list[str],
        url: str,
        description: str,
        language_preferences: list[str],
    ) -> tuple[str, str, str]:
        subtitle_lang_expr = ",".join(language_preferences)

        manual_text, manual_lang = self._extract_subtitles(
            ytdlp_cmd=ytdlp_cmd,
            url=url,
            subtitle_lang_expr=subtitle_lang_expr,
            auto_sub=False,
            language_preferences=language_preferences,
        )
        if manual_text:
            return manual_text, "subtitle_manual", manual_lang

        auto_text, auto_lang = self._extract_subtitles(
            ytdlp_cmd=ytdlp_cmd,
            url=url,
            subtitle_lang_expr=subtitle_lang_expr,
            auto_sub=True,
            language_preferences=language_preferences,
        )
        if auto_text:
            return auto_text, "subtitle_auto", auto_lang

        fallback_desc = self._sanitize_description_text(description)
        if len(fallback_desc) >= self._description_min_chars:
            return fallback_desc, "description", "unknown"
        raise MediaIngestError("no_extractable_content", "未提取到可用字幕或足够描述文本")

    def _extract_subtitles(
        self,
        *,
        ytdlp_cmd: list[str],
        url: str,
        subtitle_lang_expr: str,
        auto_sub: bool,
        language_preferences: list[str],
    ) -> tuple[str, str]:
        network_args = self._build_network_args()
        with tempfile.TemporaryDirectory(prefix="aelin-media-sub-") as tmpdir:
            workdir = Path(tmpdir)
            args = [
                "--skip-download",
                "--no-playlist",
                "--no-warnings",
                "--output",
                "media.%(ext)s",
                "--sub-langs",
                subtitle_lang_expr,
                "--sub-format",
                "vtt",
            ]
            args.append("--write-auto-subs" if auto_sub else "--write-subs")
            proc = self._run_ytdlp(ytdlp_cmd=ytdlp_cmd, args=args, url=url, cwd=workdir)
            if proc.returncode != 0 and network_args and self._is_cookie_bootstrap_error(proc.stderr or "", proc.stdout or ""):
                proc = self._run_ytdlp(
                    ytdlp_cmd=ytdlp_cmd,
                    args=args,
                    url=url,
                    cwd=workdir,
                    network_args=[],
                )
            if proc.returncode != 0 and not any(path.suffix.lower() in _SUBTITLE_EXTENSIONS for path in workdir.rglob("*")):
                return "", ""
            subtitle_paths = [path for path in workdir.rglob("*") if path.is_file() and path.suffix.lower() in _SUBTITLE_EXTENSIONS]
            if not subtitle_paths:
                return "", ""
            best_path = self._pick_best_subtitle_file(subtitle_paths=subtitle_paths, language_preferences=language_preferences)
            if best_path is None:
                return "", ""
            text = self._subtitle_file_to_text(best_path)
            if len(text) < self._subtitle_min_chars:
                return "", ""
            language = self._guess_language_from_filename(best_path.name, language_preferences)
            return text, language

    def _pick_best_subtitle_file(self, *, subtitle_paths: list[Path], language_preferences: list[str]) -> Path | None:
        if not subtitle_paths:
            return None

        def _score(path: Path) -> tuple[int, int]:
            name = path.name.lower()
            lang_score = 0
            for idx, lang in enumerate(language_preferences):
                key = lang.lower()
                if key and key in name:
                    lang_score = max(lang_score, 20 - idx)
            ext = path.suffix.lower()
            ext_score_map = {
                ".vtt": 6,
                ".srt": 5,
                ".ttml": 4,
                ".srv3": 3,
                ".srv2": 2,
                ".srv1": 1,
                ".ass": 1,
                ".ssa": 1,
            }
            return lang_score, ext_score_map.get(ext, 0)

        ranked = sorted(subtitle_paths, key=_score, reverse=True)
        return ranked[0] if ranked else None

    def _subtitle_file_to_text(self, path: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
        lines: list[str] = []
        for row in raw.splitlines():
            text = row.strip()
            if not text:
                continue
            upper = text.upper()
            if upper.startswith("WEBVTT") or upper.startswith("NOTE") or upper.startswith("STYLE") or upper.startswith("REGION"):
                continue
            if _SRT_INDEX_RE.match(text):
                continue
            if _TIMECODE_RE.match(text):
                continue
            text = _HTML_TAG_RE.sub(" ", text)
            text = _BRACE_TAG_RE.sub(" ", text)
            text = _MULTISPACE_RE.sub(" ", text).strip()
            if not text:
                continue
            if lines and lines[-1] == text:
                continue
            lines.append(text)
        merged = "\n".join(lines)
        return self._normalize_text(merged)

    def _guess_language_from_filename(self, filename: str, language_preferences: list[str]) -> str:
        lower = filename.lower()
        for lang in language_preferences:
            normalized = lang.lower()
            if normalized and normalized in lower:
                return lang
        match = re.search(r"\.([a-z]{2,3}(?:-[a-z]{2,4})?)\.", lower)
        if match:
            return match.group(1)
        return "unknown"

    def _summarize_structured(
        self,
        *,
        service: LLMService,
        provider: str,
        platform: str,
        title: str,
        source_type: str,
        source_language: str,
        text: str,
        canonical_url: str,
    ) -> dict[str, Any]:
        bounded_text = text[: self._max_model_input_chars]
        if provider != "rule_based" and service.is_configured():
            system_prompt = (
                "你是 Aelin 的媒体理解助手。根据提供的字幕/文本生成结构化中文结果。"
                "输出必须是 JSON 对象，字段: title, overview, information_note, key_points, evidence, actions, confidence, reason。"
                "说明：overview 是“总结”（讲这条内容在说什么）；information_note 是“提炼信息”（自然语言日记笔记，不要强制分点）。"
                "其中 key_points/evidence/actions 必须是字符串数组，作为内部校验依据。confidence 为 0~1 数字。"
                "要求：不要复述长链接、标签堆砌和营销文案；优先提取可验证事实。"
                "若文本信息不足，必须明确说明“信息不足”，并将 confidence 控制在 0.35 以下。"
            )
            user_prompt = (
                f"platform={platform}\n"
                f"title={title}\n"
                f"url={canonical_url}\n"
                f"source_type={source_type}\n"
                f"source_language={source_language}\n\n"
                "text:\n"
                f"{bounded_text}"
            )
            try:
                raw = service._chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=780,
                    stream=False,
                )
                parsed = self._extract_first_json_object(str(raw or ""))
                if parsed:
                    return parsed
            except Exception as exc:
                _LOG.warning("media ingest llm summarize failed: %s", exc)
        return self._fallback_structured_summary(
            title=title,
            source_type=source_type,
            source_language=source_language,
            text=bounded_text,
        )

    def _fallback_structured_summary(
        self,
        *,
        title: str,
        source_type: str,
        source_language: str,
        text: str,
    ) -> dict[str, Any]:
        sentences = self._split_sentences(text)
        overview = self._fallback.summarize(text)[:220]
        key_points = sentences[:4] if sentences else ([overview] if overview else [])
        evidence = sentences[4:7] if len(sentences) > 4 else key_points[:2]
        actions = ["如需更高准确度，请补充人工字幕或原文稿。"]
        reason = f"fallback_{source_type}_{source_language}"
        confidence = 0.74 if source_type == "subtitle_manual" else (0.65 if source_type == "subtitle_auto" else 0.46)
        information_note = self._compose_information_note(
            title=title[:160],
            overview=overview,
            key_points=key_points,
            evidence=evidence,
            actions=actions,
            source_type=source_type,
        )
        return {
            "title": title[:160],
            "overview": overview,
            "information_note": information_note,
            "key_points": key_points,
            "evidence": evidence,
            "actions": actions,
            "confidence": confidence,
            "reason": reason,
        }

    def _confidence_score(self, *, model_score: Any, source_type: str, content_length: int) -> float:
        source_base = {
            "subtitle_manual": 0.82,
            "subtitle_auto": 0.72,
            "description": 0.5,
        }.get(source_type, 0.5)
        try:
            parsed = float(model_score)
        except Exception:
            parsed = source_base
        value = max(0.0, min(1.0, parsed))
        if content_length < 300:
            value = min(value, source_base)
        if source_type == "description":
            value = min(value, 0.54)
        return round(max(0.0, min(1.0, value)), 3)

    def _render_summary_text(
        self,
        *,
        overview: str,
        information_note: str,
        confidence: float,
        source_type: str,
        quality_score: float,
        quality_usable: bool,
    ) -> str:
        blocks: list[str] = []
        if overview.strip():
            blocks.append(f"总结：\n{overview.strip()}")
        if information_note.strip():
            blocks.append(f"提炼信息：\n{information_note.strip()}")
        quality_label = "pass" if quality_usable else "review_required"
        blocks.append(
            f"来源类型：{source_type}（confidence={confidence:.2f}，quality={quality_score:.2f}，gate={quality_label}）"
        )
        return "\n\n".join(blocks).strip()

    def _render_insight_markdown(
        self,
        *,
        title: str,
        overview: str,
        information_note: str,
        key_points: list[str],
        evidence: list[str],
        actions: list[str],
        platform: str,
        canonical_url: str,
        source_type: str,
        source_language: str,
        confidence: float,
        limitations: list[str],
        quality_score: float,
        quality_reason: str,
        quality_usable: bool,
        needs_review: bool,
        quality_flags: list[str],
    ) -> str:
        evidence_note = self._render_evidence_note(evidence)
        action_note = self._render_action_note(actions)
        lines: list[str] = [
            "## 总结",
            "",
            overview or "(empty)",
            "",
            "## 提炼信息（日记）",
            "",
            information_note or "(empty)",
            "",
            "## 证据锚点",
            "",
            evidence_note,
            "",
            "## 可执行提醒",
            "",
            action_note,
        ]
        if key_points:
            lines.extend(["", "## 信息标签", ""])
            lines.append("；".join(key_points[:6]) + "。")
        lines.extend(
            [
                "",
                "## 来源元信息",
                "",
                f"- title: {title}",
                f"- platform: {platform}",
                f"- url: {canonical_url}",
                f"- source_type: {source_type}",
                f"- source_language: {source_language}",
                f"- confidence: {confidence:.2f}",
            ]
        )
        lines.extend(
            [
                "",
                "## 质量评估",
                "",
                f"- usable: {str(bool(quality_usable)).lower()}",
                f"- needs_review: {str(bool(needs_review)).lower()}",
                f"- quality_score: {quality_score:.2f}",
                f"- quality_reason: {quality_reason or '(empty)'}",
            ]
        )
        if quality_flags:
            lines.extend([f"- quality_flag: {item}" for item in quality_flags[:6]])
        if limitations:
            lines.extend(["", "## 限制说明", ""])
            lines.extend([f"- {item}" for item in limitations[:4]])
        return "\n".join(lines).strip()

    def _render_evidence_note(self, evidence: list[str]) -> str:
        cleaned: list[str] = []
        for item in evidence:
            normalized = self._normalize_paragraph(item, max_len=220)
            if normalized:
                cleaned.append(normalized)
        if not cleaned:
            return "当前未发现可直接引用的证据片段，建议结合原视频/原帖核对。"
        return "依据文本可见：" + "；".join(cleaned[:4]) + "。"

    def _render_action_note(self, actions: list[str]) -> str:
        cleaned: list[str] = []
        for item in actions:
            normalized = self._normalize_paragraph(item, max_len=180)
            if normalized:
                cleaned.append(normalized)
        if not cleaned:
            return "目前没有稳定可执行动作，建议先核实原始素材。"
        return "后续可考虑：" + "；".join(cleaned[:3]) + "。"

    def _compose_information_note(
        self,
        *,
        title: str,
        overview: str,
        key_points: list[str],
        evidence: list[str],
        actions: list[str],
        source_type: str,
    ) -> str:
        lead = self._normalize_paragraph(overview, max_len=320)
        facts = [self._normalize_paragraph(item, max_len=180) for item in key_points[:4]]
        facts = [item for item in facts if item]
        evidence_note = self._render_evidence_note(evidence)
        action_note = self._render_action_note(actions)

        parts: list[str] = []
        if lead:
            parts.append(f"这条内容围绕“{title}”展开，核心意思是：{lead}")
        if facts:
            parts.append("可直接复用的信息包括：" + "；".join(facts) + "。")
        parts.append(evidence_note)
        parts.append(action_note)
        if source_type == "description":
            parts.append("由于本次主要依据描述文本而非完整字幕，使用时建议再回看原始内容确认细节。")

        return self._normalize_paragraph(" ".join(parts), max_len=1400)

    def _normalize_paragraph(self, text: str, *, max_len: int = 1000) -> str:
        normalized = self._normalize_text(text).replace("\n", " ")
        normalized = _MULTISPACE_RE.sub(" ", normalized).strip(" \t-—;；")
        if not normalized:
            return ""
        return normalized[:max_len]

    def _sanitize_description_text(self, text: str) -> str:
        normalized = self._normalize_text(text)
        if not normalized:
            return ""
        without_urls = _URL_RE.sub(" ", normalized)
        without_hashtags = _HASHTAG_RE.sub(" ", without_urls)
        without_promos = _PROMO_PHRASE_RE.sub(" ", without_hashtags)

        chunks = re.split(r"(?<=[。！？!?\.])\s+|\n+", without_promos)
        out: list[str] = []
        seen: set[str] = set()
        total_len = 0
        for chunk in chunks:
            clean = _MULTISPACE_RE.sub(" ", chunk).strip(" -|•·")
            if len(clean) < 10:
                continue
            if self._is_low_signal_fragment(clean):
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            clipped = clean[:260]
            out.append(clipped)
            total_len += len(clipped)
            if total_len >= 2600 or len(out) >= 18:
                break
        if out:
            return "\n".join(out)
        compact = _MULTISPACE_RE.sub(" ", without_promos).strip()
        return compact[:2600]

    def _is_low_signal_fragment(self, text: str) -> bool:
        snippet = str(text or "").strip()
        if not snippet:
            return True
        if snippet.lower() in {"(empty)", "empty", "none", "n/a"}:
            return True
        url_matches = _URL_RE.findall(snippet)
        url_chars = sum(len(match) for match in url_matches)
        if url_chars > 0 and (url_chars / max(1, len(snippet))) > 0.45:
            return True
        hashtags = _HASHTAG_RE.findall(snippet)
        if len(hashtags) >= 3 and len(snippet) < 90:
            return True
        token_count = len(_TOKEN_RE.findall(snippet))
        if token_count == 0:
            return True
        if token_count == 1 and len(snippet) < 10:
            return True
        return False

    def _assess_summary_quality(
        self,
        *,
        source_type: str,
        extracted_text: str,
        overview: str,
        information_note: str,
        key_points: list[str],
        evidence: list[str],
        actions: list[str],
        confidence: float,
    ) -> dict[str, Any]:
        text = self._normalize_text(extracted_text)
        overview_text = self._normalize_text(overview)
        information_text = self._normalize_text(information_note)
        text_len = len(text)
        overview_len = len(overview_text)
        information_len = len(information_text)
        sentence_count = len(self._split_sentences(text))
        url_hits = _URL_RE.findall(text)
        url_chars = sum(len(match) for match in url_hits)
        url_ratio = url_chars / max(1, text_len)
        hashtag_count = len(_HASHTAG_RE.findall(text))
        tokens = [tok.lower() for tok in _TOKEN_RE.findall(text)]
        unique_ratio = (len(set(tokens)) / max(1, len(tokens))) if tokens else 0.0

        source_base = {
            "subtitle_manual": 0.42,
            "subtitle_auto": 0.34,
            "description": 0.18,
        }.get(source_type, 0.2)
        score = source_base
        score += min(0.18, text_len / 1800.0 * 0.18)
        score += min(0.13, overview_len / 180.0 * 0.13)
        score += min(0.13, information_len / 420.0 * 0.13)
        score += min(0.12, len(key_points) / 3.0 * 0.12)
        score += min(0.09, len(evidence) / 2.0 * 0.09)
        score += min(0.06, len(actions) / 2.0 * 0.06)
        score += max(0.0, min(1.0, float(confidence or 0.0))) * 0.12
        score += min(0.10, unique_ratio * 0.10)

        flags: list[str] = []
        if overview_len < 24:
            score -= 0.12
            flags.append("overview_too_short")
        if information_len < 40:
            score -= 0.18
            flags.append("information_note_too_short")
        if len(key_points) == 0:
            score -= 0.18
            flags.append("key_points_empty")
        if source_type.startswith("subtitle") and len(evidence) == 0:
            score -= 0.11
            flags.append("subtitle_missing_evidence")
        if source_type == "description":
            if sentence_count < self._description_min_sentences:
                score -= 0.22
                flags.append("description_sentence_sparse")
            if text_len < 160:
                score -= 0.25
                flags.append("description_too_short")
            if len(key_points) < 2:
                score -= 0.12
                flags.append("description_keypoints_sparse")
            if len(evidence) < 1:
                score -= 0.10
                flags.append("description_missing_evidence")
        if url_ratio > 0.16:
            score -= min(0.24, (url_ratio - 0.16) * 1.2)
            flags.append("url_density_high")
        if hashtag_count >= 10:
            score -= min(0.16, (hashtag_count - 9) * 0.01)
            flags.append("hashtag_density_high")
        if unique_ratio < 0.18:
            score -= 0.08
            flags.append("lexical_diversity_low")
        if confidence < 0.28:
            score -= 0.06
            flags.append("confidence_low")

        bounded_score = round(max(0.0, min(1.0, score)), 3)
        min_quality = self._subtitle_auto_min_quality
        if source_type == "subtitle_manual":
            min_quality = self._subtitle_manual_min_quality
        elif source_type == "description":
            min_quality = self._description_min_quality

        critical_reasons: list[tuple[str, str]] = []
        if information_len < 40:
            critical_reasons.append(("information_note_too_short", "提炼信息过短，缺少可复用内容"))
        if len(key_points) < 1:
            critical_reasons.append(("key_points_empty", "缺少可复用的关键信息要点"))
        if source_type.startswith("subtitle") and len(evidence) < 1:
            critical_reasons.append(("subtitle_missing_evidence", "字幕摘要缺少证据片段"))
        if source_type == "description" and sentence_count < self._description_min_sentences:
            critical_reasons.append(("description_sentence_sparse", "描述文本句子过少，缺少可提炼信息"))
        if source_type == "description" and text_len < 160:
            critical_reasons.append(("description_too_short", "描述文本过短，信息密度不足"))
        if source_type == "description" and len(evidence) < 1:
            critical_reasons.append(("description_missing_evidence", "缺少可引用证据片段"))
        if url_ratio > 0.28:
            critical_reasons.append(("url_density_high", "文本以链接为主，缺乏可用语义"))
        if bounded_score < min_quality:
            critical_reasons.append(("quality_score_low", f"质量评分 {bounded_score:.2f} 低于门禁 {min_quality:.2f}"))

        if critical_reasons:
            flag, reason = critical_reasons[0]
            if flag not in flags:
                flags.append(flag)
            return {
                "score": bounded_score,
                "usable": False,
                "needs_review": True,
                "reason": reason,
                "flags": flags,
            }

        return {
            "score": bounded_score,
            "usable": True,
            "needs_review": False,
            "reason": "quality_gate_passed",
            "flags": flags,
        }

    def _normalize_text(self, text: str) -> str:
        out = str(text or "").replace("\r", "\n")
        out = re.sub(r"\n{3,}", "\n\n", out)
        out = "\n".join(line.strip() for line in out.splitlines())
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()

    def _normalize_string_list(self, raw: Any, *, max_items: int) -> list[str]:
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            text = str(item or "").strip()
            if not text:
                continue
            normalized = text[:240]
            if self._is_low_signal_fragment(normalized):
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(normalized)
            if len(out) >= max_items:
                break
        return out

    def _split_sentences(self, text: str) -> list[str]:
        rows = re.split(r"[。！？!?;\n]+", text or "")
        out: list[str] = []
        seen: set[str] = set()
        for row in rows:
            clean = row.strip()
            if len(clean) < 8:
                continue
            compact = _MULTISPACE_RE.sub(" ", clean)[:180]
            key = compact.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(compact)
            if len(out) >= 10:
                break
        return out

    def _extract_first_json_object(self, raw: str) -> dict[str, Any]:
        text = str(raw or "")
        if not text:
            return {}
        start = text.find("{")
        if start < 0:
            return {}
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    snippet = text[start : idx + 1]
                    try:
                        parsed = json.loads(snippet)
                        return parsed if isinstance(parsed, dict) else {}
                    except Exception:
                        return {}
        return {}
