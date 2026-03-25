from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PRIMARY_ENV_PREFIX = "AELIN_"
_LEGACY_ENV_PREFIX = "MERCURYDESK_"


def _merge_legacy_env_prefix(
    env_vars: dict[str, Any] | None,
    *,
    primary_prefix: str = _PRIMARY_ENV_PREFIX,
    legacy_prefix: str = _LEGACY_ENV_PREFIX,
) -> dict[str, Any]:
    merged = dict(env_vars or {})
    primary_prefix_lower = primary_prefix.lower()
    legacy_prefix_lower = legacy_prefix.lower()
    for key, value in list(merged.items()):
        key_str = str(key)
        key_lower = key_str.lower()
        if not key_lower.startswith(legacy_prefix_lower):
            continue
        suffix = key_lower[len(legacy_prefix_lower) :]
        primary_key = f"{primary_prefix_lower}{suffix}"
        merged.setdefault(primary_key, value)
    return merged


def _inject_legacy_env_fallback(source: PydanticBaseSettingsSource) -> PydanticBaseSettingsSource:
    env_vars = getattr(source, "env_vars", None)
    if isinstance(env_vars, Mapping):
        setattr(source, "env_vars", _merge_legacy_env_prefix(dict(env_vars)))
    return source


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=_PRIMARY_ENV_PREFIX,
        env_file=(str(_BACKEND_DIR / ".env"), ".env", "backend/.env"),
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _inject_legacy_env_fallback(env_settings),
            _inject_legacy_env_fallback(dotenv_settings),
            file_secret_settings,
        )

    database_url: str = "sqlite+pysqlite:///./mercurydesk.db"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    media_dir: str = "./media"
    models_catalog_url: str = "https://models.dev/api.json"
    models_catalog_refresh_seconds: int = 60 * 60

    # File memory bridge (AGENTS.md-based memory only).
    aelin_base_context_cache_ttl_seconds: float = 4.0
    aelin_base_context_cache_max_entries: int = 128

    # Agent tool policy knobs (DeepAgents-only). Legacy AelinAgentLoop 已经移除，
    # 这些配置仅用于构造 AelinToolPolicy，限制 DeepAgents 工具调用行为。
    # 当前默认值刻意放宽，以便 DeepAgents 在每轮对话中可以更自由地尝试工具调用。
    # DeepAgents 工具策略：默认给足够大的空间，让复杂任务可以自由使用工具。
    aelin_agent_loop_max_tool_calls: int = 512
    aelin_agent_loop_max_write_calls: int = 128
    aelin_agent_loop_allow_write_tools: bool = True
    feishu_bot_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bot_bind_user_email: str = ""
    feishu_bot_workspace: str = "default"
    feishu_bot_allowed_open_ids_csv: str = ""
    feishu_bot_allowed_chat_ids_csv: str = ""
    feishu_bot_command_prefix: str = "/aelin"
    feishu_bot_group_require_prefix: bool = True
    feishu_bot_message_dedupe_ttl_seconds: int = 600
    feishu_bot_reply_timeout_seconds: float = 15.0
    qq_bot_enabled: bool = False
    qq_bot_ws_url: str = "ws://127.0.0.1:6700"
    qq_bot_token: str = ""
    qq_bot_bind_user_email: str = ""
    qq_bot_workspace: str = "default"
    qq_bot_allowed_user_ids_csv: str = ""
    qq_bot_allowed_group_ids_csv: str = ""
    qq_bot_command_prefix: str = "/aelin"
    qq_bot_group_require_prefix: bool = True
    qq_bot_message_dedupe_ttl_seconds: int = 600
    qq_bot_api_timeout_seconds: float = 15.0
    desktop_plugin_base_url: str = "http://127.0.0.1:21914"
    desktop_plugin_token: str = ""
    desktop_plugin_timeout_seconds: float = 12.0
    desktop_plugin_capture_max_data_url_length: int = 3_000_000
    # Google Workspace CLI (gws) integration.
    # `google_workspace_cli_bin` 可以是 "gws"（放在 PATH 中），也可以是一个绝对路径。
    google_workspace_cli_bin: str = "gws"
    google_workspace_cli_timeout_seconds: float = 20.0
    google_workspace_cli_config_dir: str = "../data/google_workspace"
    aelin_attachment_storage_dir: str = "./data/aelin_attachments"
    aelin_attachment_max_size_bytes: int = 30 * 1024 * 1024
    aelin_attachment_chunk_size: int = 700
    aelin_attachment_chunk_overlap: int = 120
    aelin_attachment_soffice_bin: str = "soffice"
    aelin_attachment_legacy_convert_timeout_seconds: int = 30
    aelin_attachment_pdf_ocr_fallback_enabled: bool = True
    aelin_attachment_pdf_ocr_max_images_per_page: int = 4
    aelin_attachment_pdf_ocr_render_dpi: int = 220
    aelin_attachment_ocr_languages: str = "chi_sim+eng"
    aelin_attachment_ocr_psm_modes: str = "6,11,4"
    aelin_attachment_ocr_min_chars: int = 8
    aelin_attachment_ocr_max_attempts_per_image: int = 18
    aelin_attachment_ocr_image_timeout_seconds: int = 10
    aelin_attachment_ocr_page_timeout_seconds: int = 25
    aelin_attachment_tesseract_cmd: str = ""
    aelin_attachment_tessdata_dir: str = ""
    aelin_attachment_rapidocr_enabled: bool = True

    # LLM client runtime tuning.
    # DeepAgents 回路可能会触发多轮工具调用，因此默认超时时间相对更长。
    llm_request_timeout_seconds: float = 180.0
    llm_verify_ssl: bool = True
    backend_log_level: str = "INFO"

    # Optional extra DeepAgents skills root dir (for example chrome-cdp-skill).
    # When set, all subdirectories under this path will be exposed as
    # `/skills/external/<skill-name>/` to the DeepAgents SkillsMiddleware.
    deepagents_extra_skills_dir: str = ""

    # Optional Fernet key used to encrypt stored secrets.
    # Generate one via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None


settings = Settings()
