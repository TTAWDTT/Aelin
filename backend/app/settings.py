from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AELIN_",
        env_file=(str(_BACKEND_DIR / ".env"), ".env", "backend/.env"),
        extra="ignore",
    )

    database_url: str = "sqlite+pysqlite:///./aelin.db"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    media_dir: str = "./media"
    models_catalog_url: str = "https://models.dev/api.json"
    models_catalog_refresh_seconds: int = 60 * 60
    frontend_url: str = "http://127.0.0.1:5173"
    api_public_base_url: str = "http://127.0.0.1:8000"

    # Crawler runtime tuning.
    crawler_headless: bool = False
    crawler_use_persistent_login: bool = True
    crawler_browser_data_dir: str = "./browser_data"
    crawler_rsshub_parallelism: int = 12
    crawler_playwright_poll_seconds: int = 10

    # File memory bridge (AGENTS.md-based memory only).
    aelin_base_context_cache_ttl_seconds: float = 4.0
    aelin_base_context_cache_max_entries: int = 128

    # Agent tool policy knobs (DeepAgents-only). Legacy AelinAgentLoop 已经移除，
    # 这些配置仅用于构造 AelinToolPolicy，限制 DeepAgents 工具调用行为。
    # 当前默认值刻意放宽，以便 DeepAgents 在每轮对话中可以更自由地尝试工具调用。
    # DeepAgents 工具策略：默认给足够大的空间，让复杂任务可以自由使用工具。
    aelin_agent_loop_max_tool_calls: int = 512
    aelin_agent_loop_max_calls_per_round: int = 128
    aelin_agent_loop_max_write_calls: int = 128
    aelin_agent_loop_allow_write_tools: bool = True
    feishu_bot_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bot_name: str = "Aelin"
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
    qq_bot_name: str = "Aelin"
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
    desktop_module_base_url: str = ""
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
    backend_log_level: str = "INFO"

    # Media ingest (yt-dlp) network/auth tuning.
    browser_tool_headless: bool = True
    browser_tool_open_external_on_navigate: bool = False
    browser_tool_mode_default: str = "auto"  # auto | managed | cdp
    browser_tool_cdp_enabled: bool = False
    browser_tool_cdp_endpoint: str = "http://127.0.0.1:9222"
    browser_tool_cdp_auto_launch: bool = True
    browser_tool_cdp_launch_timeout_seconds: float = 10.0
    browser_tool_cdp_browser_path: str = ""
    browser_tool_cdp_profile_dir: str = ""
    browser_tool_default_timeout_ms: int = 12_000
    browser_tool_idle_ttl_seconds: int = 900
    browser_tool_profile_dir: str = "./browser_data/agent_browser"

    # Optional extra DeepAgents skills root dir (for example chrome-cdp-skill).
    # When set, all subdirectories under this path will be exposed as
    # `/skills/external/<skill-name>/` to the DeepAgents SkillsMiddleware.
    deepagents_extra_skills_dir: str = ""

    # Optional Fernet key used to encrypt stored secrets.
    # Generate one via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None


settings = Settings()
