from __future__ import annotations

from pathlib import Path

from app.settings import Settings


def test_settings_support_legacy_mercurydesk_env_prefix(monkeypatch):
    monkeypatch.delenv("AELIN_SECRET_KEY", raising=False)
    monkeypatch.setenv("MERCURYDESK_SECRET_KEY", "legacy-secret")

    settings = Settings(_env_file=None)

    assert settings.secret_key == "legacy-secret"


def test_settings_prefer_aelin_env_prefix_over_legacy(monkeypatch):
    monkeypatch.setenv("AELIN_SECRET_KEY", "new-secret")
    monkeypatch.setenv("MERCURYDESK_SECRET_KEY", "legacy-secret")

    settings = Settings(_env_file=None)

    assert settings.secret_key == "new-secret"


def test_settings_support_legacy_mercurydesk_prefix_in_dotenv(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("MERCURYDESK_QQ_BOT_TOKEN=legacy-token\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.qq_bot_token == "legacy-token"


def test_settings_keep_backward_compatible_default_database_path(monkeypatch):
    monkeypatch.delenv("AELIN_DATABASE_URL", raising=False)
    monkeypatch.delenv("MERCURYDESK_DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite+pysqlite:///./mercurydesk.db"
