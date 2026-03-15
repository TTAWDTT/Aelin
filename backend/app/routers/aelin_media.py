from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinMediaAuthGuideRequest,
    AelinMediaAuthGuideResponse,
    AelinMediaIngestRequest,
    AelinMediaIngestResponse,
)
from app.services.aelin_media_pipeline import media_ingest_service as _media_ingest
from app.services.aelin_runtime import normalize_workspace as _normalize_workspace
from app.services.aelin_runtime import resolve_llm_service as _resolve_llm_service
from app.services.media_ingest import MediaIngestError


router = APIRouter(prefix="/aelin", tags=["aelin"])


def _status_code_for_media_error(code: str, *, auth_related_codes: set[str]) -> int:
    if code in {"tool_missing", "extract_failed", "extract_timeout", "no_extractable_content", *auth_related_codes}:
        return 422
    return 400


@router.post("/media/ingest", response_model=AelinMediaIngestResponse)
def ingest_media_content(
    payload: AelinMediaIngestRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    workspace = _normalize_workspace(payload.workspace)
    service, provider = _resolve_llm_service(db, current_user)
    platform = _media_ingest.detect_platform(payload.url)
    auth_related_codes = {
        "auth_required",
        "cookie_unavailable",
        "auth_guide_failed",
        "auth_guide_unavailable",
        "auth_guide_disabled",
    }

    guide_payload: dict[str, Any] | None = None
    try:
        result = _media_ingest.ingest(
            user_id=current_user.id,
            workspace=workspace,
            url=payload.url,
            service=service,
            provider=provider,
            languages=payload.languages,
        )
    except MediaIngestError as exc:
        if (
            platform == "douyin"
            and payload.auto_login_guide
            and exc.code in {"auth_required", "cookie_unavailable"}
        ):
            try:
                guide_payload = _media_ingest.run_douyin_login_guide(
                    wait_seconds=payload.login_wait_seconds,
                    open_url=payload.url,
                    force_relogin=payload.force_relogin,
                )
            except MediaIngestError as guide_exc:
                raise HTTPException(
                    status_code=_status_code_for_media_error(guide_exc.code, auth_related_codes=auth_related_codes),
                    detail={
                        "code": guide_exc.code,
                        "message": guide_exc.message,
                        "guide": _media_ingest.build_douyin_auth_guidance(
                            wait_seconds=payload.login_wait_seconds,
                            open_url=payload.url,
                            force_relogin=payload.force_relogin,
                        ),
                    },
                ) from guide_exc
            if bool(guide_payload.get("ok")):
                try:
                    result = _media_ingest.ingest(
                        user_id=current_user.id,
                        workspace=workspace,
                        url=payload.url,
                        service=service,
                        provider=provider,
                        languages=payload.languages,
                    )
                except MediaIngestError as retry_exc:
                    raise HTTPException(
                        status_code=_status_code_for_media_error(retry_exc.code, auth_related_codes=auth_related_codes),
                        detail={
                            "code": retry_exc.code,
                            "message": retry_exc.message,
                            "guide": guide_payload,
                            "guide_applied": True,
                        },
                    ) from retry_exc
            else:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "auth_required",
                        "message": str(guide_payload.get("message") or exc.message),
                        "guide": guide_payload,
                        "guide_applied": True,
                    },
                ) from exc
        else:
            detail = {"code": exc.code, "message": exc.message}
            if platform == "douyin" and exc.code in auth_related_codes:
                detail["guide"] = _media_ingest.build_douyin_auth_guidance(
                    wait_seconds=payload.login_wait_seconds,
                    open_url=payload.url,
                    force_relogin=payload.force_relogin,
                )
            raise HTTPException(
                status_code=_status_code_for_media_error(exc.code, auth_related_codes=auth_related_codes),
                detail=detail,
            ) from exc

    status = "processed"
    message = f"已完成 {result.platform} 内容摘要。"
    if (not result.quality_usable) or result.needs_review:
        status = "needs_review"
        reason = result.quality_reason or "quality_gate"
        message = f"已完成 {result.platform} 内容摘要，但未通过质量门禁（reason={reason}）。"
    if guide_payload is not None and bool(guide_payload.get("ok")):
        message = f"{message}（已自动完成抖音登录引导并重试）"
    return AelinMediaIngestResponse(
        status=status,
        message=message,
        url=result.canonical_url,
        platform=result.platform,
        title=result.title,
        source_type=result.source_type,
        summary=result.summary,
        summary_overview=result.summary_overview,
        information_note=result.information_note,
        confidence=result.confidence,
        quality_score=result.quality_score,
        quality_reason=result.quality_reason,
        quality_usable=result.quality_usable,
        needs_review=result.needs_review,
        written=False,
        limitations=result.limitations,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/media/auth/douyin/guide", response_model=AelinMediaAuthGuideResponse)
def launch_douyin_media_login_guide(
    payload: AelinMediaAuthGuideRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    try:
        result = _media_ingest.run_douyin_login_guide(
            wait_seconds=payload.wait_seconds,
            open_url=payload.open_url,
            force_relogin=payload.force_relogin,
        )
    except MediaIngestError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": exc.code,
                "message": exc.message,
                "guide": _media_ingest.build_douyin_auth_guidance(
                    wait_seconds=payload.wait_seconds,
                    open_url=payload.open_url,
                    force_relogin=payload.force_relogin,
                ),
            },
        ) from exc
    status = "ready" if bool(result.get("ok")) else "pending"
    return AelinMediaAuthGuideResponse(
        status=status,
        platform="douyin",
        message=str(result.get("message") or ""),
        login_url=str(result.get("login_url") or ""),
        profile_dir=str(result.get("profile_dir") or ""),
        wait_seconds=int(result.get("wait_seconds") or 0),
        cookie_count=int(result.get("cookie_count") or 0),
        generated_at=datetime.now(timezone.utc),
    )
