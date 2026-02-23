from __future__ import annotations

import html
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

from app.services.asr_text import ASRTextProcessor
from app.services.media_ingest_constants import (
    _BRACE_TAG_RE,
    _CHROME_UA,
    _DEFAULT_LANGUAGE_PREFERENCES,
    _DOUYIN_AUTH_COOKIE_NAMES,
    _DOUYIN_NOISE_FRAGMENT_RE,
    _HASHTAG_RE,
    _HTML_TAG_RE,
    _MULTISPACE_RE,
    _PLATFORM_RULES,
    _PROMO_PHRASE_RE,
    _SRT_INDEX_RE,
    _SUBTITLE_EXTENSIONS,
    _TIMECODE_RE,
    _TOKEN_RE,
    _URL_RE,
    _VIDEO_EXTENSIONS,
)
from app.services.llm import LLMService
from app.services.summarizer import RuleBasedSummarizer
from app.settings import settings

_LOG = logging.getLogger(__name__)


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
        self._asr_min_chars = 80
        self._description_min_chars = 80
        self._description_min_sentences = 2
        self._description_min_quality = 0.64
        self._subtitle_auto_min_quality = 0.52
        self._subtitle_manual_min_quality = 0.46
        self._max_model_input_chars = 12000
        self._asr_text_processor = ASRTextProcessor(
            normalize_text=self._normalize_text,
            split_sentences=self._split_sentences,
            is_low_signal_fragment=self._is_low_signal_fragment,
            max_model_input_chars=self._max_model_input_chars,
        )
        self._run_timeout_seconds = 140
        self._cookie_mode = str(getattr(settings, "media_ingest_cookie_mode", "off") or "off").strip().lower()
        self._cookie_browser = str(getattr(settings, "media_ingest_cookie_browser", "chrome") or "chrome").strip()
        self._cookie_browser_profile = str(getattr(settings, "media_ingest_cookie_browser_profile", "") or "").strip()
        self._cookie_file = str(getattr(settings, "media_ingest_cookie_file", "") or "").strip()
        self._proxy_url = str(getattr(settings, "media_ingest_proxy_url", "") or "").strip()
        self._douyin_auto_login_enabled = bool(
            getattr(settings, "media_ingest_douyin_auto_login_enabled", True)
        )
        raw_douyin_profile = str(
            getattr(settings, "media_ingest_douyin_browser_profile_dir", "./browser_data/douyin_media")
            or "./browser_data/douyin_media"
        ).strip()
        self._douyin_browser_profile_arg = raw_douyin_profile.replace("\\", "/")
        self._douyin_browser_profile_dir = self._resolve_runtime_path(raw_douyin_profile)
        self._douyin_cookie_file = self._douyin_browser_profile_dir / "douyin.cookies.txt"
        self._douyin_login_url = str(
            getattr(settings, "media_ingest_douyin_login_url", "https://www.douyin.com/")
            or "https://www.douyin.com/"
        ).strip()
        self._douyin_asr_enabled = bool(
            getattr(settings, "media_ingest_douyin_asr_enabled", True)
        )
        self._douyin_asr_backend = str(
            getattr(settings, "media_ingest_douyin_asr_backend", "auto") or "auto"
        ).strip().lower()
        if self._douyin_asr_backend not in {"auto", "openai", "faster_whisper"}:
            self._douyin_asr_backend = "auto"
        self._douyin_asr_model = str(
            getattr(settings, "media_ingest_douyin_asr_model", "whisper-1") or "whisper-1"
        ).strip()
        self._douyin_asr_local_model = str(
            getattr(settings, "media_ingest_douyin_asr_local_model", "small") or "small"
        ).strip()
        self._douyin_asr_local_device = str(
            getattr(settings, "media_ingest_douyin_asr_local_device", "auto") or "auto"
        ).strip().lower()
        if self._douyin_asr_local_device not in {"auto", "cpu", "cuda"}:
            self._douyin_asr_local_device = "auto"
        self._douyin_asr_local_compute_type = str(
            getattr(settings, "media_ingest_douyin_asr_local_compute_type", "int8") or "int8"
        ).strip()
        self._douyin_asr_local_beam_size = max(
            1,
            min(8, int(getattr(settings, "media_ingest_douyin_asr_local_beam_size", 4) or 4)),
        )
        self._douyin_asr_max_audio_seconds = max(
            30,
            min(360, int(getattr(settings, "media_ingest_douyin_asr_max_audio_seconds", 120) or 120)),
        )
        self._douyin_asr_timeout_seconds = max(
            20,
            min(300, int(getattr(settings, "media_ingest_douyin_asr_timeout_seconds", 80) or 80)),
        )
        self._ffmpeg_command = self._resolve_ffmpeg_command()
        self._douyin_asr_openai_available = True
        self._faster_whisper_model: Any | None = None
        self._faster_whisper_failed = False

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
        metadata = self._fetch_metadata(ytdlp_cmd=ytdlp_cmd, url=canonical_url, platform=platform)
        title = str(metadata.get("title") or "").strip()[:220] or f"{platform} content"
        description = str(metadata.get("description") or "").strip()
        prefer_platform_text = (
            platform == "douyin" and str(metadata.get("_aelin_extractor") or "") == "playwright_fallback"
        )

        extracted_text, source_type, source_language = self._extract_best_text(
            ytdlp_cmd=ytdlp_cmd,
            url=canonical_url,
            description=description,
            language_preferences=language_preferences,
            platform=platform,
            prefer_platform_text=prefer_platform_text,
            video_url=str(metadata.get("_aelin_video_url") or ""),
            service=service,
            provider=provider,
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
        if source_type == "douyin_api":
            limitations.append("当前基于抖音页面/API抓取文本生成，非官方字幕逐字稿。")
        if source_type == "subtitle_asr":
            limitations.append("当前字幕由 ASR 转写生成，可能存在听写误差。")
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

    def _resolve_runtime_path(self, raw: str) -> Path:
        path = Path(str(raw or "").strip() or ".").expanduser()
        if path.is_absolute():
            return path
        backend_dir = Path(__file__).resolve().parents[2]
        return (backend_dir / path).resolve()

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

    def _resolve_ffmpeg_command(self) -> str:
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            return ffmpeg_bin
        try:
            import imageio_ffmpeg  # type: ignore

            candidate = str(imageio_ffmpeg.get_ffmpeg_exe() or "").strip()
            if candidate and Path(candidate).exists():
                return candidate
        except Exception:
            pass
        return ""

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
            or "could not find chromium cookies database" in text
            or "could not extract cookies from browser" in text
        )

    def _build_network_args(self, *, platform: str = "") -> list[str]:
        out: list[str] = []
        platform_norm = str(platform or "").strip().lower()
        mode = self._cookie_mode
        use_douyin_profile = (
            platform_norm == "douyin"
            and self._douyin_auto_login_enabled
            and mode != "file"
        )
        if use_douyin_profile:
            if self._douyin_cookie_file.exists():
                out.extend(["--cookies", str(self._douyin_cookie_file)])
            else:
                self._douyin_browser_profile_dir.mkdir(parents=True, exist_ok=True)
                out.extend(["--cookies-from-browser", f"chromium:{self._douyin_browser_profile_arg}"])
        elif mode == "browser" and self._cookie_browser:
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
        if (
            "could not copy chrome cookie database" in lowered
            or "could not find edge cookies database" in lowered
            or "could not find chromium cookies database" in lowered
        ):
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

    def build_douyin_auth_guidance(
        self,
        *,
        wait_seconds: int = 180,
        open_url: str = "",
        force_relogin: bool = False,
    ) -> dict[str, Any]:
        safe_wait = max(30, min(900, int(wait_seconds or 180)))
        login_url = open_url.strip() if open_url.strip() else self._douyin_login_url
        return {
            "platform": "douyin",
            "supported": bool(self._douyin_auto_login_enabled),
            "login_url": login_url,
            "wait_seconds": safe_wait,
            "force_relogin": bool(force_relogin),
            "profile_dir": str(self._douyin_browser_profile_dir),
            "cookie_file": str(self._douyin_cookie_file),
            "next_step": "POST /api/v1/aelin/media/auth/douyin/guide 启动引导登录，再重试 /api/v1/aelin/media/ingest",
        }

    def run_douyin_login_guide(
        self,
        *,
        wait_seconds: int = 180,
        open_url: str = "",
        force_relogin: bool = False,
    ) -> dict[str, Any]:
        if not self._douyin_auto_login_enabled:
            raise MediaIngestError("auth_guide_disabled", "当前环境已关闭抖音自动登录引导。")

        safe_wait = max(30, min(900, int(wait_seconds or 180)))
        login_url = open_url.strip() if open_url.strip() else self._douyin_login_url
        profile_dir = self._douyin_browser_profile_dir
        if bool(force_relogin):
            try:
                if profile_dir.exists():
                    shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception as exc:
                _LOG.warning("failed to cleanup douyin profile dir: %s", exc)
            try:
                if self._douyin_cookie_file.exists():
                    self._douyin_cookie_file.unlink(missing_ok=True)
            except Exception as exc:
                _LOG.warning("failed to cleanup douyin cookie file: %s", exc)
        profile_dir.mkdir(parents=True, exist_ok=True)

        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:
            raise MediaIngestError(
                "auth_guide_unavailable",
                "当前环境不可用 Playwright 浏览器，请先执行 `playwright install chromium`。",
            ) from exc

        cookie_count = 0
        cookie_rows: list[dict[str, Any]] = []
        success = False
        message = "未检测到新的登录态，请确认是否已完成扫码/验证码登录。"

        try:
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
                    deadline = time.time() + safe_wait
                    while time.time() < deadline:
                        cookies = context.cookies("https://www.douyin.com/")
                        cookie_count = len(cookies)
                        if cookies:
                            cookie_rows = [dict(item) for item in cookies]
                        if self._has_douyin_auth_cookie(cookie_rows):
                            success = True
                            message = "已检测到抖音登录态，接下来会自动重试抓取。"
                            break
                        time.sleep(2.0)
                finally:
                    context.close()
        except MediaIngestError:
            raise
        except Exception as exc:
            raise MediaIngestError("auth_guide_failed", f"抖音登录引导失败: {str(exc)[:140]}") from exc

        cookie_file_written = False
        if success and cookie_rows:
            try:
                self._write_netscape_cookie_file(path=self._douyin_cookie_file, cookies=cookie_rows)
                cookie_file_written = self._douyin_cookie_file.exists()
            except Exception as exc:
                _LOG.warning("failed to write douyin cookie file: %s", exc)

        return {
            "ok": success,
            "platform": "douyin",
            "login_url": login_url,
            "force_relogin": bool(force_relogin),
            "profile_dir": str(profile_dir),
            "cookie_file": str(self._douyin_cookie_file),
            "cookie_file_written": bool(cookie_file_written),
            "wait_seconds": safe_wait,
            "cookie_count": cookie_count,
            "message": message,
        }

    def _has_douyin_auth_cookie(self, cookies: list[dict[str, Any]]) -> bool:
        if not cookies:
            return False
        names = {str(item.get("name") or "").strip().lower() for item in cookies}
        return any(name in names for name in _DOUYIN_AUTH_COOKIE_NAMES)

    def _write_netscape_cookie_file(self, *, path: Path, cookies: list[dict[str, Any]]) -> None:
        lines = [
            "# Netscape HTTP Cookie File",
            "# Generated by Aelin Douyin login guide",
        ]
        for item in cookies:
            domain = str(item.get("domain") or "").strip()
            name = str(item.get("name") or "").strip()
            value = str(item.get("value") or "")
            if not domain or not name:
                continue
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            path_value = str(item.get("path") or "/").strip() or "/"
            secure = "TRUE" if bool(item.get("secure")) else "FALSE"
            expires_raw = item.get("expires")
            try:
                expires = int(float(expires_raw)) if expires_raw is not None else 0
            except Exception:
                expires = 0
            lines.append(
                f"{domain}\t{include_subdomains}\t{path_value}\t{secure}\t{expires}\t{name}\t{value}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _fetch_metadata(self, *, ytdlp_cmd: list[str], url: str, platform: str) -> dict[str, Any]:
        if platform == "douyin":
            fallback_metadata = self._fetch_douyin_metadata_with_playwright(url=url)
            if fallback_metadata:
                _LOG.info("douyin metadata fetched via playwright first")
                return fallback_metadata

        network_args = self._build_network_args(platform=platform)
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
            if platform == "douyin":
                fallback_metadata = self._fetch_douyin_metadata_with_playwright(url=url)
                if fallback_metadata:
                    _LOG.info("douyin metadata fallback applied: playwright")
                    return fallback_metadata
            raise MediaIngestError(code, msg)
        payload = self._extract_first_json_object(proc.stdout or "")
        if not payload:
            payload = self._extract_first_json_object(proc.stderr or "")
        if not payload:
            if platform == "douyin":
                fallback_metadata = self._fetch_douyin_metadata_with_playwright(url=url)
                if fallback_metadata:
                    _LOG.info("douyin metadata fallback applied after empty yt-dlp payload")
                    return fallback_metadata
            code, msg = self._classify_ytdlp_error(stderr=(proc.stderr or ""), stdout=(proc.stdout or ""))
            raise MediaIngestError(code, msg if msg else "未获取到可解析的媒体元数据")
        entries = payload.get("entries")
        if isinstance(entries, list) and entries:
            first_entry = entries[0]
            if isinstance(first_entry, dict):
                return first_entry
        return payload

    def _fetch_douyin_metadata_with_playwright(self, *, url: str) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:
            _LOG.warning("playwright unavailable for douyin fallback: %s", exc)
            return {}

        profile_dir = self._douyin_browser_profile_dir
        profile_dir.mkdir(parents=True, exist_ok=True)

        aweme_detail: dict[str, Any] = {}
        render_payload: dict[str, Any] = {}
        page_title = ""
        page_snapshot: dict[str, Any] = {}
        comment_samples: list[str] = []
        try:
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()

                    def _on_response(response: Any) -> None:
                        nonlocal aweme_detail, comment_samples
                        response_url = str(getattr(response, "url", "") or "")
                        try:
                            payload = response.json()
                        except Exception:
                            return
                        if not isinstance(payload, dict):
                            return
                        if "aweme/v1/web/aweme/detail" in response_url:
                            detail = payload.get("aweme_detail")
                            if isinstance(detail, dict):
                                aweme_detail = detail
                            return
                        if "aweme/v1/web/comment/list" in response_url:
                            rows = payload.get("comments")
                            if not isinstance(rows, list):
                                return
                            seen = {item.lower() for item in comment_samples}
                            for row in rows:
                                if not isinstance(row, dict):
                                    continue
                                text = self._normalize_paragraph(str(row.get("text") or ""), max_len=140)
                                if not text:
                                    continue
                                key = text.lower()
                                if key in seen:
                                    continue
                                seen.add(key)
                                comment_samples.append(text)
                                if len(comment_samples) >= 20:
                                    break

                    page.on("response", _on_response)
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3500)
                    page_title = str(page.title() or "").strip()
                    try:
                        snapshot = page.evaluate(
                            """() => {
                                const read = (selector, attr = 'content') => {
                                    const node = document.querySelector(selector);
                                    if (!node) return '';
                                    const value = node.getAttribute(attr) || node.textContent || '';
                                    return String(value || '').trim();
                                };
                                const bodyText = document.body ? (document.body.innerText || '') : '';
                                return {
                                    og_title: read("meta[property='og:title']"),
                                    og_description: read("meta[property='og:description']"),
                                    meta_description: read("meta[name='description']"),
                                    body_preview: String(bodyText || '').slice(0, 2200),
                                };
                            }"""
                        )
                        if isinstance(snapshot, dict):
                            page_snapshot = snapshot
                    except Exception:
                        page_snapshot = {}
                    if not aweme_detail:
                        render_payload = self._extract_douyin_render_payload(page=page)
                    if not comment_samples:
                        try:
                            body_preview = self._normalize_paragraph(
                                str(page.evaluate("() => (document.body && document.body.innerText) || ''") or ""),
                                max_len=2200,
                            )
                        except Exception:
                            body_preview = ""
                        if body_preview:
                            for line in body_preview.split(" "):
                                snippet = self._normalize_paragraph(line, max_len=90)
                                if snippet and snippet not in comment_samples:
                                    comment_samples.append(snippet)
                                if len(comment_samples) >= 12:
                                    break
                finally:
                    context.close()
        except Exception as exc:
            _LOG.warning("douyin playwright fallback failed: %s", exc)
            return {}

        if not aweme_detail and render_payload:
            aweme_detail = self._find_first_aweme_dict(render_payload) or {}

        fallback = self._build_douyin_fallback_metadata(
            url=url,
            aweme_detail=aweme_detail,
            page_title=page_title,
            page_snapshot=page_snapshot,
            comment_samples=comment_samples,
        )
        return fallback

    def _extract_douyin_render_payload(self, *, page: Any) -> dict[str, Any]:
        selectors = [
            "script[id='RENDER_DATA']",
            "script#__UNIVERSAL_DATA_FOR_REHYDRATION__",
            "script#__NEXT_DATA__",
        ]
        for selector in selectors:
            try:
                node = page.query_selector(selector)
            except Exception:
                node = None
            if node is None:
                continue
            try:
                raw = str(node.inner_text() or "")
            except Exception:
                raw = ""
            parsed = self._parse_maybe_encoded_json(raw)
            if parsed:
                return parsed
        return {}

    def _parse_maybe_encoded_json(self, raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        decoded = html.unescape(text)
        candidates = [decoded]
        if "%" in decoded:
            try:
                unquoted = unquote(decoded)
            except Exception:
                unquoted = decoded
            if unquoted != decoded:
                candidates.insert(0, unquoted)
        for item in candidates:
            snippet = str(item or "").strip()
            if not snippet:
                continue
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                parsed = self._extract_first_json_object(snippet)
                if parsed:
                    return parsed
        return {}

    def _find_first_aweme_dict(self, payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            if "aweme_id" in payload and any(
                key in payload for key in ("desc", "author", "statistics", "video")
            ):
                return payload
            for key in ("aweme_detail", "awemeInfo", "aweme_info", "aweme"):
                node = payload.get(key)
                if isinstance(node, (dict, list)):
                    found = self._find_first_aweme_dict(node)
                    if found:
                        return found
            for node in payload.values():
                if isinstance(node, (dict, list)):
                    found = self._find_first_aweme_dict(node)
                    if found:
                        return found
            return None
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, (dict, list)):
                    found = self._find_first_aweme_dict(item)
                    if found:
                        return found
        return None

    def _build_douyin_fallback_metadata(
        self,
        *,
        url: str,
        aweme_detail: dict[str, Any],
        page_title: str,
        page_snapshot: dict[str, Any],
        comment_samples: list[str],
    ) -> dict[str, Any]:
        title = self._normalize_paragraph(str(aweme_detail.get("desc") or ""), max_len=220)
        if not title and isinstance(page_snapshot, dict):
            title = self._normalize_paragraph(str(page_snapshot.get("og_title") or ""), max_len=220)
        if not title and page_title:
            title = self._normalize_paragraph(page_title, max_len=220)
        if not title:
            title = "Douyin content"

        description_parts: list[str] = []
        if aweme_detail:
            desc = self._normalize_paragraph(str(aweme_detail.get("desc") or ""), max_len=900)
            if desc:
                description_parts.append(f"内容描述：{desc}")

            author = aweme_detail.get("author")
            if isinstance(author, dict):
                nickname = self._normalize_paragraph(str(author.get("nickname") or ""), max_len=60)
                signature = self._normalize_paragraph(str(author.get("signature") or ""), max_len=160)
                if nickname or signature:
                    description_parts.append(f"作者信息：昵称={nickname or 'unknown'}；简介={signature or 'unknown'}")

            stats = aweme_detail.get("statistics")
            if isinstance(stats, dict):
                stat_bits: list[str] = []
                for key, label in (
                    ("digg_count", "点赞"),
                    ("comment_count", "评论"),
                    ("share_count", "分享"),
                    ("collect_count", "收藏"),
                ):
                    value = self._format_social_count(stats.get(key))
                    if value:
                        stat_bits.append(f"{label}{value}")
                if stat_bits:
                    description_parts.append("互动数据：" + "，".join(stat_bits))

            text_extra = aweme_detail.get("text_extra")
            if isinstance(text_extra, list):
                tags: list[str] = []
                for item in text_extra:
                    if not isinstance(item, dict):
                        continue
                    tag = str(item.get("hashtag_name") or "").strip()
                    if tag and tag not in tags:
                        tags.append(tag)
                    if len(tags) >= 8:
                        break
                if tags:
                    description_parts.append("话题标签：" + "、".join(tags))

        if isinstance(page_snapshot, dict):
            for key, label, max_len in (
                ("og_description", "页面摘要", 420),
                ("meta_description", "页面描述", 420),
                ("body_preview", "页面正文片段", 860),
            ):
                raw_value = str(page_snapshot.get(key) or "")
                if key == "body_preview":
                    raw_value = self._sanitize_douyin_body_preview(raw_value)
                value = self._normalize_paragraph(raw_value, max_len=max_len)
                if value:
                    description_parts.append(f"{label}：{value}")

        if page_title:
            page_title_clean = self._normalize_paragraph(page_title, max_len=220)
            if page_title_clean and page_title_clean not in description_parts:
                description_parts.append(f"页面标题：{page_title_clean}")
        if comment_samples:
            comment_line = "；".join(comment_samples[:6])
            comment_line = self._normalize_paragraph(comment_line, max_len=600)
            if comment_line:
                description_parts.append(f"评论/弹幕摘录：{comment_line}")

        description_parts.append(f"来源链接：{url}")
        description = self._sanitize_description_text("\n".join(description_parts))
        if len(description) < self._description_min_chars:
            return {}
        video_url = self._extract_douyin_video_url(aweme_detail)
        return {
            "title": title,
            "description": description,
            "_aelin_extractor": "playwright_fallback",
            "_aelin_video_url": video_url,
        }

    def _format_social_count(self, raw: Any) -> str:
        try:
            value = int(float(raw))
        except Exception:
            return ""
        if value < 0:
            return ""
        if value >= 100000000:
            return f"{value / 100000000:.1f}亿"
        if value >= 10000:
            return f"{value / 10000:.1f}万"
        return str(value)

    def _extract_douyin_video_url(self, aweme_detail: dict[str, Any]) -> str:
        if not isinstance(aweme_detail, dict):
            return ""
        video = aweme_detail.get("video")
        if not isinstance(video, dict):
            return ""
        for key in ("play_addr", "play_addr_h264", "download_addr"):
            node = video.get(key)
            if not isinstance(node, dict):
                continue
            url_list = node.get("url_list")
            if isinstance(url_list, list):
                for item in url_list:
                    url = str(item or "").strip()
                    if url.startswith("http"):
                        return url
        return ""

    def _sanitize_douyin_body_preview(self, text: str) -> str:
        raw = self._normalize_text(text).replace("\n", " ")
        if not raw:
            return ""
        segments = re.split(r"[。！？!?；;\n]+|\s{2,}", raw)
        kept: list[str] = []
        seen: set[str] = set()
        total_len = 0
        for segment in segments:
            denoised = _DOUYIN_NOISE_FRAGMENT_RE.sub(" ", str(segment or ""))
            cleaned = self._normalize_paragraph(denoised, max_len=140)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            if self._is_douyin_noise_fragment(cleaned):
                continue
            seen.add(lowered)
            kept.append(cleaned)
            total_len += len(cleaned)
            if total_len >= 760 or len(kept) >= 8:
                break
        return "。".join(kept)

    def _is_douyin_noise_fragment(self, text: str) -> bool:
        snippet = self._normalize_paragraph(text, max_len=160)
        if not snippet:
            return True
        if _DOUYIN_NOISE_FRAGMENT_RE.search(snippet):
            return True
        digits = sum(ch.isdigit() for ch in snippet)
        if digits > 0 and (digits / max(1, len(snippet))) > 0.35:
            return True
        return False

    def _extract_best_text(
        self,
        *,
        ytdlp_cmd: list[str],
        url: str,
        description: str,
        language_preferences: list[str],
        platform: str,
        prefer_platform_text: bool = False,
        video_url: str = "",
        service: LLMService | None = None,
        provider: str = "rule_based",
    ) -> tuple[str, str, str]:
        fallback_desc = self._sanitize_description_text(description)
        if prefer_platform_text and len(fallback_desc) >= self._description_min_chars:
            asr_text = self._transcribe_douyin_audio(
                video_url=video_url,
                page_url=url,
                ytdlp_cmd=ytdlp_cmd,
                service=service,
                provider=provider,
            )
            if len(asr_text) >= self._subtitle_min_chars:
                return asr_text, "subtitle_asr", "zh"
            return fallback_desc, "douyin_api", "zh"

        subtitle_lang_expr = ",".join(language_preferences)

        manual_text, manual_lang = self._extract_subtitles(
            ytdlp_cmd=ytdlp_cmd,
            url=url,
            subtitle_lang_expr=subtitle_lang_expr,
            auto_sub=False,
            language_preferences=language_preferences,
            platform=platform,
        )
        if manual_text:
            return manual_text, "subtitle_manual", manual_lang

        auto_text, auto_lang = self._extract_subtitles(
            ytdlp_cmd=ytdlp_cmd,
            url=url,
            subtitle_lang_expr=subtitle_lang_expr,
            auto_sub=True,
            language_preferences=language_preferences,
            platform=platform,
        )
        if auto_text:
            return auto_text, "subtitle_auto", auto_lang

        if len(fallback_desc) >= self._description_min_chars:
            return fallback_desc, "description", "unknown"
        raise MediaIngestError("no_extractable_content", "未提取到可用字幕或足够描述文本")

    def _transcribe_douyin_audio(
        self,
        *,
        video_url: str,
        page_url: str = "",
        ytdlp_cmd: list[str] | None = None,
        service: LLMService | None,
        provider: str,
    ) -> str:
        if not self._douyin_asr_enabled:
            return ""
        source_url = str(video_url or "").strip()
        ffmpeg_cmd = str(self._ffmpeg_command or "").strip() or self._resolve_ffmpeg_command()
        if not ffmpeg_cmd:
            _LOG.warning("douyin asr skipped: ffmpeg not found")
            return ""
        self._ffmpeg_command = ffmpeg_cmd

        with tempfile.TemporaryDirectory(prefix="aelin-douyin-asr-") as tmpdir:
            audio_path = Path(tmpdir) / "douyin_audio.mp3"
            extracted = False
            if source_url.startswith("http"):
                extracted = self._extract_audio_for_asr(
                    ffmpeg_cmd=ffmpeg_cmd,
                    source_url=source_url,
                    audio_path=audio_path,
                    add_headers=True,
                )
            if not extracted and ytdlp_cmd and str(page_url or "").startswith("http"):
                downloaded_video = self._download_douyin_video_for_asr(
                    ytdlp_cmd=ytdlp_cmd,
                    page_url=page_url,
                    workdir=Path(tmpdir),
                )
                if downloaded_video is not None:
                    extracted = self._extract_audio_for_asr(
                        ffmpeg_cmd=ffmpeg_cmd,
                        source_url=str(downloaded_video),
                        audio_path=audio_path,
                        add_headers=False,
                    )
            if not extracted:
                return ""
            for backend in self._resolve_douyin_asr_backend_order():
                text = ""
                if backend == "faster_whisper":
                    text = self._transcribe_douyin_audio_with_faster_whisper(audio_path=audio_path)
                elif backend == "openai":
                    text = self._transcribe_douyin_audio_with_openai(
                        audio_path=audio_path,
                        service=service,
                        provider=provider,
                    )
                if text:
                    return text[: self._max_model_input_chars]
        return ""

    def _resolve_douyin_asr_backend_order(self) -> list[str]:
        mode = self._douyin_asr_backend
        if mode == "openai":
            return ["openai"] if self._douyin_asr_openai_available else []
        if mode == "faster_whisper":
            return ["faster_whisper"]
        out = ["faster_whisper"]
        if self._douyin_asr_openai_available:
            out.append("openai")
        return out

    def _download_douyin_video_for_asr(self, *, ytdlp_cmd: list[str], page_url: str, workdir: Path) -> Path | None:
        args = [
            "--no-playlist",
            "--no-warnings",
            "--format",
            "bv*+ba/best",
            "--output",
            "aelin_douyin_asr.%(ext)s",
        ]
        network_args = self._build_network_args(platform="douyin")
        proc = self._run_ytdlp(
            ytdlp_cmd=ytdlp_cmd,
            args=args,
            url=page_url,
            cwd=workdir,
            network_args=network_args,
        )
        if proc.returncode != 0 and network_args and self._is_cookie_bootstrap_error(proc.stderr or "", proc.stdout or ""):
            proc = self._run_ytdlp(
                ytdlp_cmd=ytdlp_cmd,
                args=args,
                url=page_url,
                cwd=workdir,
                network_args=[],
            )
        if proc.returncode != 0:
            return None
        candidates = [
            path
            for path in workdir.glob("aelin_douyin_asr.*")
            if path.is_file() and path.suffix.lower() in _VIDEO_EXTENSIONS and path.stat().st_size >= 20 * 1024
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item.stat().st_size, reverse=True)[0]

    def _extract_audio_for_asr(
        self,
        *,
        ffmpeg_cmd: str,
        source_url: str,
        audio_path: Path,
        add_headers: bool = True,
    ) -> bool:
        cmd = [
            ffmpeg_cmd,
            "-y",
            "-loglevel",
            "error",
        ]
        if add_headers:
            cmd.extend(
                [
                    "-headers",
                    f"User-Agent: {_CHROME_UA}\r\nReferer: https://www.douyin.com/\r\n",
                ]
            )
        cmd.extend(
            [
                "-i",
                source_url,
                "-t",
                str(self._douyin_asr_max_audio_seconds),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "mp3",
                str(audio_path),
            ]
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._douyin_asr_timeout_seconds,
                encoding="utf-8",
                errors="ignore",
            )
        except Exception as exc:
            _LOG.warning("douyin asr ffmpeg failed: %s", exc)
            return False
        return proc.returncode == 0 and audio_path.exists() and audio_path.stat().st_size >= 4096

    def _resolve_faster_whisper_device(self) -> str:
        if self._douyin_asr_local_device in {"cpu", "cuda"}:
            return self._douyin_asr_local_device
        if shutil.which("nvidia-smi"):
            return "cuda"
        return "cpu"

    def _get_faster_whisper_model(self) -> Any | None:
        if self._faster_whisper_model is not None:
            return self._faster_whisper_model
        if self._faster_whisper_failed:
            return None
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:
            _LOG.warning("douyin asr faster-whisper unavailable: %s", exc)
            self._faster_whisper_failed = True
            return None
        device = self._resolve_faster_whisper_device()
        try:
            self._faster_whisper_model = WhisperModel(
                self._douyin_asr_local_model,
                device=device,
                compute_type=self._douyin_asr_local_compute_type,
            )
        except Exception as exc:
            if device == "cuda":
                try:
                    self._faster_whisper_model = WhisperModel(
                        self._douyin_asr_local_model,
                        device="cpu",
                        compute_type=self._douyin_asr_local_compute_type,
                    )
                    return self._faster_whisper_model
                except Exception:
                    pass
            _LOG.warning("douyin asr faster-whisper init failed: %s", exc)
            self._faster_whisper_failed = True
            return None
        return self._faster_whisper_model

    def _transcribe_douyin_audio_with_faster_whisper(self, *, audio_path: Path) -> str:
        model = self._get_faster_whisper_model()
        if model is None:
            return ""
        try:
            segments, _info = model.transcribe(
                str(audio_path),
                language="zh",
                beam_size=self._douyin_asr_local_beam_size,
                vad_filter=True,
            )
            parts: list[str] = []
            total = 0
            for segment in segments:
                snippet = self._normalize_paragraph(str(getattr(segment, "text", "") or ""), max_len=220)
                if not snippet:
                    continue
                parts.append(snippet)
                total += len(snippet)
                if total >= self._max_model_input_chars:
                    break
            text = self._sanitize_asr_text(" ".join(parts))
            if len(text) < self._asr_min_chars or self._asr_noise_score(text) >= 0.58:
                return ""
            return text[: self._max_model_input_chars]
        except Exception as exc:
            _LOG.warning("douyin asr faster-whisper transcription failed: %s", exc)
            return ""

    def _transcribe_douyin_audio_with_openai(
        self,
        *,
        audio_path: Path,
        service: LLMService | None,
        provider: str,
    ) -> str:
        if not self._douyin_asr_openai_available:
            return ""
        if provider == "rule_based" or service is None or not service.is_configured():
            return ""
        client = getattr(service, "client", None)
        if client is None:
            return ""
        try:
            with audio_path.open("rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=self._douyin_asr_model,
                    file=audio_file,
                    language="zh",
                )
        except Exception as exc:
            err = str(exc)
            if "404" in err or "not found" in err.lower():
                _LOG.warning("douyin asr transcription endpoint unsupported, disabling openai-asr: %s", exc)
                self._douyin_asr_openai_available = False
            else:
                _LOG.warning("douyin asr transcription failed: %s", exc)
            return ""
        text = self._sanitize_asr_text(str(getattr(transcript, "text", "") or ""))
        if len(text) < self._asr_min_chars or self._asr_noise_score(text) >= 0.58:
            return ""
        return text[: self._max_model_input_chars]

    def _extract_subtitles(
        self,
        *,
        ytdlp_cmd: list[str],
        url: str,
        subtitle_lang_expr: str,
        auto_sub: bool,
        language_preferences: list[str],
        platform: str,
    ) -> tuple[str, str]:
        network_args = self._build_network_args(platform=platform)
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
            proc = self._run_ytdlp(
                ytdlp_cmd=ytdlp_cmd,
                args=args,
                url=url,
                cwd=workdir,
                network_args=network_args,
            )
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
                "若 source_type=subtitle_asr，先去掉口语重复和疑似识别噪声，再输出。"
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
        confidence = 0.46
        if source_type == "subtitle_manual":
            confidence = 0.74
        elif source_type == "subtitle_auto":
            confidence = 0.65
        elif source_type == "douyin_api":
            confidence = 0.68
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
            "douyin_api": 0.74,
            "subtitle_asr": 0.7,
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
        if source_type == "douyin_api":
            value = min(value, 0.78)
        if source_type == "subtitle_asr":
            value = min(value, 0.76)
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

    def _sanitize_asr_text(self, text: str) -> str:
        return self._asr_text_processor.sanitize(text)

    def _asr_noise_score(self, text: str) -> float:
        return self._asr_text_processor.noise_score(text)

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
        asr_noise = self._asr_noise_score(text) if source_type == "subtitle_asr" else 0.0

        source_base = {
            "subtitle_manual": 0.42,
            "subtitle_auto": 0.34,
            "description": 0.18,
            "douyin_api": 0.29,
            "subtitle_asr": 0.32,
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
        if source_type == "subtitle_asr" and asr_noise >= 0.42:
            score -= min(0.22, asr_noise * 0.25)
            flags.append("asr_noise_high")

        bounded_score = round(max(0.0, min(1.0, score)), 3)
        min_quality = self._subtitle_auto_min_quality
        if source_type == "subtitle_manual":
            min_quality = self._subtitle_manual_min_quality
        elif source_type == "description":
            min_quality = self._description_min_quality
        elif source_type == "douyin_api":
            min_quality = 0.56
        elif source_type == "subtitle_asr":
            min_quality = 0.52

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
        if source_type == "douyin_api" and text_len < 220:
            critical_reasons.append(("douyin_api_text_short", "抖音页面文本过短，信息密度不足"))
        if source_type == "douyin_api" and len(evidence) < 1:
            critical_reasons.append(("douyin_api_evidence_sparse", "抖音抓取文本缺少可引用证据"))
        if source_type == "subtitle_asr" and asr_noise >= 0.6:
            critical_reasons.append(("asr_noise_high", "ASR 转写噪声较高，当前文本不稳定"))
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
