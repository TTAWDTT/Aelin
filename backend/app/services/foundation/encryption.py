from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.settings import settings


def _get_fernet() -> Fernet | None:
    if not settings.fernet_key:
        return None
    return Fernet(settings.fernet_key.encode() if isinstance(settings.fernet_key, str) else settings.fernet_key)


def encrypt_optional(value: str | None) -> str | None:
    if value is None:
        return None
    f = _get_fernet()
    if f is None:
        return value
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_optional(value: str | None) -> str | None:
    if value is None:
        return None
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Backward compatibility: if a secret was stored before FERNET was enabled
        # (or the key was rotated), fall back to treating it as plaintext.
        return value
