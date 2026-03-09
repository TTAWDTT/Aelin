from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MERCURYDESK_",
        env_file=(str(_BACKEND_DIR / ".env"), ".env", "backend/.env"),
        extra="ignore",
    )

    database_url: str = "sqlite+pysqlite:///./mercurydesk.db"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    media_dir: str = "./media"
    rsshub_base_url: str = "https://rsshub.app"
    models_catalog_url: str = "https://models.dev/api.json"
    models_catalog_refresh_seconds: int = 60 * 60
    frontend_url: str = "http://127.0.0.1:5173"
    api_public_base_url: str = "http://127.0.0.1:8000"
    oauth_redirect_base_url: str = "http://127.0.0.1:8000"
    forward_inbound_domain: str = "inbox.localhost"
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    outlook_client_id: str | None = None
    outlook_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # X (Twitter) API v2 Bearer Token for official API access
    x_bearer_token: str | None = None

    # Sync job concurrency (accounts can be synced in parallel).
    sync_job_max_workers: int = 12

    # Crawler runtime tuning.
    crawler_headless: bool = False
    crawler_use_persistent_login: bool = True
    crawler_browser_data_dir: str = "./browser_data"
    crawler_rsshub_parallelism: int = 12
    crawler_playwright_poll_seconds: int = 10

    # File memory bridge (OpenViking-compatible projection + retrieval fallback).
    openviking_enabled: bool = True
    openviking_semantic_enabled: bool = True
    openviking_sync_on_write: bool = True
    openviking_wait_processed_on_search: bool = False
    openviking_resync_interval_seconds: float = 120.0
    openviking_data_dir: str = "../data/aelin_memory"
    openviking_query_limit: int = 8
    openviking_local_cache_max_entries: int = 2000
    aelin_parallel_memory_draft_enabled: bool = True
    aelin_parallel_memory_draft_workers: int = 4
    aelin_parallel_memory_draft_timeout_seconds: float = 2.0
    aelin_parallel_memory_draft_min_confidence: float = 0.58
    aelin_base_context_cache_ttl_seconds: float = 4.0
    aelin_base_context_cache_max_entries: int = 128
    aelin_agent_loop_enabled: bool = True
    aelin_agent_loop_shadow_enabled: bool = False
    aelin_agent_loop_max_rounds: int = 8
    aelin_agent_loop_max_tool_calls: int = 15
    aelin_agent_loop_max_calls_per_round: int = 2
    aelin_agent_loop_max_write_calls: int = 15
    aelin_agent_loop_allow_write_tools: bool = True
    aelin_agent_loop_hard_fail: bool = True
    aelin_agent_loop_user_whitelist_csv: str = ""
    aelin_agent_loop_workspace_whitelist_csv: str = ""
    # Agent-loop timeouts (per round + overall)。如需调整针对 PinchTab 等长任务的等待窗口，
    # 建议通过环境变量显式覆盖，而不是在代码里硬编码过大的默认值。
    aelin_agent_loop_round_timeout_seconds: float = 40.0
    aelin_agent_loop_total_timeout_seconds: float = 120.0
    desktop_plugin_base_url: str = "http://127.0.0.1:21914"
    desktop_plugin_token: str = ""
    desktop_plugin_timeout_seconds: float = 12.0
    desktop_plugin_capture_max_data_url_length: int = 3_000_000
    pinchtab_base_url: str = "http://127.0.0.1:9867"
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
    llm_request_timeout_seconds: float = 90.0
    backend_log_level: str = "INFO"

    # Media ingest (yt-dlp) network/auth tuning.
    media_ingest_cookie_mode: str = "off"  # off | browser | file
    media_ingest_cookie_browser: str = "chrome"  # chrome | edge | firefox | safari
    media_ingest_cookie_browser_profile: str = ""  # e.g. "Default"
    media_ingest_cookie_file: str = ""  # Netscape cookie file path
    media_ingest_temp_dir: str = ""  # optional temp workdir root; defaults to OS temp
    media_ingest_proxy_url: str = ""  # e.g. http://127.0.0.1:7890
    media_ingest_douyin_auto_login_enabled: bool = True
    media_ingest_douyin_browser_profile_dir: str = "./browser_data/douyin_media"
    media_ingest_douyin_login_url: str = "https://www.douyin.com/"
    media_ingest_douyin_asr_enabled: bool = True
    media_ingest_douyin_asr_backend: str = "auto"  # auto | faster_whisper | openai
    media_ingest_douyin_asr_model: str = "whisper-1"
    media_ingest_douyin_asr_local_model: str = "small"
    media_ingest_douyin_asr_local_device: str = "auto"  # auto | cpu | cuda
    media_ingest_douyin_asr_local_compute_type: str = "int8"
    media_ingest_douyin_asr_local_beam_size: int = 4
    media_ingest_douyin_asr_max_audio_seconds: int = 120
    media_ingest_douyin_asr_timeout_seconds: int = 80
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

    # Optional Fernet key used to encrypt stored secrets (OAuth tokens, IMAP passwords).
    # Generate one via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None


settings = Settings()
