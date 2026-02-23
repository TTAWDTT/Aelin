"""抖音用户视频订阅连接器

策略链（按速度排序）:
1. Playwright 精简模式 — 跳过首页，直达用户页面，拦截 XHR 获取 JSON ~13s
2. RSSHub 镜像 — 轻量回退，适用于自建 RSSHub 实例配置了 DOUYIN_COOKIE 的情况

安装:
    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

import concurrent.futures
import logging
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.connectors.base import IncomingMessage
from app.connectors.douyin_utils import (
    _CHROME_UA,
    _POST_API_PATTERN,
    _RSSHUB_MIRRORS,
    _build_preview_html,
    _extract_sec_uid,
    _to_datetime,
)

from app.connectors.feed import FeedConnector
from app.services.avatar import normalize_http_avatar_url
from app.settings import settings

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import Error as PlaywrightError

    _HAS_PLAYWRIGHT = True
except ImportError:
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightTimeout = TimeoutError  # type: ignore[assignment, misc]
    PlaywrightError = Exception  # type: ignore[assignment, misc]
    _HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)

# =====================================================================
# DouyinConnector
# =====================================================================


class DouyinConnector:
    """抖音用户视频订阅连接器 — Playwright 无头浏览器 + RSSHub 回退"""

    def __init__(
        self,
        *,
        sec_uid: str,
        fallback_feed_url: str | None = None,
        default_sender: str | None = None,
        timeout_seconds: int = 60,
        max_items: int = 50,
        transport: httpx.BaseTransport | None = None,
    ):
        self._sec_uid = _extract_sec_uid(sec_uid)
        self._fallback_feed_url = (fallback_feed_url or "").strip() or None
        self._default_sender = (default_sender or "抖音用户").strip()
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
            user_data_dir = self._resolve_browser_data_dir("douyin")
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=settings.crawler_headless,
                args=launch_args,
                user_agent=_CHROME_UA,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                bypass_csp=True,
            )
            return context, None

        browser = playwright.chromium.launch(
            headless=settings.crawler_headless,
            args=launch_args,
        )
        context = browser.new_context(
            user_agent=_CHROME_UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            bypass_csp=True,
        )
        return context, browser

    # ------------------------------------------------------------------
    # 策略 1: Playwright 精简模式（跳过首页, ~13s）
    # ------------------------------------------------------------------

    def _fetch_via_playwright(
        self, *, since: datetime | None, fresh: bool = False,
    ) -> list[IncomingMessage]:
        """
        精简 Playwright — 直达用户页面拦截 XHR，
        跳过首页访问和随机延迟，~13s 完成。

        当 fresh=True 时，使用干净上下文消除被标记的 cookie。
        """
        if not _HAS_PLAYWRIGHT:
            raise RuntimeError(
                "playwright 未安装。请运行:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        sec_uid = self._sec_uid
        if not sec_uid:
            raise ValueError("缺少有效的 sec_uid")

        url = f"https://www.douyin.com/user/{sec_uid}"
        collected: list[dict[str, Any]] = []
        lock = threading.Lock()

        def _on_response(response: Any) -> None:
            """拦截视频列表 API 响应"""
            try:
                if _POST_API_PATTERN not in response.url:
                    return
                if response.status != 200:
                    return
                body = response.json()
                if isinstance(body, dict) and body.get("aweme_list"):
                    with lock:
                        collected.append(body)
            except Exception:
                pass

        timeout_ms = self._timeout_seconds * 1000

        try:
            with sync_playwright() as pw:
                context, browser = self._create_playwright_context(
                    pw, fresh=fresh
                )
                context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',"
                    "{get:()=>undefined});"
                    "window.chrome={runtime:{}};"
                )

                page = context.pages[0] if context.pages else context.new_page()
                page.on("response", _on_response)

                logger.info("Playwright: 正在打开 %s", url)

                # 直达用户页面，跳过首页访问
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                # 兼容旧版 Playwright：不依赖 wait_for_response，仅使用轮询等待。
                try:
                    if hasattr(page, "wait_for_response"):
                        page.wait_for_response(
                            lambda resp: _POST_API_PATTERN in resp.url and resp.status == 200,  # noqa: E731
                            timeout=min(10_000, timeout_ms),
                        )
                except PlaywrightTimeout:
                    pass

                poll_limit = max(
                    1,
                    min(
                        int(settings.crawler_playwright_poll_seconds),
                        max(1, self._timeout_seconds - 5),
                    ),
                )
                for _ in range(poll_limit):
                    if collected:
                        break
                    page.wait_for_timeout(1000)

                # 如果仍未获取数据，滚动触发一次
                if not collected:
                    page.evaluate("window.scrollTo(0, 600)")
                    page.wait_for_timeout(3000)

                # 回退: 如果拦截未命中，尝试从 RENDER_DATA 提取
                if not collected:
                    logger.debug("Playwright: XHR 拦截未获得数据，尝试 RENDER_DATA")
                    raw = page.evaluate(
                        """() => {
                            const el = document.getElementById('RENDER_DATA');
                            return el ? el.textContent : null;
                        }"""
                    )
                    if raw:
                        try:
                            import urllib.parse as _up
                            render = json.loads(_up.unquote(raw))
                            collected.extend(
                                self._extract_from_render_data(render)
                            )
                        except Exception as exc:
                            logger.debug("RENDER_DATA 解析失败: %s", exc)

                context.close()
                if browser is not None:
                    browser.close()

        except PlaywrightError as exc:
            msg = str(exc)
            if "Executable doesn't exist" in msg or "browserType.launch" in msg:
                raise RuntimeError(
                    "Playwright 浏览器未安装。请运行:\n"
                    "  playwright install chromium"
                ) from exc
            raise

        if not collected:
            raise ValueError(
                "Playwright 未能获取抖音视频数据。"
                "可能原因: 页面需要登录、用户不存在、或网络超时"
            )

        return self._parse_aweme_responses(collected, since=since)

    # ------------------------------------------------------------------
    # Playwright 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_from_render_data(
        render: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        从页面 RENDER_DATA 中提取 aweme_list 格式的数据。
        RENDER_DATA 结构: {<route_key>: {post: {data: [...]}}} (可能变化)
        """
        results: list[dict[str, Any]] = []
        if not isinstance(render, dict):
            return results

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                # 直接找 aweme_list
                if "aweme_list" in obj and isinstance(obj["aweme_list"], list):
                    results.append(obj)
                    return
                # 适配新版 RENDER_DATA 结构
                post = obj.get("post") or obj.get("awemeData")
                if isinstance(post, dict):
                    data = post.get("data") or post.get("aweme_list")
                    if isinstance(data, list) and data:
                        results.append({"aweme_list": data})
                        return
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(render)
        return results

    def _parse_aweme_responses(
        self,
        responses: list[dict[str, Any]],
        *,
        since: datetime | None,
    ) -> list[IncomingMessage]:
        """
        将拦截到的 /aweme/v1/web/aweme/post/ JSON 响应
        转换为 IncomingMessage 列表。
        """
        since_utc = since.astimezone(timezone.utc) if since else None
        seen_ids: set[str] = set()
        messages: list[IncomingMessage] = []

        for resp in responses:
            aweme_list = resp.get("aweme_list") or []
            for aweme in aweme_list:
                if not isinstance(aweme, dict):
                    continue
                aweme_id = str(aweme.get("aweme_id") or "")
                if not aweme_id or aweme_id in seen_ids:
                    continue
                seen_ids.add(aweme_id)

                # 时间
                create_time = aweme.get("create_time")
                received_at = _to_datetime(create_time)
                if since_utc and received_at <= since_utc:
                    continue

                # 标题
                desc = str(aweme.get("desc") or "").strip()
                title = desc or "抖音视频"

                # 作者
                author = aweme.get("author") or {}
                nickname = str(
                    author.get("nickname") or self._default_sender
                ).strip()

                # 头像
                avatar_url: str | None = None
                avatar_info = author.get("avatar_thumb") or author.get(
                    "avatar_medium"
                )
                if isinstance(avatar_info, dict):
                    url_list = avatar_info.get("url_list") or []
                    if url_list:
                        avatar_url = normalize_http_avatar_url(
                            str(url_list[0])
                        )

                # 封面
                cover_url: str | None = None
                video = aweme.get("video") or {}
                cover_info = video.get("origin_cover") or video.get("cover")
                if isinstance(cover_info, dict):
                    cov_list = cover_info.get("url_list") or []
                    if cov_list:
                        cover_url = str(cov_list[0])

                link = f"https://www.douyin.com/video/{aweme_id}"

                messages.append(
                    IncomingMessage(
                        source="douyin",
                        external_id=aweme_id,
                        sender=nickname,
                        subject=title[:998],
                        body=_build_preview_html(
                            title=title[:300],
                            description=desc[:1500],
                            link=link,
                            cover_url=cover_url,
                        ),
                        received_at=received_at,
                        sender_avatar_url=avatar_url,
                    )
                )
                if len(messages) >= self._max_items:
                    return messages

        return messages

    # ------------------------------------------------------------------
    # 策略 2: RSSHub 镜像（回退）
    # ------------------------------------------------------------------

    def _try_rsshub_feed(
        self, *, feed_url: str, since: datetime | None
    ) -> list[IncomingMessage]:
        return FeedConnector(
            feed_url=feed_url,
            source="douyin",
            default_sender=self._default_sender,
            timeout_seconds=min(15, self._timeout_seconds),
            max_entries=self._max_items,
        ).fetch_new_messages(since=since)

    def _collect_rsshub_urls(self) -> list[str]:
        """收集所有可尝试的 RSSHub URL"""
        urls: list[str] = []

        if self._fallback_feed_url:
            effective = self._fallback_feed_url
            if (
                self._sec_uid
                and self._sec_uid.startswith("MS4")
                and "/user/" in effective
            ):
                base = effective.split("/user/")[0]
                effective = f"{base}/user/{self._sec_uid}"
            urls.append(effective)

        sec_uid = self._sec_uid
        if sec_uid:
            seen: set[str] = set()
            for u in urls:
                if "/douyin/user/" in u:
                    seen.add(u.split("/douyin/user/")[0].rstrip("/"))
            for mirror in _RSSHUB_MIRRORS:
                base = mirror.rstrip("/")
                if base not in seen:
                    urls.append(f"{base}/douyin/user/{sec_uid}")
                    seen.add(base)

        return urls

    def _fetch_rsshub_in_parallel(
        self, *, rsshub_urls: list[str], since: datetime | None
    ) -> tuple[list[IncomingMessage] | None, list[str]]:
        if not rsshub_urls:
            return None, []

        parallelism = max(
            1, min(int(settings.crawler_rsshub_parallelism), len(rsshub_urls))
        )
        errors: list[str] = []

        if parallelism == 1:
            for feed_url in rsshub_urls:
                try:
                    messages = self._try_rsshub_feed(feed_url=feed_url, since=since)
                    if messages:
                        return messages, errors
                except Exception as exc:
                    errors.append(f"{feed_url}: {exc}")
            return None, errors

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=parallelism, thread_name_prefix="douyin-rsshub"
        ) as executor:
            future_map = {
                executor.submit(
                    self._try_rsshub_feed, feed_url=feed_url, since=since
                ): feed_url
                for feed_url in rsshub_urls
            }
            for future in concurrent.futures.as_completed(future_map):
                feed_url = future_map[future]
                try:
                    messages = future.result()
                    if messages:
                        return messages, errors
                except Exception as exc:
                    errors.append(f"{feed_url}: {exc}")

        return None, errors

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def fetch_new_messages(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        errors: list[str] = []

        # ── 主策略: Playwright 精简模式（~13s）──
        if _HAS_PLAYWRIGHT:
            try:
                messages = self._fetch_via_playwright(since=since, fresh=False)
                logger.info(
                    "Playwright 成功获取 %d 条抖音消息",
                    len(messages),
                )
                return messages
            except Exception as e:
                errors.append(f"Playwright: {e}")
                logger.warning("Playwright 抖音抓取失败: %s", e)
                if settings.crawler_use_persistent_login:
                    try:
                        messages = self._fetch_via_playwright(since=since, fresh=True)
                        logger.info(
                            "Playwright(Fresh) 成功获取 %d 条抖音消息",
                            len(messages),
                        )
                        return messages
                    except Exception as fresh_error:
                        errors.append(f"Playwright(Fresh): {fresh_error}")
                        logger.warning(
                            "Playwright Fresh 抖音抓取失败: %s", fresh_error
                        )
        else:
            errors.append(
                "playwright 未安装 — pip install playwright && "
                "playwright install chromium"
            )
            logger.warning(
                "playwright 未安装，跳过浏览器策略。"
                "请运行: pip install playwright && playwright install chromium"
            )

        # ── 回退: RSSHub 镜像（并发探测） ──
        rsshub_urls = self._collect_rsshub_urls()
        for i, feed_url in enumerate(rsshub_urls):
            logger.info("加入 RSSHub 并发探测 [%d/%d]: %s", i + 1, len(rsshub_urls), feed_url)
        messages, rsshub_errors = self._fetch_rsshub_in_parallel(
            rsshub_urls=rsshub_urls,
            since=since,
        )
        if messages:
            logger.info("RSSHub 成功 (%d 条消息)", len(messages))
            return messages
        if rsshub_errors:
            for item in rsshub_errors:
                logger.debug("RSSHub 失败: %s", item)

        if rsshub_urls:
            errors.append(
                f"已尝试 {len(rsshub_urls)} 个 RSSHub 镜像均失败"
            )

        raise ValueError(
            "抖音同步失败: " + "; ".join(errors) + "\n\n"
            "推荐解决方案:\n"
            "1. 安装 Playwright: pip install playwright && "
            "playwright install chromium\n"
            "2. 或自建 RSSHub 并配置 DOUYIN_COOKIE 环境变量"
        )
