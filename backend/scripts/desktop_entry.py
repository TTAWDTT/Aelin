from __future__ import annotations

import os

from langgraph_api.cli import run_server

from agent_server import auth as _agent_server_auth  # noqa: F401
from agent_server import graph as _agent_server_graph  # noqa: F401
from app import main as _app_main  # noqa: F401


def _env_port(default: int) -> int:
    try:
        return int(os.getenv("AELIN_BACKEND_PORT", str(default)))
    except (TypeError, ValueError):
        return default


def main() -> None:
    host = os.getenv("AELIN_BACKEND_HOST", "127.0.0.1")
    port = _env_port(18080)
    log_level = str(os.getenv("AELIN_BACKEND_LOG_LEVEL", "info") or "info").strip().upper()
    env = dict(os.environ)
    if not str(env.get("LANGGRAPH_AUTH_TYPE", "") or "").strip():
        env.pop("LANGGRAPH_AUTH_TYPE", None)
    if not str(env.get("LANGGRAPH_AUTH", "") or "").strip():
        env.pop("LANGGRAPH_AUTH", None)
    run_server(
        host=host,
        port=port,
        reload=False,
        graphs={
            "agent": "agent_server.graph:make_graph",
        },
        auth={
            "path": "agent_server.auth:aelin_auth",
        },
        http={
            "app": "app.main:app",
            "enable_custom_route_auth": True,
            "middleware_order": "auth_first",
        },
        env=env,
        runtime_edition="inmem",
        server_level=log_level,
    )


if __name__ == "__main__":
    main()
