from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont


_LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_POSTER_WIDTH = 1200
_POSTER_HEIGHT = 1800
_MARGIN_X = 92
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FONT_ROOT = _REPO_ROOT / "backend" / "deepagents_skills" / "anthropic-canvas-design" / "canvas-fonts"


@dataclass(frozen=True)
class VisualArtifact:
    path: str
    relative_path: str
    name: str
    mime_type: str
    size_bytes: int
    preview_kind: str
    content: str
    created_at: str
    modified_at: str


@dataclass(frozen=True)
class PosterRenderResult:
    summary: str
    artifacts: list[VisualArtifact]
    file_paths: list[str]
    title: str
    format: str


@dataclass(frozen=True)
class PosterCopy:
    title_lines: list[str]
    eyebrow: str
    english_line: str
    detail_line: str
    accent_line: str
    filename_stem: str


def _safe_slug(text: str) -> str:
    ascii_text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return ascii_text[:64] or "visual-poster"


def _looks_like_data_url(value: str) -> bool:
    return str(value or "").startswith("data:")


def _pick_font(candidates: list[Path | str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in candidates:
        path = Path(str(candidate))
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _chinese_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _pick_font(
        [
            Path("C:/Windows/Fonts/msyhbd.ttc"),
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("C:/Windows/Fonts/simsun.ttc"),
            _FONT_ROOT / "NotoSansSC-Regular.otf",
        ],
        size,
    )


def _latin_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _pick_font(
        [
            _FONT_ROOT / "Gloock-Regular.ttf",
            _FONT_ROOT / "YoungSerif-Regular.ttf",
            _FONT_ROOT / "InstrumentSans-Regular.ttf",
            Path("C:/Windows/Fonts/georgia.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ],
        size,
    )


def _mono_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _pick_font(
        [
            _FONT_ROOT / "JetBrainsMono-Regular.ttf",
            _FONT_ROOT / "GeistMono-Regular.ttf",
            _FONT_ROOT / "IBMplexMono-Regular.ttf",
            Path("C:/Windows/Fonts/consola.ttf"),
        ],
        size,
    )


def _mix(color_a: tuple[int, int, int], color_b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    clamped = max(0.0, min(1.0, float(t)))
    return tuple(
        int(round(color_a[index] + (color_b[index] - color_a[index]) * clamped))
        for index in range(3)
    )


def _create_background() -> Image.Image:
    image = Image.new("RGBA", (_POSTER_WIDTH, _POSTER_HEIGHT), "#fbf6f2")
    draw = ImageDraw.Draw(image)
    top = (250, 242, 236)
    mid = (248, 228, 235)
    bottom = (241, 246, 239)
    for y in range(_POSTER_HEIGHT):
        progress = y / max(1, _POSTER_HEIGHT - 1)
        if progress < 0.56:
            color = _mix(top, mid, progress / 0.56)
        else:
            color = _mix(mid, bottom, (progress - 0.56) / 0.44)
        draw.line([(0, y), (_POSTER_WIDTH, y)], fill=(*color, 255))
    return image


def _add_blurred_petals(base: Image.Image, rng: Random) -> None:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    petal_palette = [
        (255, 232, 240, 190),
        (244, 202, 220, 180),
        (255, 245, 247, 200),
        (227, 181, 201, 120),
    ]
    clusters = [
        (_POSTER_WIDTH - 250, 260, 16),
        (_POSTER_WIDTH - 150, 520, 12),
        (210, _POSTER_HEIGHT - 280, 10),
    ]
    for center_x, center_y, count in clusters:
        for _ in range(count):
            width = rng.randint(44, 112)
            height = rng.randint(18, 44)
            x = center_x + rng.randint(-210, 170)
            y = center_y + rng.randint(-170, 160)
            angle = math.radians(rng.randint(0, 180))
            dx = math.cos(angle) * width * 0.5
            dy = math.sin(angle) * height * 0.5
            color = petal_palette[rng.randrange(len(petal_palette))]
            draw.ellipse(
                [x - width, y - height, x + width, y + height],
                fill=color,
            )
            highlight_x0 = x - dx - width * 0.28
            highlight_y0 = y - dy - height * 0.28
            highlight_x1 = x + dx
            highlight_y1 = y + dy
            draw.ellipse(
                [
                    min(highlight_x0, highlight_x1),
                    min(highlight_y0, highlight_y1),
                    max(highlight_x0, highlight_x1),
                    max(highlight_y0, highlight_y1),
                ],
                fill=(255, 255, 255, 95),
            )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=18))
    base.alpha_composite(overlay)


def _add_linework(base: Image.Image) -> None:
    draw = ImageDraw.Draw(base)
    rose = (188, 132, 152, 92)
    ink = (52, 47, 50, 42)
    draw.rounded_rectangle(
        [_MARGIN_X - 26, 60, _POSTER_WIDTH - _MARGIN_X + 26, _POSTER_HEIGHT - 60],
        radius=34,
        outline=ink,
        width=2,
    )
    draw.line(
        [(_POSTER_WIDTH - 272, 172), (_POSTER_WIDTH - 130, 172)],
        fill=rose,
        width=3,
    )
    draw.arc(
        [(_POSTER_WIDTH - 360), 118, (_POSTER_WIDTH - 112), 366],
        start=196,
        end=336,
        fill=rose,
        width=3,
    )
    for y in (1030, 1080, 1130):
        draw.line(
            [(_POSTER_WIDTH - 368, y), (_POSTER_WIDTH - 116, y)],
            fill=(70, 65, 69, 28),
            width=1,
        )


def _text_box_height(lines: list[str], font: ImageFont.ImageFont, spacing: int) -> int:
    height = 0
    for index, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_height = int(bbox[3] - bbox[1])
        height += line_height
        if index < len(lines) - 1:
            height += spacing
    return height


def _draw_multiline(
    draw: ImageDraw.ImageDraw,
    *,
    lines: list[str],
    font: ImageFont.ImageFont,
    start_x: int,
    start_y: int,
    fill: tuple[int, int, int, int],
    spacing: int,
) -> int:
    y = start_y
    for line in lines:
        draw.text((start_x, y), line, font=font, fill=fill)
        bbox = font.getbbox(line)
        y += int(bbox[3] - bbox[1]) + spacing
    return y - spacing


def _extract_copy(brief: str, filename_stem: str | None = None) -> PosterCopy:
    text = str(brief or "").strip()
    lower = text.lower()

    if "同济大学" in text and "樱花" in text:
        return PosterCopy(
            title_lines=["同济大学", "樱花季", "赏花活动"],
            eyebrow="SPRING CAMPUS EVENT POSTER",
            english_line="TONGJI UNIVERSITY SAKURA SEASON",
            detail_line="Bloom Walk / Campus Spring Gathering",
            accent_line="Pure composition, blossom rhythm, quiet precision",
            filename_stem=filename_stem or "tongji-sakura-season-poster",
        )

    chinese_fragments = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    english_words = re.findall(r"[A-Za-z][A-Za-z0-9&' -]{1,18}", text)
    headline = chinese_fragments[:3] or ["视觉海报", "活动呈现"]
    english_line = " / ".join(word.strip().upper() for word in english_words[:4]) or "VISUAL EVENT POSTER"
    stem = filename_stem or _safe_slug("-".join(chinese_fragments[:2]) or english_line)
    return PosterCopy(
        title_lines=headline[:3],
        eyebrow="ART DIRECTION / EVENT POSTER",
        english_line=english_line,
        detail_line="Composed for clarity, breathing room, and strong focal rhythm",
        accent_line="Refined craft / structured calm / visual hierarchy",
        filename_stem=stem,
    )


def _draw_poster(copy: PosterCopy, *, seed: int) -> Image.Image:
    image = _create_background()
    rng = Random(seed)
    _add_blurred_petals(image, rng)
    _add_linework(image)
    draw = ImageDraw.Draw(image)

    title_font = _chinese_font(168)
    subtitle_font = _latin_font(34)
    detail_font = _latin_font(26)
    mono_font = _mono_font(23)
    micro_font = _mono_font(18)

    ink = (34, 31, 34, 255)
    muted = (86, 80, 85, 218)
    rose = (174, 110, 138, 255)

    title_x = _MARGIN_X
    title_y = 192
    title_spacing = 22
    title_block_height = _text_box_height(copy.title_lines, title_font, title_spacing)

    draw.text((title_x, 120), copy.eyebrow, font=mono_font, fill=rose)
    _draw_multiline(
        draw,
        lines=copy.title_lines,
        font=title_font,
        start_x=title_x,
        start_y=title_y,
        fill=ink,
        spacing=title_spacing,
    )

    body_left = title_x + 8
    body_top = title_y + title_block_height + 74
    draw.text((body_left, body_top), copy.english_line, font=subtitle_font, fill=rose)
    draw.text((body_left, body_top + 62), copy.detail_line, font=detail_font, fill=muted)

    footer_y = _POSTER_HEIGHT - 212
    draw.line(
        [(_MARGIN_X, footer_y - 26), (_POSTER_WIDTH - _MARGIN_X, footer_y - 26)],
        fill=(53, 47, 51, 46),
        width=2,
    )
    draw.text((_MARGIN_X, footer_y + 4), copy.accent_line, font=detail_font, fill=muted)
    draw.text(
        (_POSTER_WIDTH - _MARGIN_X - 250, footer_y + 8),
        "AELIN / STATIC ARTIFACT",
        font=micro_font,
        fill=(73, 67, 72, 164),
    )

    side_label = Image.new("RGBA", (980, 72), (0, 0, 0, 0))
    side_draw = ImageDraw.Draw(side_label)
    side_draw.text(
        (0, 0),
        "TONGJI SAKURA BLOOM / METICULOUSLY COMPOSED",
        font=_mono_font(20),
        fill=(82, 76, 82, 148),
    )
    rotated = side_label.rotate(90, expand=True)
    image.alpha_composite(rotated, (_POSTER_WIDTH - 126, 412))

    return image


def render_poster_artifact(
    *,
    brief: str,
    workspace: str,
    preferred_format: str = "auto",
    filename_stem: str | None = None,
) -> PosterRenderResult:
    clean_brief = " ".join(str(brief or "").split()).strip()
    if not clean_brief:
        raise ValueError("brief is required")

    format_text = str(preferred_format or "auto").strip().lower()
    if format_text not in {"auto", "png", "pdf"}:
        format_text = "auto"
    chosen_format = "png" if format_text == "auto" else format_text

    copy = _extract_copy(clean_brief, filename_stem=filename_stem)
    timestamp = datetime.now(_LOCAL_TZ).strftime("%Y%m%d-%H%M%S")
    seed = int(hashlib.sha256(clean_brief.encode("utf-8")).hexdigest()[:12], 16)
    poster = _draw_poster(copy, seed=seed).convert("RGB")

    output_dir = _REPO_ROOT / "output" / "generated-posters" / _safe_slug(workspace or "default") / f"{timestamp}-{copy.filename_stem}"
    output_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(_LOCAL_TZ).isoformat(timespec="seconds")

    png_path = output_dir / f"{copy.filename_stem}.png"
    poster.save(png_path, format="PNG", optimize=True, compress_level=9)
    pdf_path = output_dir / f"{copy.filename_stem}.pdf"
    poster.save(pdf_path, format="PDF", resolution=240.0)

    file_paths = [str(png_path.resolve()), str(pdf_path.resolve())]
    png_artifact = VisualArtifact(
        path=str(png_path.resolve()),
        relative_path=png_path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix(),
        name=png_path.name,
        mime_type="image/png",
        size_bytes=int(png_path.stat().st_size),
        preview_kind="image-data-url",
        content="",
        created_at=created_at,
        modified_at=created_at,
    )
    pdf_artifact = VisualArtifact(
        path=str(pdf_path.resolve()),
        relative_path=pdf_path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix(),
        name=pdf_path.name,
        mime_type="application/pdf",
        size_bytes=int(pdf_path.stat().st_size),
        preview_kind="pdf-data-url",
        content="",
        created_at=created_at,
        modified_at=created_at,
    )
    artifacts = [png_artifact, pdf_artifact]
    if chosen_format == "pdf":
        artifacts = [pdf_artifact, png_artifact]

    summary = (
        f"Poster ready: {copy.title_lines[0]} / {copy.title_lines[-1]} "
        f"({chosen_format.upper()}) with {len(artifacts)} deliverable artifact(s). "
        "Deliverable is finished; preview/download should use the returned file metadata instead of another read_file step."
    )
    return PosterRenderResult(
        summary=summary,
        artifacts=artifacts,
        file_paths=file_paths,
        title=" / ".join(copy.title_lines),
        format=chosen_format,
    )
