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

    # Autonomous tracking scheduler.
    tracking_scheduler_enabled: bool = True
    tracking_scheduler_tick_seconds: float = 1.0
    tracking_scheduler_batch_size: int = 80
    tracking_global_max_workers: int = 16
    tracking_source_max_workers: int = 4
    tracking_min_interval_seconds: int = 30
    tracking_default_term_interval_seconds: int = 120
    tracking_default_url_interval_seconds: int = 180
    tracking_max_backoff_seconds: int = 60 * 60 * 6
    tracking_request_timeout_seconds: float = 15.0
    tracking_target_timeout_seconds: float = 70.0
    tracking_error_threshold: int = 10
    tracking_dedupe_window_hours: int = 24
    tracking_quiet_start_hour: int = 23
    tracking_quiet_end_hour: int = 8
    tracking_sqlite_lock_retry_attempts: int = 4
    tracking_sqlite_lock_retry_base_delay_seconds: float = 0.15

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
    aelin_tracking_snapshot_cache_ttl_seconds: float = 10.0
    aelin_tracking_snapshot_cache_max_entries: int = 256
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
    aelin_agent_loop_round_timeout_seconds: float = 40.0
    aelin_agent_loop_total_timeout_seconds: float = 120.0

    # LLM client runtime tuning.
    llm_request_timeout_seconds: float = 90.0

    # Media ingest (yt-dlp) network/auth tuning.
    media_ingest_cookie_mode: str = "off"  # off | browser | file
    media_ingest_cookie_browser: str = "chrome"  # chrome | edge | firefox | safari
    media_ingest_cookie_browser_profile: str = ""  # e.g. "Default"
    media_ingest_cookie_file: str = ""  # Netscape cookie file path
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

    # Optional Fernet key used to encrypt stored secrets (OAuth tokens, IMAP passwords).
    # Generate one via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None


settings = Settings()
