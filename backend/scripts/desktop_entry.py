from __future__ import annotations

import os

import uvicorn
from app.main import app as fastapi_app


def _env_port(default: int) -> int:
    try:
        return int(os.getenv("AELIN_BACKEND_PORT", str(default)))
    except (TypeError, ValueError):
        return default


def main() -> None:
    host = os.getenv("AELIN_BACKEND_HOST", "127.0.0.1")
    port = _env_port(18080)
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level=os.getenv("AELIN_BACKEND_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
