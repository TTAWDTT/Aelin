from __future__ import annotations

from typing import Any

from urllib.parse import urlparse

from app.services.media_ingest_constants import _PLATFORM_RULES


def detect_platform(url: str) -> str:
    """
    Detect supported media platform from URL.

    This is a thin wrapper around `_PLATFORM_RULES` so that platform rules
    can evolve independently from the main MediaIngestService class.
    """
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


def build_limitations(source_type: str, quality: dict[str, Any] | None = None) -> list[str]:
    """
    Normalize the standard limitations note list based on the text source type.

    Kept close to platform rules so that changes to source_type semantics
    remain local. This mirrors the previous `_build_limitations` helper.
    """
    limitations = ["摘要主要基于字幕/文本，不覆盖纯视觉镜头语义。"]
    if source_type == "description":
        limitations.append("当前未提取到字幕，改用描述文本生成，置信度较低。")
    if source_type == "douyin_api":
        limitations.append("当前基于抖音页面/API抓取文本生成，非官方字幕逐字稿。")
    if source_type == "subtitle_asr":
        limitations.append("当前字幕由 ASR 转写生成，可能存在听写误差。")
    if source_type == "subtitle_auto":
        limitations.append("当前使用自动字幕，可能存在识别误差。")
    if quality is not None:
        usable = bool(quality.get("usable", True))
        reason = str(quality.get("reason") or "").strip()
        if not usable:
            gate_reason = reason or "质量评分未通过门禁阈值"
            limitations.append(f"质量门禁未通过：{gate_reason}")
    return limitations
