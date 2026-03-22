from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.services.media_ingest_constants import (
    _CHROME_UA,
    _DOUYIN_AUTH_COOKIE_NAMES,
    _DOUYIN_NOISE_FRAGMENT_RE,
)
from app.settings import settings

_LOG = logging.getLogger(__name__)


class DouyinConfig:
    """
    Lightweight container for Douyin-specific configuration.

    This keeps MediaIngestService.__init__ slimmer and makes it easier to
    reason about which settings are truly Douyin-specific.
    """

    def __init__(self) -> None:
        self.auto_login_enabled = bool(
            getattr(settings, "media_ingest_douyin_auto_login_enabled", True)
        )
        raw_profile = str(
            getattr(settings, "media_ingest_douyin_browser_profile_dir", "./browser_data/douyin_media")
            or "./browser_data/douyin_media"
        ).strip()
        self.browser_profile_arg = raw_profile.replace("\\", "/")
        self.browser_profile_dir_raw = raw_profile
        self.login_url = str(
            getattr(settings, "media_ingest_douyin_login_url", "https://www.douyin.com/")
            or "https://www.douyin.com/"
        ).strip()
        self.asr_enabled = bool(
            getattr(settings, "media_ingest_douyin_asr_enabled", True)
        )
        self.asr_backend = str(
            getattr(settings, "media_ingest_douyin_asr_backend", "auto") or "auto"
        ).strip().lower()
        self.asr_model = str(
            getattr(settings, "media_ingest_douyin_asr_model", "whisper-1") or "whisper-1"
        ).strip()
        self.asr_local_model = str(
            getattr(settings, "media_ingest_douyin_asr_local_model", "small") or "small"
        ).strip()
        self.asr_local_device = str(
            getattr(settings, "media_ingest_douyin_asr_local_device", "auto") or "auto"
        ).strip().lower()
        if self.asr_local_device not in {"auto", "cpu", "cuda"}:
            self.asr_local_device = "auto"
        self.asr_local_compute_type = str(
            getattr(settings, "media_ingest_douyin_asr_local_compute_type", "int8") or "int8"
        ).strip()
        self.asr_local_beam_size = max(
            1,
            min(8, int(getattr(settings, "media_ingest_douyin_asr_local_beam_size", 4) or 4)),
        )
        self.asr_max_audio_seconds = max(
            30,
            min(360, int(getattr(settings, "media_ingest_douyin_asr_max_audio_seconds", 120) or 120)),
        )
        self.asr_timeout_seconds = max(
            20,
            min(300, int(getattr(settings, "media_ingest_douyin_asr_timeout_seconds", 80) or 80)),
        )


def resolve_douyin_paths(runtime_root: Path, cfg: DouyinConfig) -> tuple[Path, Path]:
    """
    Resolve Douyin browser profile dir and cookie file path under the backend runtime.
    """
    if Path(cfg.browser_profile_dir_raw).is_absolute():
        profile_dir = Path(cfg.browser_profile_dir_raw)
    else:
        profile_dir = (runtime_root / cfg.browser_profile_dir_raw).resolve()
    cookie_file = profile_dir / "douyin.cookies.txt"
    return profile_dir, cookie_file


def has_douyin_auth_cookie(cookies: list[dict[str, Any]]) -> bool:
    """
    Check if cookie rows contain any of the known Douyin auth cookie names.
    """
    auth_names = _DOUYIN_AUTH_COOKIE_NAMES
    for row in cookies:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if name in auth_names:
            return True
    return False


def sanitize_douyin_body_preview(text: str) -> str:
    """
    Lightweight text sanitizer for Douyin body preview, mirroring the original
    `_sanitize_douyin_body_preview` helper.
    """
    raw = str(text or "")
    if not raw:
        return ""
    cleaned = _DOUYIN_NOISE_FRAGMENT_RE.sub(" ", raw)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()[:600]

