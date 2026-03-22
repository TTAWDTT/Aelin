from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.aelin_attachment_service import (
    AelinAttachmentService,
    get_aelin_attachment_service,
)
from app.services.aelin_utils import normalize_positive_ints
from app.services.web_search import WebSearchService


def _normalize_workspace(raw: str) -> str:
    clean = " ".join(str(raw or "").strip().split())
    return (clean[:64] if clean else "default") or "default"


class AelinToolHub:
    """
    Thin context binder for the current DB/user/workspace/services.

    DeepAgents now registers tools explicitly in `deepagents_graph.py`, so this
    object only carries runtime context and a few shared helpers used by those
    tools.
    """

    def __init__(
        self,
        *,
        db: Session,
        user_id: int,
        workspace: str,
        web_search_service: WebSearchService | None = None,
        attachment_service: AelinAttachmentService | None = None,
        available_attachment_ids: list[int] | None = None,
    ) -> None:
        self.db = db
        self.user_id = int(user_id)
        self.workspace = _normalize_workspace(workspace)
        self._web_search = web_search_service or WebSearchService()
        self._attachments = attachment_service or get_aelin_attachment_service()
        self._available_attachment_ids = normalize_positive_ints(
            available_attachment_ids, cap=20
        )

__all__ = ["AelinToolHub"]
