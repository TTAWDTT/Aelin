from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.memory.agent_memory import AgentMemoryService
from app.services.web.web_search import WebSearchService

_memory = AgentMemoryService()
_web_search = WebSearchService()


def scoped_web_search_service(proxy_url: str = "") -> WebSearchService:
    return WebSearchService(
        timeout_seconds=float(getattr(_web_search, "timeout_seconds", 10.0) or 10.0),
        max_parallel_providers=int(getattr(_web_search, "max_parallel_providers", 4) or 4),
        max_parallel_fetch=int(getattr(_web_search, "max_parallel_fetch", 4) or 4),
        enable_reader_fallback=bool(getattr(_web_search, "enable_reader_fallback", True)),
        enable_browser_fallback=bool(getattr(_web_search, "enable_browser_fallback", True)),
        proxy_url=str(proxy_url or "").strip(),
    )


def get_agents_memory_text_for_chat(db: Session, user_id: int, *, workspace: str = "default") -> str:
    try:
        text = _memory.get_agents_memory_text(db, user_id, workspace=workspace)
    except Exception:
        text = ""
    return str(text or "").strip()
