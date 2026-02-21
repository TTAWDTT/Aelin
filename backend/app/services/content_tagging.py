from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import crud
from app.db import create_session
from app.models import Message, MessageTopicTag
from app.schemas import AgentConfigOut
from app.services.encryption import decrypt_optional
from app.services.llm import LLMService

_LOG = logging.getLogger(__name__)

CONTENT_SOURCES = {"x", "weibo", "xiaohongshu", "douyin", "bilibili", "rss", "web"}
_MAX_TAGS_PER_MESSAGE = 5

CANONICAL_TAGS = [
    "AI",
    "科技",
    "编程",
    "数码",
    "商业",
    "财经",
    "汽车",
    "体育",
    "游戏",
    "影视",
    "音乐",
    "教育",
    "健康",
    "旅行",
    "时尚",
    "美食",
    "设计",
    "营销",
    "创业",
    "生活",
    "其他",
]

ALIAS_MAP = {
    "aigc": "AI",
    "人工智能": "AI",
    "ai": "AI",
    "machine learning": "AI",
    "deep learning": "AI",
    "programming": "编程",
    "coding": "编程",
    "code": "编程",
    "开发": "编程",
    "tech": "科技",
    "technology": "科技",
    "digital": "数码",
    "business": "商业",
    "finance": "财经",
    "financial": "财经",
    "sport": "体育",
    "movie": "影视",
    "film": "影视",
    "music": "音乐",
    "fashion": "时尚",
    "food": "美食",
    "design": "设计",
    "marketing": "营销",
    "startup": "创业",
}

_TAG_RULES: dict[str, tuple[str, ...]] = {
    "AI": ("ai", "aigc", "llm", "大模型", "人工智能", "机器学习", "openai", "deepseek", "claude"),
    "科技": ("科技", "tech", "technology", "创新", "研究", "前沿"),
    "编程": ("代码", "编程", "开发", "工程", "api", "github", "python", "javascript", "rust", "go"),
    "数码": ("数码", "手机", "芯片", "硬件", "电脑", "笔记本", "平板"),
    "商业": ("公司", "企业", "战略", "商业", "产品发布", "收购", "融资"),
    "财经": ("财经", "股市", "基金", "财报", "投资", "证券", "美联储", "利率"),
    "汽车": ("汽车", "新车", "车企", "比亚迪", "特斯拉", "新能源车"),
    "体育": ("体育", "足球", "篮球", "比赛", "联赛", "欧冠", "英超", "nba"),
    "游戏": ("游戏", "电竞", "steam", "主机", "手游"),
    "影视": ("电影", "电视剧", "综艺", "票房", "导演", "演员"),
    "音乐": ("音乐", "专辑", "演唱会", "歌手", "乐队"),
    "教育": ("教育", "学习", "课程", "学校", "考试", "留学"),
    "健康": ("健康", "医疗", "医院", "减脂", "健身", "睡眠", "营养"),
    "旅行": ("旅行", "旅游", "机票", "酒店", "航班", "目的地"),
    "时尚": ("时尚", "穿搭", "美妆", "护肤", "品牌"),
    "美食": ("美食", "餐厅", "烹饪", "菜谱", "探店"),
    "设计": ("设计", "ui", "ux", "视觉", "排版", "字体"),
    "营销": ("营销", "投放", "品牌增长", "流量", "转化"),
    "创业": ("创业", "创始人", "初创", "孵化", "融资"),
    "生活": ("生活", "日常", "经验分享", "vlog", "记录"),
}

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(slots=True)
class TagClassification:
    primary_tag: str
    tags: list[str]
    confidence: float
    ambiguous: bool = False


_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="content-tag")
_job_lock = Lock()


def _clean_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_tag(tag: str | None) -> str | None:
    raw = _clean_text(tag)
    if not raw:
        return None
    if raw in CANONICAL_TAGS:
        return raw
    low = raw.lower()
    mapped = ALIAS_MAP.get(low)
    if mapped:
        return mapped
    for canonical in CANONICAL_TAGS:
        if canonical.lower() == low:
            return canonical
    return None


def _distinct_keep_order(tags: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        normalized = normalize_tag(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def classify_rule_based(*, source: str, sender: str, subject: str, preview: str) -> TagClassification:
    text = " ".join([_clean_text(source), _clean_text(sender), _clean_text(subject), _clean_text(preview)]).lower()
    score_map: dict[str, float] = {}
    for tag, keywords in _TAG_RULES.items():
        score = 0.0
        for keyword in keywords:
            key = keyword.lower()
            if not key:
                continue
            if key in text:
                score += 1.2 if len(key) >= 4 else 0.8
        if score > 0:
            score_map[tag] = score

    if not score_map:
        return TagClassification(primary_tag="其他", tags=["其他"], confidence=0.42, ambiguous=False)

    ranked = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    primary_tag, top_score = ranked[0]
    tags = [primary_tag] + [tag for tag, _ in ranked[1 : _MAX_TAGS_PER_MESSAGE]]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    ambiguous = len(ranked) > 1 and (top_score - second_score) < 0.75
    confidence = min(0.95, max(0.45, 0.45 + top_score / 8.0))
    return TagClassification(primary_tag=primary_tag, tags=_distinct_keep_order(tags), confidence=confidence, ambiguous=ambiguous)


def _should_try_llm(rule: TagClassification) -> bool:
    if not rule.tags:
        return True
    if rule.confidence < 0.65:
        return True
    return bool(rule.ambiguous)


def _extract_json_candidate(raw: str) -> str:
    block = _CODE_BLOCK_RE.search(raw or "")
    if block:
        return block.group(1).strip()
    matched = _JSON_OBJ_RE.search(raw or "")
    if matched:
        return matched.group(0).strip()
    return (raw or "").strip()


def _build_llm_service(db: Session, *, user_id: int) -> LLMService | None:
    cfg = crud.get_agent_config(db, user_id=user_id)
    if cfg is None or cfg.provider == "rule_based":
        return None
    api_key = decrypt_optional(cfg.api_key)
    if not api_key:
        return None
    try:
        config_out = AgentConfigOut(
            provider=cfg.provider,
            base_url=cfg.base_url,
            model=cfg.model,
            temperature=cfg.temperature,
            has_api_key=True,
        )
        service = LLMService(config_out, api_key)
        if not service.is_configured():
            return None
        return service
    except Exception:
        return None


def _classify_with_llm(
    db: Session,
    *,
    user_id: int,
    source: str,
    sender: str,
    subject: str,
    preview: str,
) -> TagClassification | None:
    service = _build_llm_service(db, user_id=user_id)
    if service is None:
        return None

    payload = {
        "source": _clean_text(source),
        "sender": _clean_text(sender),
        "subject": _clean_text(subject),
        "preview": _clean_text(preview),
        "allowed_tags": CANONICAL_TAGS,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You classify short social/news content into topic tags. "
                "Return strict JSON only: "
                "{\"primary_tag\":\"...\",\"tags\":[\"...\"],\"confidence\":0.0}. "
                "Use only tags from allowed_tags."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]

    try:
        raw = service._chat(messages=messages, max_tokens=220, stream=False)
        if not isinstance(raw, str):
            return None
        parsed = json.loads(_extract_json_candidate(raw))
        if not isinstance(parsed, dict):
            return None
    except Exception:
        return None

    llm_tags = parsed.get("tags")
    if not isinstance(llm_tags, list):
        llm_tags = []
    tags = _distinct_keep_order(str(item) for item in llm_tags)
    primary = normalize_tag(str(parsed.get("primary_tag") or ""))
    if primary and primary not in tags:
        tags.insert(0, primary)
    if not tags:
        return None

    primary_tag = primary or tags[0]
    confidence_raw = parsed.get("confidence")
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.6
    confidence = max(0.4, min(0.98, confidence))
    return TagClassification(primary_tag=primary_tag, tags=tags[:_MAX_TAGS_PER_MESSAGE], confidence=confidence, ambiguous=False)


def _merge_rule_and_llm(rule: TagClassification, llm: TagClassification) -> TagClassification:
    combined_tags = _distinct_keep_order([llm.primary_tag, *llm.tags, rule.primary_tag, *rule.tags])
    if not combined_tags:
        combined_tags = ["其他"]
    primary = llm.primary_tag if llm.primary_tag in combined_tags else combined_tags[0]
    confidence = max(rule.confidence, min(0.98, llm.confidence))
    return TagClassification(primary_tag=primary, tags=combined_tags[:_MAX_TAGS_PER_MESSAGE], confidence=confidence, ambiguous=False)


def _replace_message_tags(
    db: Session,
    *,
    user_id: int,
    message_id: int,
    classification: TagClassification,
    method: str,
) -> None:
    tags = _distinct_keep_order(classification.tags)
    if not tags:
        tags = ["其他"]
    if classification.primary_tag not in tags:
        tags.insert(0, classification.primary_tag or "其他")
    tags = tags[:_MAX_TAGS_PER_MESSAGE]
    primary = classification.primary_tag if classification.primary_tag in tags else tags[0]

    db.execute(
        delete(MessageTopicTag).where(
            MessageTopicTag.user_id == user_id,
            MessageTopicTag.message_id == message_id,
        )
    )
    for idx, tag in enumerate(tags):
        confidence = max(0.35, min(0.98, classification.confidence - idx * 0.08))
        db.add(
            MessageTopicTag(
                user_id=user_id,
                message_id=message_id,
                tag=tag,
                confidence=confidence,
                method=method,
                is_primary=(tag == primary),
            )
        )


def tag_message_by_id(
    db: Session,
    *,
    user_id: int,
    message_id: int,
    allow_llm: bool = True,
) -> bool:
    message = db.scalar(
        select(Message).where(
            Message.user_id == user_id,
            Message.id == message_id,
        )
    )
    if message is None:
        return False
    if (message.source or "").strip().lower() not in CONTENT_SOURCES:
        return False

    rule = classify_rule_based(
        source=message.source or "",
        sender=message.sender or "",
        subject=message.subject or "",
        preview=message.body_preview or message.body or "",
    )
    classification = rule
    method = "rule"

    if allow_llm and _should_try_llm(rule):
        try:
            llm_result = _classify_with_llm(
                db,
                user_id=user_id,
                source=message.source or "",
                sender=message.sender or "",
                subject=message.subject or "",
                preview=message.body_preview or message.body or "",
            )
        except Exception:
            llm_result = None
        if llm_result is not None:
            classification = _merge_rule_and_llm(rule, llm_result)
            method = "hybrid"

    _replace_message_tags(
        db,
        user_id=user_id,
        message_id=message.id,
        classification=classification,
        method=method,
    )
    return True


def tag_messages_for_user(
    db: Session,
    *,
    user_id: int,
    message_ids: Iterable[int],
    allow_llm: bool = True,
) -> int:
    done = 0
    for raw_id in message_ids:
        try:
            message_id = int(raw_id)
        except Exception:
            continue
        if message_id <= 0:
            continue
        try:
            ok = tag_message_by_id(db, user_id=user_id, message_id=message_id, allow_llm=allow_llm)
            if ok:
                done += 1
        except Exception as exc:
            _LOG.debug("tag_message_by_id failed for %s: %s", message_id, exc)
    return done


def _should_run_inline() -> bool:
    db = create_session()
    try:
        bind = db.get_bind()
        if bind is None:
            return False
        if bind.dialect.name != "sqlite":
            return False
        db_name = (getattr(bind.url, "database", None) or "").strip().lower()
        return db_name in {"", ":memory:"} or db_name.startswith("file::memory:")
    finally:
        db.close()


def _run_tagging_job(*, user_id: int, message_ids: list[int], allow_llm: bool) -> None:
    db = create_session()
    try:
        touched = tag_messages_for_user(db, user_id=user_id, message_ids=message_ids, allow_llm=allow_llm)
        if touched > 0:
            db.commit()
    except Exception as exc:
        db.rollback()
        _LOG.debug("tagging job failed for user %s: %s", user_id, exc)
    finally:
        db.close()


def enqueue_tagging_job(*, user_id: int, message_ids: Iterable[int], allow_llm: bool = True) -> None:
    clean_ids: set[int] = set()
    for raw in message_ids:
        try:
            value = int(raw)
        except Exception:
            continue
        if value > 0:
            clean_ids.add(value)
    deduped = sorted(clean_ids)
    if not deduped:
        return
    if _should_run_inline():
        _run_tagging_job(user_id=user_id, message_ids=deduped, allow_llm=allow_llm)
        return
    with _job_lock:
        _executor.submit(_run_tagging_job, user_id=user_id, message_ids=deduped, allow_llm=allow_llm)


def ensure_rule_tags_for_messages(db: Session, *, user_id: int, message_ids: Iterable[int]) -> int:
    touched = tag_messages_for_user(db, user_id=user_id, message_ids=message_ids, allow_llm=False)
    if touched > 0:
        db.commit()
    return touched


def normalize_follow_tag(tag: str) -> str:
    normalized = normalize_tag(tag)
    if normalized:
        return normalized
    safe = _clean_text(tag)[:64]
    return safe or "其他"


def utc_iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
