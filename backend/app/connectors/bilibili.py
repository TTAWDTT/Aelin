"""B站用户视频订阅连接器

策略链（按速度排序）:
1. recArchivesByKeywords API — 无需签名/cookies，~1 秒（主策略）
2. 纯 HTTP + WBI 签名 API — 需 buvid cookies，~0.3 秒（可能被风控）
3. jina.ai 网页抓取 + API 查详情 — 无需浏览器，~3 秒
4. RSSHub 镜像 — ~1 秒但公共镜像经常不可用
5. Playwright 无头浏览器 — ~30 秒，最后回退
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.connectors.base import IncomingMessage
from app.connectors.bilibili_utils import (
    _BVID_RE,
    _DEFAULT_USER_AGENT,
    _FACE_URL_RE,
    _RSSHUB_MIRRORS,
    _build_preview_html,
    _extract_uid,
    _to_datetime,
    _unique_bvids,
    _wbi_sign,
)
from app.connectors.feed import FeedConnector
from app.services.avatar import normalize_http_avatar_url

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import Error as PlaywrightError

    _HAS_PLAYWRIGHT = True
except ImportError:
    sync_playwright = None  # type: ignore[assignment]
    PlaywrightError = Exception  # type: ignore[assignment, misc]
    _HAS_PLAYWRIGHT = False

logger = logging.getLogger(__name__)

# =====================================================================
# BilibiliConnector
# =====================================================================


class BilibiliConnector:
    """B站用户视频订阅 — 纯 HTTP + WBI 签名（极速主策略）"""

    def __init__(
        self,
        *,
        uid: str,
        fallback_feed_url: str | None = None,
        default_sender: str | None = None,
        timeout_seconds: int = 20,
        max_items: int = 80,
        transport: httpx.BaseTransport | None = None,
    ):
        self._uid = _extract_uid(uid)
        self._fallback_feed_url = (fallback_feed_url or "").strip() or None
        self._default_sender = (
            (default_sender or f"B站 UP {self._uid or ''}").strip()
            or "Bilibili"
        )
        self._timeout_seconds = max(5, timeout_seconds)
        self._max_items = max(1, max_items)
        self._transport = transport

    # ------------------------------------------------------------------
    # 核心: 纯 HTTP WBI 签名 API（极速 ~0.3s）
    # ------------------------------------------------------------------

    def _fetch_via_wbi_api(
        self,
        *,
        since: datetime | None,
        client: httpx.Client | None = None,
    ) -> list[IncomingMessage]:
        """
        纯 HTTP 方案：
        1. 调用 nav API 获取 WBI keys（~0.1s）
        2. WBI 签名后调用 wbi/arc/search（~0.1s）
        3. 解析 vlist 数据并返回消息列表

        全程无需浏览器，总计约 0.3 秒。
        """
        if not self._uid:
            raise ValueError("Bilibili 订阅缺少有效 UID")

        own_client = client is None
        if own_client:
            client = httpx.Client(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": _DEFAULT_USER_AGENT},
                transport=self._transport,
            )

        try:
            return self._do_wbi_fetch(client=client, since=since)
        finally:
            if own_client:
                client.close()

    def _do_wbi_fetch(
        self,
        *,
        client: httpx.Client,
        since: datetime | None,
    ) -> list[IncomingMessage]:
        """执行实际的 WBI API 调用"""
        space_ref = f"https://space.bilibili.com/{self._uid}/"

        # 0. 获取 buvid cookies（通过 SPI 接口，无需浏览器）
        try:
            spi_resp = client.get(
                "https://api.bilibili.com/x/frontend/finger/spi"
            )
            spi_data = spi_resp.json().get("data", {})
            b3 = spi_data.get("b_3", "")
            b4 = spi_data.get("b_4", "")
            if b3:
                client.cookies.set("buvid3", b3, domain=".bilibili.com")
            if b4:
                client.cookies.set("buvid4", b4, domain=".bilibili.com")
        except Exception as e:
            logger.debug("获取 buvid cookies 失败: %s", e)

        # 1. 获取 WBI keys（nav API 即使未登录也会返回 wbi_img）
        nav_resp = client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={"Referer": "https://www.bilibili.com/"},
        )
        nav_data = nav_resp.json()
        wbi_img = nav_data.get("data", {}).get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        img_key = (
            img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
        )
        sub_key = (
            sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
        )
        if not img_key or not sub_key:
            raise ValueError("无法获取 WBI keys")

        # 2. WBI 签名后调用搜索 API
        params = _wbi_sign(
            {"mid": self._uid, "ps": "30", "pn": "1", "order": "pubdate"},
            img_key,
            sub_key,
        )
        resp = client.get(
            "https://api.bilibili.com/x/space/wbi/arc/search",
            params=params,
            headers={"Referer": space_ref},
        )
        data = resp.json()
        code = data.get("code", -1)
        if code != 0:
            raise ValueError(
                f"WBI API code={code}, msg={data.get('message', '')}"
            )

        vlist = data.get("data", {}).get("list", {}).get("vlist", [])
        if not vlist:
            return []

        since_utc = since.astimezone(timezone.utc) if since else None

        # 3. 获取 UP 主信息
        avatar, up_name = self._fetch_user_info(client=client)

        return self._parse_vlist(
            vlist,
            since_utc=since_utc,
            fallback_avatar=avatar,
            fallback_name=up_name,
        )

    # ------------------------------------------------------------------
    # 核心: recArchivesByKeywords API（极速 ~1s，无需签名/cookies）
    # ------------------------------------------------------------------

    def _fetch_via_rec_api(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        """
        使用 recArchivesByKeywords API 获取 UP 主最新视频。
        此 API 无需 WBI 签名、无需 cookies、无需浏览器。
        单次请求 ~1 秒即可获取 30 条视频。
        """
        if not self._uid:
            raise ValueError("Bilibili 订阅缺少有效 UID")

        with httpx.Client(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
            transport=self._transport,
        ) as client:
            resp = client.get(
                "https://api.bilibili.com/x/series/recArchivesByKeywords",
                params={"mid": self._uid, "keywords": "", "ps": "30"},
                headers={
                    "Referer": f"https://space.bilibili.com/{self._uid}/",
                },
            )
            data = resp.json()
            code = data.get("code", -1)
            if code != 0:
                raise ValueError(
                    f"recArchivesByKeywords code={code}, "
                    f"msg={data.get('message', '')}"
                )

            archives = data.get("data", {}).get("archives") or []
            if not archives:
                raise ValueError("recArchivesByKeywords 返回空列表")

            # 转换为 vlist 兼容格式供 _parse_vlist 使用
            vlist = []
            for a in archives:
                vlist.append(
                    {
                        "bvid": a.get("bvid"),
                        "title": a.get("title"),
                        "created": a.get("pubdate"),
                        "description": a.get("desc", ""),
                        "pic": a.get("pic"),
                        "author": None,
                    }
                )

            # 获取 UP 主信息（昵称/头像），单次请求 ~0.1s
            avatar, up_name = self._fetch_user_info(client=client)

            since_utc = (
                since.astimezone(timezone.utc) if since else None
            )
            return self._parse_vlist(
                vlist,
                since_utc=since_utc,
                fallback_avatar=avatar,
                fallback_name=up_name,
            )

    # ------------------------------------------------------------------
    # 用户信息
    # ------------------------------------------------------------------

    def _fetch_user_info(
        self, *, client: httpx.Client
    ) -> tuple[str | None, str | None]:
        """通过 B 站 API 获取用户头像和昵称"""
        if not self._uid:
            return None, None
        endpoints = [
            (
                "https://api.bilibili.com/x/web-interface/card",
                {"mid": self._uid, "photo": "true"},
            ),
        ]
        for url, params in endpoints:
            try:
                response = client.get(
                    url,
                    params=params,
                    headers={
                        "Referer": f"https://space.bilibili.com/{self._uid}/"
                    },
                )
                if response.status_code != 200:
                    continue
                payload = response.json()
                if (
                    not isinstance(payload, dict)
                    or payload.get("code") != 0
                ):
                    continue
                data = payload.get("data")
                if not isinstance(data, dict):
                    continue
                card = data.get("card")
                if isinstance(card, dict):
                    avatar = normalize_http_avatar_url(card.get("face"))
                    name = (
                        str(card.get("name") or "").strip() or None
                    )
                    if avatar:
                        return avatar, name
            except Exception:
                continue
        return None, None

    # ------------------------------------------------------------------
    # vlist 解析（供 WBI API 和 Playwright 共用）
    # ------------------------------------------------------------------

    def _parse_vlist(
        self,
        vlist: list[dict[str, Any]],
        *,
        since_utc: datetime | None,
        fallback_avatar: str | None = None,
        fallback_name: str | None = None,
    ) -> list[IncomingMessage]:
        """将 vlist 格式数据解析为 IncomingMessage 列表"""
        messages: list[IncomingMessage] = []
        seen: set[str] = set()

        for v in vlist:
            bvid = str(v.get("bvid") or "").strip()
            if not bvid or bvid in seen:
                continue
            seen.add(bvid)

            received_at = _to_datetime(v.get("created"))
            if since_utc is not None and received_at <= since_utc:
                continue

            title = str(
                v.get("title") or f"B站更新 {bvid}"
            ).strip()
            description = str(v.get("description") or "").strip()
            if not description:
                description = f"UP 主发布了新视频：{title}"
            link = f"https://www.bilibili.com/video/{bvid}/"
            cover = normalize_http_avatar_url(v.get("pic"))
            sender = (
                str(
                    v.get("author")
                    or fallback_name
                    or self._default_sender
                ).strip()
                or self._default_sender
            )

            messages.append(
                IncomingMessage(
                    source="bilibili",
                    external_id=bvid,
                    sender=sender,
                    subject=title[:998],
                    body=_build_preview_html(
                        title=title,
                        description=description[:1500],
                        link=link,
                        cover_url=cover,
                    ),
                    received_at=received_at,
                    sender_avatar_url=fallback_avatar,
                )
            )
            if len(messages) >= self._max_items:
                break
        return messages

    # ------------------------------------------------------------------
    # RSSHub 回退
    # ------------------------------------------------------------------

    def _try_rsshub_feed(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        """尝试通过 RSSHub 获取视频列表"""
        urls: list[str] = []
        if self._fallback_feed_url:
            urls.append(self._fallback_feed_url)
        for mirror in _RSSHUB_MIRRORS:
            url = f"{mirror.rstrip('/')}/bilibili/user/video/{self._uid}"
            if url not in urls:
                urls.append(url)

        last_error: Exception | None = None
        for feed_url in urls:
            try:
                msgs = FeedConnector(
                    feed_url=feed_url,
                    source="bilibili",
                    default_sender=self._default_sender,
                    timeout_seconds=min(15, self._timeout_seconds),
                    max_entries=self._max_items,
                ).fetch_new_messages(since=since)
                if msgs:
                    return msgs
            except Exception as e:
                last_error = e
                logger.debug("RSSHub 失败 [%s]: %s", feed_url, e)
                continue

        if last_error:
            raise last_error
        raise ValueError("所有 RSSHub 镜像均失败")

    # ------------------------------------------------------------------
    # jina.ai + BV 号查详情 回退
    # ------------------------------------------------------------------

    def _discover_bvids(
        self, *, client: httpx.Client
    ) -> tuple[list[str], str | None]:
        if not self._uid:
            raise ValueError("Bilibili 订阅缺少有效 UID")

        candidate_urls = [
            f"https://r.jina.ai/http://space.bilibili.com/{self._uid}/video",
            f"https://r.jina.ai/http://space.bilibili.com/{self._uid}/dynamic",
        ]
        for url in candidate_urls:
            try:
                response = client.get(
                    url,
                    headers={
                        "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8"
                    },
                )
                response.raise_for_status()
            except Exception:
                continue
            body = response.text or ""
            bvids = _unique_bvids(_BVID_RE.findall(body))
            face_match = _FACE_URL_RE.search(body)
            fallback_avatar = (
                normalize_http_avatar_url(face_match.group(1))
                if face_match
                else None
            )
            if bvids:
                return bvids, fallback_avatar

        raise ValueError("未能从 B 站页面解析到视频列表")

    def _fetch_video_detail(
        self, *, client: httpx.Client, bvid: str
    ) -> dict[str, Any] | None:
        try:
            response = client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                headers={
                    "Referer": f"https://www.bilibili.com/video/{bvid}/"
                },
            )
            response.raise_for_status()
        except Exception:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("code") != 0:
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    def _fetch_video_details_for_bvids(
        self,
        bvids: list[str],
        *,
        since_utc: datetime | None,
        fallback_avatar: str | None = None,
    ) -> list[IncomingMessage]:
        """通过 BV 号列表获取视频详情并构建消息"""
        with httpx.Client(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
            transport=self._transport,
        ) as client:
            api_avatar, api_name = self._fetch_user_info(client=client)
            primary_avatar = api_avatar or fallback_avatar

            messages: list[IncomingMessage] = []
            for bvid in bvids:
                detail = self._fetch_video_detail(
                    client=client, bvid=bvid
                )
                if not detail:
                    continue

                owner = (
                    detail.get("owner")
                    if isinstance(detail.get("owner"), dict)
                    else {}
                )
                owner_face = normalize_http_avatar_url(owner.get("face"))
                if not primary_avatar and owner_face:
                    primary_avatar = owner_face

                received_at = _to_datetime(detail.get("pubdate"))
                if since_utc is not None and received_at <= since_utc:
                    continue

                title = str(
                    detail.get("title") or f"B站更新 {bvid}"
                ).strip()
                description = str(detail.get("desc") or "").strip()
                if not description:
                    description = f"UP 主发布了新视频：{title}"
                link = f"https://www.bilibili.com/video/{bvid}/"
                cover = normalize_http_avatar_url(detail.get("pic"))
                sender = (
                    str(
                        owner.get("name")
                        or api_name
                        or self._default_sender
                    ).strip()
                    or self._default_sender
                )

                messages.append(
                    IncomingMessage(
                        source="bilibili",
                        external_id=bvid,
                        sender=sender,
                        subject=title[:998],
                        body=_build_preview_html(
                            title=title,
                            description=description[:1500],
                            link=link,
                            cover_url=cover,
                        ),
                        received_at=received_at,
                        sender_avatar_url=owner_face or primary_avatar,
                    )
                )
                if len(messages) >= self._max_items:
                    break
            return messages

    # ------------------------------------------------------------------
    # Playwright 浏览器回退（最后手段）
    # ------------------------------------------------------------------

    def _fetch_via_playwright(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        """Playwright 无头浏览器回退 — 仅在所有 HTTP 方案失败时使用"""
        if not _HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright 未安装")
        if not self._uid:
            raise ValueError("Bilibili 订阅缺少有效 UID")

        import threading

        url = f"https://space.bilibili.com/{self._uid}/video"
        api_video_list: list[dict[str, Any]] = []
        lock = threading.Lock()

        def _on_response(response: Any) -> None:
            try:
                resp_url = response.url
                if "arc/search" in resp_url and response.status == 200:
                    body = response.json()
                    if isinstance(body, dict) and body.get("code") == 0:
                        vlist = (
                            body.get("data", {})
                            .get("list", {})
                            .get("vlist", [])
                        )
                        if vlist:
                            with lock:
                                api_video_list.extend(vlist)
            except Exception:
                pass

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
                ctx = browser.new_context(
                    user_agent=_DEFAULT_USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )
                ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',"
                    "{get:()=>undefined})"
                )
                page = ctx.new_page()
                page.on("response", _on_response)

                logger.info("Playwright 回退: 正在打开 %s", url)
                page.goto(
                    url, wait_until="domcontentloaded", timeout=30000
                )
                page.wait_for_timeout(5000)
                page.evaluate("window.scrollTo(0, 600)")
                page.wait_for_timeout(3000)

                # 提取页面 BV 号
                page_bvids: list[str] = []
                fallback_avatar: str | None = None
                try:
                    content = page.content()
                    page_bvids = _unique_bvids(
                        _BVID_RE.findall(content)
                    )
                    face_match = _FACE_URL_RE.search(content)
                    if face_match:
                        fallback_avatar = normalize_http_avatar_url(
                            face_match.group(1)
                        )
                except Exception:
                    pass

                ctx.close()
                browser.close()
        except PlaywrightError as exc:
            msg = str(exc)
            if (
                "Executable doesn't exist" in msg
                or "browserType.launch" in msg
            ):
                raise RuntimeError(
                    "Playwright 浏览器未安装。"
                    "请运行: playwright install chromium"
                ) from exc
            raise

        since_utc = since.astimezone(timezone.utc) if since else None

        # 优先用拦截到的 API 数据
        if api_video_list:
            return self._parse_vlist(
                api_video_list,
                since_utc=since_utc,
                fallback_avatar=fallback_avatar,
            )

        # 用 BV 号查详情
        if page_bvids:
            return self._fetch_video_details_for_bvids(
                page_bvids,
                since_utc=since_utc,
                fallback_avatar=fallback_avatar,
            )

        raise ValueError("Playwright 未能获取 B站视频数据")

    # ==================================================================
    # 主入口
    # ==================================================================

    def fetch_new_messages(
        self, *, since: datetime | None
    ) -> list[IncomingMessage]:
        errors: list[str] = []

        # ── 主策略: recArchivesByKeywords（极速 ~1s，无需签名/cookies）──
        try:
            t0 = time.monotonic()
            messages = self._fetch_via_rec_api(since=since)
            elapsed = time.monotonic() - t0
            logger.info(
                "recArchivesByKeywords 成功获取 %d 条 B站消息 (%.2fs)",
                len(messages),
                elapsed,
            )
            return messages
        except Exception as e:
            errors.append(f"recArchivesByKeywords: {e}")
            logger.debug("recArchivesByKeywords 失败: %s", e)

        # ── 回退 1: 纯 HTTP + WBI 签名（~0.3s，可能被风控）──
        try:
            t0 = time.monotonic()
            messages = self._fetch_via_wbi_api(since=since)
            elapsed = time.monotonic() - t0
            logger.info(
                "WBI API 成功获取 %d 条 B站消息 (%.2fs)",
                len(messages),
                elapsed,
            )
            return messages
        except Exception as e:
            errors.append(f"WBI API: {e}")
            logger.debug("WBI API 失败: %s", e)

        # ── 回退 1: jina.ai + API 详情 ──
        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": _DEFAULT_USER_AGENT},
                transport=self._transport,
            ) as client:
                bvids, fallback_avatar = self._discover_bvids(
                    client=client
                )
                if bvids:
                    since_utc = (
                        since.astimezone(timezone.utc) if since else None
                    )
                    messages = self._fetch_video_details_for_bvids(
                        bvids,
                        since_utc=since_utc,
                        fallback_avatar=fallback_avatar,
                    )
                    logger.info(
                        "jina.ai 成功获取 %d 条 B站消息", len(messages)
                    )
                    return messages
        except Exception as e:
            errors.append(f"jina.ai: {e}")
            logger.debug("jina.ai 回退失败: %s", e)

        # ── 回退 2: RSSHub ──
        try:
            messages = self._try_rsshub_feed(since=since)
            if messages:
                logger.info(
                    "RSSHub 成功获取 %d 条 B站消息", len(messages)
                )
                return messages
        except Exception as e:
            errors.append(f"RSSHub: {e}")
            logger.debug("RSSHub 回退失败: %s", e)

        # ── 回退 3: Playwright（最后手段）──
        if _HAS_PLAYWRIGHT:
            try:
                t0 = time.monotonic()
                messages = self._fetch_via_playwright(since=since)
                elapsed = time.monotonic() - t0
                logger.info(
                    "Playwright 成功获取 %d 条 B站消息 (%.2fs)",
                    len(messages),
                    elapsed,
                )
                return messages
            except Exception as e:
                errors.append(f"Playwright: {e}")
                logger.warning("Playwright 回退失败: %s", e)

        # ── 回退 4: 自定义 fallback_feed_url ──
        if self._fallback_feed_url:
            try:
                messages = FeedConnector(
                    feed_url=self._fallback_feed_url,
                    source="bilibili",
                    default_sender=self._default_sender,
                    timeout_seconds=self._timeout_seconds,
                    max_entries=self._max_items,
                ).fetch_new_messages(since=since)
                if messages:
                    return messages
            except Exception as e:
                errors.append(f"fallback feed: {e}")

        raise ValueError(
            "Bilibili 同步失败: " + "; ".join(errors)
        )
