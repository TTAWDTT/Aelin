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

    # Optional Fernet key used to encrypt stored secrets (OAuth tokens, IMAP passwords).
    # Generate one via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None


settings = Settings()

