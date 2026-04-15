from __future__ import annotations

import threading
from collections import OrderedDict

from sqlalchemy.orm import Session

from app.services.memory.agent_memory import AgentMemoryService
from app.services.web.web_search import WebSearchService
from app.settings import settings

_memory = AgentMemoryService()
_web_search = WebSearchService()
_WEB_SEARCH_CACHE_LOCK = threading.Lock()
_WEB_SEARCH_CACHE: OrderedDict[str, WebSearchService] = OrderedDict()


def _web_search_cache_max_entries() -> int:
    try:
        return max(1, int(getattr(settings, "deepagents_web_search_service_cache_max_entries", 8) or 8))
    except Exception:
        return 8


def _cached_web_search_service(proxy_url: str) -> WebSearchService:
    key = str(proxy_url or "").strip()
    with _WEB_SEARCH_CACHE_LOCK:
        cached = _WEB_SEARCH_CACHE.get(key)
        if cached is not None:
            _WEB_SEARCH_CACHE.move_to_end(key)
            return cached
        service = WebSearchService(
            timeout_seconds=float(getattr(_web_search, "timeout_seconds", 10.0) or 10.0),
            max_parallel_providers=int(getattr(_web_search, "max_parallel_providers", 4) or 4),
            max_parallel_fetch=int(getattr(_web_search, "max_parallel_fetch", 4) or 4),
            enable_reader_fallback=bool(getattr(_web_search, "enable_reader_fallback", True)),
            enable_browser_fallback=bool(getattr(_web_search, "enable_browser_fallback", True)),
            proxy_url=key,
        )
        _WEB_SEARCH_CACHE[key] = service
        _WEB_SEARCH_CACHE.move_to_end(key)
        while len(_WEB_SEARCH_CACHE) > _web_search_cache_max_entries():
            _WEB_SEARCH_CACHE.popitem(last=False)
        return service


def scoped_web_search_service(proxy_url: str = "") -> WebSearchService:
    return _cached_web_search_service(str(proxy_url or "").strip())


def get_agents_memory_text_for_chat(db: Session, user_id: int, *, workspace: str = "default") -> str:
    try:
        text = _memory.get_agents_memory_text(db, user_id, workspace=workspace)
    except Exception:
        text = ""
    return str(text or "").strip()
