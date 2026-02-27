from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import init_engine
from app.main import create_app
from app.models import Base
from app.settings import settings


def test_register_login_sync_and_list():
    # In-memory SQLite for tests (single-connection StaticPool semantics via connect_args).
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    # Point app DB helpers at the test engine
    init_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    # Replace the global engine with our actual test engine to ensure data persists for the duration of the test.
    import app.db as db_module

    db_module._engine = engine  # type: ignore[attr-defined]
    db_module._SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)  # type: ignore[attr-defined]

    with tempfile.TemporaryDirectory() as tmp_media:
        settings.media_dir = tmp_media
        app = create_app()
        client = TestClient(app)

        # Register
        reg = client.post("/api/v1/register", json={"email": "demo@example.com", "password": "password123"})
        assert reg.status_code == 200, reg.text

        # Login
        token = client.post(
            "/api/v1/token",
            data={"username": "demo@example.com", "password": "password123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert token.status_code == 200, token.text
        access_token = token.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Upload avatar (multipart) and ensure it was saved.
        avatar = client.post(
            "/api/v1/me/avatar",
            files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
            headers=headers,
        )
        assert avatar.status_code == 200, avatar.text
        avatar_url = avatar.json().get("avatar_url")
        assert isinstance(avatar_url, str) and avatar_url.startswith("/media/avatars/")
        stored = Path(tmp_media) / "avatars" / avatar_url.rsplit("/", 1)[-1]
        assert stored.exists()

        # Create a mock connected account
        acct = client.post(
            "/api/v1/accounts",
            json={"provider": "mock", "identifier": "demo", "access_token": "x"},
            headers=headers,
        )
        assert acct.status_code == 200, acct.text
        account_id = acct.json()["id"]

        # IMAP accounts should require configuration.
        bad_imap = client.post(
            "/api/v1/accounts",
            json={"provider": "imap", "identifier": "demo@example.com"},
            headers=headers,
        )
        assert bad_imap.status_code == 400, bad_imap.text

        # Create an IMAP connected account (config stored; sync not exercised in tests).
        imap_acct = client.post(
            "/api/v1/accounts",
            json={
                "provider": "imap",
                "identifier": "demo@example.com",
                "imap_host": "imap.example.com",
                "imap_port": 993,
                "imap_use_ssl": True,
                "imap_username": "demo@example.com",
                "imap_password": "password",
                "imap_mailbox": "INBOX",
            },
            headers=headers,
        )
        assert imap_acct.status_code == 200, imap_acct.text

        # Create RSS / Bilibili / X subscription accounts.
        rss_acct = client.post(
            "/api/v1/accounts",
            json={
                "provider": "rss",
                "feed_url": "https://www.anthropic.com/news/rss.xml",
                "feed_homepage_url": "https://www.anthropic.com/news",
                "feed_display_name": "Claude Blog",
            },
            headers=headers,
        )
        assert rss_acct.status_code == 200, rss_acct.text

        bilibili_acct = client.post(
            "/api/v1/accounts",
            json={"provider": "bilibili", "bilibili_uid": "2233"},
            headers=headers,
        )
        assert bilibili_acct.status_code == 200, bilibili_acct.text

        x_acct = client.post(
            "/api/v1/accounts",
            json={"provider": "x", "x_username": "openai"},
            headers=headers,
        )
        assert x_acct.status_code == 200, x_acct.text

        forward_acct = client.post(
            "/api/v1/accounts",
            json={"provider": "forward", "identifier": "from@example.com"},
            headers=headers,
        )
        assert forward_acct.status_code == 200, forward_acct.text

        forward_id = forward_acct.json()["id"]
        forward_info = client.get(f"/api/v1/accounts/{forward_id}/forward-info", headers=headers)
        assert forward_info.status_code == 200, forward_info.text
        forward_address = forward_info.json()["forward_address"]
        assert "@" in forward_address
        inbound_url = forward_info.json()["inbound_url"]
        assert inbound_url.endswith("/api/v1/inbound/forward")

        inbound_path = "/api/v1/inbound/forward"
        push = client.post(
            inbound_path,
            json={
                "recipient": forward_address,
                "from": "noreply@example.com",
                "subject": "Forward Test",
                "body": "Forward body",
            },
        )
        assert push.status_code == 200, push.text

        def run_sync_and_wait(target_account_id: int) -> dict:
            started = client.post(f"/api/v1/accounts/{target_account_id}/sync", headers=headers)
            assert started.status_code in {200, 202}, started.text
            started_payload = started.json()
            if "inserted" in started_payload:
                return started_payload

            job_id = started_payload.get("job_id")
            assert isinstance(job_id, str) and job_id
            for _ in range(200):
                job_resp = client.get(f"/api/v1/accounts/sync-jobs/{job_id}", headers=headers)
                assert job_resp.status_code == 200, job_resp.text
                job_payload = job_resp.json()
                if job_payload.get("status") == "succeeded":
                    return {
                        "inserted": int(job_payload.get("inserted") or 0),
                        "account_id": int(job_payload["account_id"]),
                    }
                if job_payload.get("status") == "failed":
                    raise AssertionError(f"sync job failed: {job_payload.get('error')}")
                time.sleep(0.05)
            raise AssertionError("sync job timed out")

        # Sync it
        sync = run_sync_and_wait(account_id)
        assert sync["inserted"] >= 1
        sync_again = run_sync_and_wait(account_id)
        assert sync_again["inserted"] >= 0

        accounts = client.get("/api/v1/accounts", headers=headers)
        assert accounts.status_code == 200, accounts.text
        assert any(a["provider"] == "imap" for a in accounts.json())
        providers = {a["provider"] for a in accounts.json()}
        assert {"rss", "bilibili", "x", "forward"}.issubset(providers)

        # List contacts
        contacts = client.get("/api/v1/contacts", headers=headers)
        assert contacts.status_code == 200, contacts.text
        contacts_data = contacts.json()
        assert len(contacts_data) >= 1

        contact_id = contacts_data[0]["id"]
        assert contacts_data[0]["unread_count"] >= 1
        assert "latest_preview" in contacts_data[0]

        messages = client.get(f"/api/v1/contacts/{contact_id}/messages", headers=headers)
        assert messages.status_code == 200, messages.text
        msgs = messages.json()
        assert len(msgs) >= 1
        assert msgs[0]["summary"] is not None

        # Pagination via before_id should work (one message per sender in mock data).
        before = client.get(
            f"/api/v1/contacts/{contact_id}/messages?limit=50&before_id={msgs[0]['id']}",
            headers=headers,
        )
        assert before.status_code == 200, before.text
        assert before.json() == []

        # Mark-read should bulk update and drop unread count to 0.
        mark = client.post(f"/api/v1/contacts/{contact_id}/mark-read", headers=headers)
        assert mark.status_code == 200, mark.text
        assert mark.json()["marked"] >= 1

        contacts2 = client.get("/api/v1/contacts", headers=headers)
        assert contacts2.status_code == 200, contacts2.text
        updated = [c for c in contacts2.json() if c["id"] == contact_id][0]
        assert updated["unread_count"] == 0

        # Agent config defaults to rule_based and summarize works with auth.
        cfg = client.get("/api/v1/agent/config", headers=headers)
        assert cfg.status_code == 200, cfg.text
        assert cfg.json()["provider"] == "rule_based"
        assert cfg.json()["has_api_key"] is False
        assert cfg.json()["web_search_proxy_url"] == ""

        catalog = client.get("/api/v1/agent/catalog", headers=headers)
        assert catalog.status_code == 200, catalog.text
        assert isinstance(catalog.json().get("providers"), list)

        oauth_start = client.get("/api/v1/accounts/oauth/gmail/start", headers=headers)
        assert oauth_start.status_code == 400, oauth_start.text

        oauth_cfg = client.patch(
            "/api/v1/accounts/oauth/gmail/config",
            json={"client_id": "test-client-id.apps.googleusercontent.com", "client_secret": "test-client-secret"},
            headers=headers,
        )
        assert oauth_cfg.status_code == 200, oauth_cfg.text
        assert oauth_cfg.json()["configured"] is True

        oauth_cfg_get = client.get("/api/v1/accounts/oauth/gmail/config", headers=headers)
        assert oauth_cfg_get.status_code == 200, oauth_cfg_get.text
        assert oauth_cfg_get.json()["configured"] is True

        oauth_start2 = client.get("/api/v1/accounts/oauth/gmail/start", headers=headers)
        assert oauth_start2.status_code == 200, oauth_start2.text
        assert "accounts.google.com" in oauth_start2.json()["auth_url"]

        sm = client.post("/api/v1/agent/summarize", json={"text": "这是一封很长的邮件内容，用于测试摘要功能。"}, headers=headers)
        assert sm.status_code == 200, sm.text
        assert isinstance(sm.json().get("summary"), str)

        # Updating config should persist (no external call performed here).
        upd = client.patch(
            "/api/v1/agent/config",
            json={
                "provider": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test",
                "model": "openai/gpt-4o-mini",
                "temperature": 0.2,
                "web_search_proxy_url": "http://127.0.0.1:7890",
            },
            headers=headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["provider"] == "openrouter"
        assert upd.json()["has_api_key"] is True
        assert upd.json()["web_search_proxy_url"] == "http://127.0.0.1:7890"
