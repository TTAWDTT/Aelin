"""小红书用户笔记订阅连接器

策略链（按速度排序）:
1. Playwright 精简模式 — 直达用户页面提取 __INITIAL_STATE__ ~8s
2. jina.ai 网页抓取 — 无需浏览器 ~3s（可能被限制）
3. RSSHub 镜像 — 需要自建实例配置 cookie
4. 自定义 RSS 回退
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.connectors.base import IncomingMessage
from app.connectors.feed import FeedConnector
from app.connectors.xiaohongshu_utils import (
    _DEFAULT_USER_AGENT,
    _NOTE_ID_RE,
    _RSSHUB_MIRRORS,
    _build_preview_html,
    _extract_user_id,
)
from app.services.avatar import normalize_http_avatar_url
from app.settings import settings

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import Error as PlaywrightError

    _HAS_PLAYWRIGHT = True
except ImportError:
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightError = Exception  # type: ignore[assignment, misc]
    _HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)

class XiaohongshuConnector:
    """小红书用户笔记订阅连接器 — 多策略链"""

    def __init__(
        self,
        *,
        user_id: str,
        fallback_feed_url: str | None = None,
        default_sender: str | None = None,
        timeout_seconds: int = 60,
        max_items: int = 50,
        transport: httpx.BaseTransport | None = None,
    ):
        self._user_id = _extract_user_id(user_id)
        self._fallback_feed_url = (fallback_feed_url or "").strip() or None
        self._default_sender = (default_sender or "小红书用户").strip()
        self._timeout_seconds = max(10, timeout_seconds)
        self._max_items = max(1, max_items)
        self._transport = transport

    @staticmethod
    def _resolve_browser_data_dir(platform: str) -> str:
        base_dir = Path(settings.crawler_browser_data_dir).expanduser()
        if not base_dir.is_absolute():
            base_dir = Path(__file__).resolve().parents[2] / base_dir
        target = base_dir / platform
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def _create_playwright_context(self, playwright: Any, *, fresh: bool):
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
        if settings.crawler_use_persistent_login and not fresh:
            user_data_dir = self._resolve_browser_data_dir("xiaohongshu")
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=settings.crawler_headless,
                args=launch_args,
                user_agent=_DEFAULT_USER_AGENT,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            return context, None

        browser = playwright.chromium.launch(
            headless=settings.crawler_headless,
            args=launch_args,
        )
        context = browser.new_context(
            user_agent=_DEFAULT_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        return context, browser

    # ------------------------------------------------------------------
    # 策略 1: Playwright 精简模式
    # ------------------------------------------------------------------

    def _fetch_via_playwright(
        self, *, since: datetime | None, fresh: bool = False
    ) -> list[IncomingMessage]:
        """使用 Playwright 打开用户页面，提取 __INITIAL_STATE__ SSR 数据"""
        if not _HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright 未安装")
        if not self._user_id:
            raise ValueError("小红书订阅缺少有效用户 ID")

        url = f"https://www.xiaohongshu.com/user/profile/{self._user_id}"

        try:
            with sync_playwright() as pw:
                ctx, browser = self._create_playwright_context(
                    pw, fresh=fresh
                )
                ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',"
                    "{get:()=>undefined})"
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                logger.info("Playwright 小红书: 正在打开 %s", url)
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout_seconds * 1000,
                )

                initial_state: Any = None
                poll_limit = max(
                    1, min(int(settings.crawler_playwright_poll_seconds), 12)
                )
                for _ in range(poll_limit):
                    initial_state = page.evaluate(
                        """() => {
                            try {
                                return window.__INITIAL_STATE__ || null;
                            } catch(e) { return null; }
                        }"""
                    )
                    if isinstance(initial_state, dict):
                        break
                    page.wait_for_timeout(1000)

                # 回退：页面 HTML 提取 note id
                content = page.content() or ""

                ctx.close()
                if browser is not None:
                    browser.close()

        except PlaywrightError as exc:
            msg = str(exc)
            if "Executable doesn't exist" in msg:
                raise RuntimeError("Playwright 浏览器未安装") from exc
            raise

        since_utc = since.astimezone(timezone.utc) if since else None

        # 尝试从 __INITIAL_STATE__ 解析
        if isinstance(initial_state, dict):
            msgs = self._parse_initial_state(
                initial_state, since_utc=since_utc
            )
            if msgs:
                return msgs

        # 回退：从页面 HTML 提取笔记链接
        return self._parse_page_html(content, since_utc=since_utc)

    def _parse_initial_state(
        self,
        state: dict[str, Any],
        *,
        since_utc: datetime | None,
    ) -> list[IncomingMessage]:
        """解析小红书 __INITIAL_STATE__ 中的笔记数据"""
        messages: list[IncomingMessage] = []
        seen_ids: set[str] = set()

        # 提取用户信息
        user_info = state.get("user", {}).get("userPageData", {})
        nickname = str(
            user_info.get("basicInfo", {}).get("nickname") or ""
        ).strip()
        avatar_url = normalize_http_avatar_url(
            user_info.get("basicInfo", {}).get("imageb")
            or user_info.get("basicInfo", {}).get("images")
        )
        sender = nickname or self._default_sender

        # 提取笔记列表
        notes = state.get("user", {}).get("notes", [])
        if not notes:
            notes = (
                state.get("user", {})
                .get("userPageData", {})
                .get("notes", [])
            )

        for note in notes:
            if not isinstance(note, dict):
                continue
            note_id = str(
                note.get("id") or note.get("noteId") or ""
            ).strip()
            if not note_id or note_id in seen_ids:
                continue
            seen_ids.add(note_id)

            title = str(
                note.get("displayTitle")
                or note.get("title")
                or note.get("desc")
                or ""
            ).strip()
            if not title:
                title = f"{sender} 发布了新笔记"

            cover = normalize_http_avatar_url(
                note.get("cover", {}).get("url")
                if isinstance(note.get("cover"), dict)
                else note.get("cover")
            )

            ts = note.get("time") or note.get("timestamp")
            if isinstance(ts, (int, float)):
                received_at = datetime.fromtimestamp(
                    float(ts) / 1000 if ts > 1e12 else float(ts),
                    tz=timezone.utc,
                )
            else:
                received_at = datetime.now(timezone.utc)

            if since_utc and received_at <= since_utc:
                continue

            link = f"https://www.xiaohongshu.com/explore/{note_id}"

            messages.append(
                IncomingMessage(
                    source="xiaohongshu",
                    external_id=note_id,
                    sender=sender,
                    subject=title[:998],
                    body=_build_preview_html(
                        title=title,
                        description=title,
                        link=link,
                        cover_url=cover,
                    ),
                    received_at=received_at,
                    sender_avatar_url=avatar_url,
                )
            )
            if len(messages) >= self._max_items:
                break

        return messages

    def _parse_page_html(
        self,
        html: str,
        *,
        since_utc: datetime | None,
    ) -> list[IncomingMessage]:
        """从页面 HTML 中提取笔记链接"""
        name_match = re.search(
            r'class="user-name[^"]*"[^>]*>([^<]+)', html
        )
        sender = (
            name_match.group(1).strip()
            if name_match
            else self._default_sender
        )

        avatar_match = re.search(
            r'(https?://[^\s"\']+(?:avatar|user)[^\s"\']*'
            r'\.(?:jpeg|jpg|png|webp)[^\s"\']*)',
            html,
            re.IGNORECASE,
        )
        avatar = (
            normalize_http_avatar_url(avatar_match.group(1))
            if avatar_match
            else None
        )

        note_ids = list(dict.fromkeys(_NOTE_ID_RE.findall(html)))
        messages: list[IncomingMessage] = []

        for note_id in note_ids:
            link = f"https://www.xiaohongshu.com/explore/{note_id}"
            title = f"{sender} 发布了新笔记"
            messages.append(
                IncomingMessage(
                    source="xiaohongshu",
                    external_id=note_id,
                    sender=sender,
                    subject=title[:998],
                    body=_build_preview_html(
                        title=title,
                        description="",
                        link=link,
                        cover_url=None,
                    ),
                    received_at=datetime.now(timezone.utc),
                    sender_avatar_url=avatar,
                )
            )
            if len(messages) >= self._max_items:
                break

        return messages

    # ------------------------------------------------------------------
    # 策略 2: jina.ai（可能被限制）
    # ------------------------------------------------------------------

    def _fetch_via_jina(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        """通过 jina.ai 抓取用户笔记列表"""
        if not self._user_id:
            raise ValueError("小红书订阅缺少有效用户 ID")

        with httpx.Client(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
            transport=self._transport,
        ) as client:
            url = (
                "https://r.jina.ai/https://www.xiaohongshu.com"
                f"/user/profile/{self._user_id}"
            )
            response = client.get(
                url,
                headers={
                    "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8"
                },
            )
            response.raise_for_status()
            body = response.text or ""

            if not body or len(body) < 100:
                raise ValueError("jina.ai 返回空内容")

            avatar_match = re.search(
                r"(https?://[^\s)\"']+(?:avatar|user)"
                r"[^\s)\"']*\.(?:jpeg|jpg|png|webp)[^\s)\"']*)",
                body,
                re.IGNORECASE,
            )
            avatar = (
                normalize_http_avatar_url(avatar_match.group(1))
                if avatar_match
                else None
            )

            name_match = re.search(
                r"#\s*(.+?)\s*(?:的小红书|的主页|\n|$)", body
            )
            sender = (
                name_match.group(1).strip()
                if name_match
                else self._default_sender
            )

            note_pattern = re.compile(
                r"\[([^\]]+)\]\(https://www\.xiaohongshu\.com"
                r"/explore/([a-f0-9]+)[^\)]*\)",
                re.IGNORECASE,
            )

            messages: list[IncomingMessage] = []
            seen_ids: set[str] = set()

            for match in note_pattern.finditer(body):
                title = match.group(1).strip()
                note_id = match.group(2)

                if note_id in seen_ids:
                    continue
                seen_ids.add(note_id)

                link = f"https://www.xiaohongshu.com/explore/{note_id}"
                messages.append(
                    IncomingMessage(
                        source="xiaohongshu",
                        external_id=note_id,
                        sender=sender,
                        subject=(
                            title[:998] or f"{sender} 发布了新笔记"
                        ),
                        body=_build_preview_html(
                            title=title or f"{sender} 发布了新笔记",
                            description=title,
                            link=link,
                            cover_url=None,
                        ),
                        received_at=datetime.now(timezone.utc),
                        sender_avatar_url=avatar,
                    )
                )
                if len(messages) >= self._max_items:
                    break

            return messages

    # ------------------------------------------------------------------
    # 策略 3: RSSHub 镜像
    # ------------------------------------------------------------------

    def _try_rsshub(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        urls: list[str] = []
        if self._fallback_feed_url:
            urls.append(self._fallback_feed_url)
        for mirror in _RSSHUB_MIRRORS:
            url = f"{mirror.rstrip('/')}/xiaohongshu/user/{self._user_id}"
            if url not in urls:
                urls.append(url)

        parallelism = max(1, min(int(settings.crawler_rsshub_parallelism), len(urls)))
        errors: list[str] = []

        def _fetch(url: str) -> list[IncomingMessage]:
            return FeedConnector(
                feed_url=url,
                source="xiaohongshu",
                default_sender=self._default_sender,
                timeout_seconds=min(15, self._timeout_seconds),
                max_entries=self._max_items,
            ).fetch_new_messages(since=since)

        if parallelism == 1:
            for feed_url in urls:
                try:
                    msgs = _fetch(feed_url)
                    if msgs:
                        return msgs
                except Exception as exc:
                    errors.append(f"{feed_url}: {exc}")
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=parallelism, thread_name_prefix="xhs-rsshub"
            ) as executor:
                future_map = {
                    executor.submit(_fetch, feed_url): feed_url for feed_url in urls
                }
                for future in concurrent.futures.as_completed(future_map):
                    feed_url = future_map[future]
                    try:
                        msgs = future.result()
                        if msgs:
                            return msgs
                    except Exception as exc:
                        errors.append(f"{feed_url}: {exc}")

        if errors:
            for item in errors:
                logger.debug("RSSHub 失败: %s", item)
            raise ValueError("所有 RSSHub 镜像均失败")
        raise ValueError("没有可用的 RSSHub 镜像 URL")

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def fetch_new_messages(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        errors: list[str] = []

        # ── 主策略: Playwright 精简模式 ──
        if _HAS_PLAYWRIGHT:
            try:
                t0 = time.monotonic()
                messages = self._fetch_via_playwright(since=since, fresh=False)
                elapsed = time.monotonic() - t0
                logger.info(
                    "Playwright 成功获取 %d 条小红书消息 (%.2fs)",
                    len(messages),
                    elapsed,
                )
                return messages
            except Exception as e:
                errors.append(f"Playwright: {e}")
                logger.debug("Playwright 小红书失败: %s", e)
                if settings.crawler_use_persistent_login:
                    try:
                        t0 = time.monotonic()
                        messages = self._fetch_via_playwright(
                            since=since, fresh=True
                        )
                        elapsed = time.monotonic() - t0
                        logger.info(
                            "Playwright(Fresh) 成功获取 %d 条小红书消息 (%.2fs)",
                            len(messages),
                            elapsed,
                        )
                        return messages
                    except Exception as fresh_error:
                        errors.append(f"Playwright(Fresh): {fresh_error}")
                        logger.debug(
                            "Playwright Fresh 小红书失败: %s", fresh_error
                        )

        # ── 回退 1: jina.ai ──
        try:
            messages = self._fetch_via_jina(since=since)
            if messages:
                logger.info(
                    "jina.ai 成功获取 %d 条小红书消息", len(messages)
                )
                return messages
        except Exception as e:
            errors.append(f"jina.ai: {e}")
            logger.debug("jina.ai 小红书失败: %s", e)

        # ── 回退 2: RSSHub ──
        try:
            messages = self._try_rsshub(since=since)
            if messages:
                logger.info(
                    "RSSHub 成功获取 %d 条小红书消息", len(messages)
                )
                return messages
        except Exception as e:
            errors.append(f"RSSHub: {e}")
            logger.debug("RSSHub 小红书失败: %s", e)

        # ── 回退 3: 自定义 RSS ──
        if self._fallback_feed_url:
            try:
                messages = FeedConnector(
                    feed_url=self._fallback_feed_url,
                    source="xiaohongshu",
                    default_sender=self._default_sender,
                    timeout_seconds=self._timeout_seconds,
                    max_entries=self._max_items,
                ).fetch_new_messages(since=since)
                if messages:
                    return messages
            except Exception as e:
                errors.append(f"RSS fallback: {e}")

        raise ValueError("小红书同步失败: " + "; ".join(errors))
