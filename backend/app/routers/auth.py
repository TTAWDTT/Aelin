from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.models import User
from app.schemas import Token, UserCreate, UserOut, UserUpdate
from app.security import ALGORITHM, create_access_token
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"], deprecated=True)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def _ensure_local_user(db: Session) -> User:
    """Single-user local fallback in no-login mode."""
    user = db.scalar(select(User).order_by(User.id.asc()))
    if user is not None:
        return user
    return crud.create_user(
        db,
        email="local@aelin.local",
        password=f"local-{uuid4().hex}-{uuid4().hex}",
    )


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_session)):
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = crud.create_user(db, email=payload.email, password=payload.password)
    return user


@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    user = crud.authenticate_user(db, email=form_data.username, password=form_data.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


def get_current_user(db: Session = Depends(get_session), token: str | None = Depends(oauth2_scheme)) -> User:
    fallback_user = _ensure_local_user(db)
    if not token:
        return fallback_user

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return fallback_user
        user_id = int(sub)
    except (JWTError, ValueError):
        return fallback_user

    user = db.get(User, user_id)
    if user is None:
        return fallback_user
    return user


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    # If email is being changed, check for uniqueness
    if payload.email is not None and payload.email != current_user.email:
        existing = db.scalar(select(User).where(User.email == payload.email))
        if existing is not None:
            raise HTTPException(status_code=400, detail="Email already registered")

    updated_user = crud.update_user(
        db,
        user=current_user,
        email=payload.email,
        password=payload.password,
        avatar_url=payload.avatar_url,
    )
    return updated_user


@router.post("/me/avatar", response_model=UserOut)
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    content_type = (file.content_type or "").lower()
    allowed = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported avatar type")

    media_dir = Path(settings.media_dir)
    avatars_dir = media_dir / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    filename = f"user-{current_user.id}-{uuid4().hex}{allowed[content_type]}"
    dest_path = avatars_dir / filename

    max_bytes = 5 * 1024 * 1024  # 5MB
    written = 0
    old_avatar_url = current_user.avatar_url
    try:
        with dest_path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=413, detail="Avatar too large (max 5MB)")
                f.write(chunk)
    except HTTPException:
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except Exception as e:
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=f"Failed to upload avatar: {e}") from e
    finally:
        await file.close()

    avatar_url = f"/media/avatars/{filename}"
    updated_user = crud.update_user(db, user=current_user, avatar_url=avatar_url)

    if old_avatar_url and old_avatar_url.startswith("/media/avatars/"):
        old_name = old_avatar_url.rsplit("/", 1)[-1]
        if old_name and old_name != filename:
            try:
                (avatars_dir / old_name).unlink(missing_ok=True)
            except OSError:
                pass
    return updated_user

