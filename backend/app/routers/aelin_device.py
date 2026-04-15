from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.models import User
from app.routers.auth import get_current_user
from app.schemas import (
    AelinArtifactResolveResponse,
    AelinDeviceCapabilitiesResponse,
    AelinDevicePathOpenRequest,
    AelinDevicePathOpenResponse,
    AelinDeviceScreenCaptureRequest,
    AelinDeviceScreenCaptureResponse,
)
from app.services.artifact_files import (
    LocalArtifactAccessError,
    artifact_media_type,
    normalize_tool_artifact_payloads,
    resolve_local_artifact_path,
)
from app.services.deepagents.delivery_paths import get_delivery_paths, resolve_virtual_or_local_path
from app.services.device.device_center import (
    capture_device_screen as device_capture_screen,
    open_desktop_local_path,
    DesktopPluginActionError,
    DeviceScreenCaptureError,
    device_status_snapshot,
)


router = APIRouter(prefix="/aelin", tags=["aelin"])


@router.post("/device/screen/capture", response_model=AelinDeviceScreenCaptureResponse)
def capture_device_screen(
    payload: AelinDeviceScreenCaptureRequest | None = None,
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    request = payload or AelinDeviceScreenCaptureRequest()
    try:
        result = device_capture_screen(
            display_id=request.display_id,
            max_edge=request.max_edge,
            image_format=request.image_format,
            quality=request.quality,
            mode=request.mode,
            selection_timeout_ms=request.selection_timeout_ms,
        )
    except DeviceScreenCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return AelinDeviceScreenCaptureResponse(
        data_url=str(result.get("data_url") or "").strip(),
        name=str(result.get("name") or "").strip()[:120],
        width=max(0, int(result.get("width") or 0)),
        height=max(0, int(result.get("height") or 0)),
        source_display=str(result.get("source_display") or "").strip()[:64],
        captured_at=str(result.get("captured_at") or datetime.now(timezone.utc).isoformat())[:64],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/device/capabilities", response_model=AelinDeviceCapabilitiesResponse)
def get_device_capabilities(
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    snapshot = device_status_snapshot()
    return AelinDeviceCapabilitiesResponse(
        platform=str(snapshot.get("platform") or "unknown"),
        capabilities=dict(snapshot.get("capabilities") or {}),
        notes=list(snapshot.get("notes") or []),
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/device/path/open", response_model=AelinDevicePathOpenResponse)
def open_device_local_path(
    payload: AelinDevicePathOpenRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local device APIs.
    try:
        result = open_desktop_local_path(payload.path)
    except DesktopPluginActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return AelinDevicePathOpenResponse(
        path=str(result.get("path") or payload.path).strip()[:2000],
        opened=bool(result.get("opened", True)),
        detail=str(result.get("detail") or "ok").strip()[:200],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/artifact/content")
def get_local_artifact_content(
    path: str,
    download: bool = False,
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local artifact APIs.
    try:
        resolved = resolve_local_artifact_path(path)
    except LocalArtifactAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    response = FileResponse(
        path=str(resolved),
        media_type=artifact_media_type(resolved),
    )
    disposition = "attachment" if download else "inline"
    response.headers["Content-Disposition"] = (
        f"{disposition}; filename*=UTF-8''{quote(resolved.name)}"
    )
    return response


@router.get("/artifact/resolve", response_model=AelinArtifactResolveResponse)
def resolve_artifact_reference(
    path: str,
    workspace: str = "default",
    current_user: User = Depends(get_current_user),
):
    _ = current_user  # Auth guard for local artifact APIs.
    delivery_paths = get_delivery_paths(
        workspace=workspace,
        user_id=int(getattr(current_user, "id", 0) or 0),
        create=False,
    )
    try:
        resolved = resolve_virtual_or_local_path(
            path,
            delivery_paths,
            default_root="outputs",
            allow_workspace=True,
            allow_outputs=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"artifact_path_invalid:{str(exc)[:160]}") from exc

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="artifact_path_is_not_file")

    artifacts = normalize_tool_artifact_payloads([{"path": str(resolved)}])
    if not artifacts:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    artifact = artifacts[0]
    return AelinArtifactResolveResponse(
        workspace=str(workspace or "default"),
        requested_path=str(path or "").strip()[:2000],
        path=str(artifact.get("path") or ""),
        relative_path=str(artifact.get("relative_path") or ""),
        name=str(artifact.get("name") or resolved.name),
        mime_type=str(artifact.get("mime_type") or "application/octet-stream"),
        size_bytes=max(0, int(artifact.get("size_bytes") or 0)),
        preview_kind=str(artifact.get("preview_kind") or "unknown"),
        content=str(artifact.get("content") or ""),
        created_at=str(artifact.get("created_at") or "")[:64],
        modified_at=str(artifact.get("modified_at") or "")[:64],
        generated_at=datetime.now(timezone.utc),
    )

