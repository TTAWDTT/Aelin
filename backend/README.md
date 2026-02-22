# MercuryDesk Backend

## Running

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

## Env

The backend uses SQLite by default (`backend/mercurydesk.db`).

Optional env vars:

- `MERCURYDESK_DATABASE_URL` (e.g. `postgresql+psycopg://...`)
- `MERCURYDESK_SECRET_KEY` (JWT signing key)
- `MERCURYDESK_FERNET_KEY` (encrypt stored secrets: OAuth tokens / IMAP passwords)
- `MERCURYDESK_CORS_ORIGINS` (comma-separated)
- `MERCURYDESK_MEDIA_DIR` (where uploaded avatars are stored; default `./media`)
- `MERCURYDESK_RSSHUB_BASE_URL` (RSSHub base URL, default `https://rsshub.app`)
- `MERCURYDESK_MODELS_CATALOG_URL` (model catalog source, default `https://models.dev/api.json`)
- `MERCURYDESK_MODELS_CATALOG_REFRESH_SECONDS` (catalog cache TTL, default `3600`)
- `MERCURYDESK_LLM_REQUEST_TIMEOUT_SECONDS` (LLM request timeout, default `90`)
- `MERCURYDESK_MEDIA_INGEST_COOKIE_MODE` (`off`/`browser`/`file`, default `off`)
- `MERCURYDESK_MEDIA_INGEST_COOKIE_BROWSER` (when mode=`browser`, default `chrome`)
- `MERCURYDESK_MEDIA_INGEST_COOKIE_BROWSER_PROFILE` (optional browser profile, e.g. `Default`)
- `MERCURYDESK_MEDIA_INGEST_COOKIE_FILE` (when mode=`file`, Netscape cookie file path)
- `MERCURYDESK_MEDIA_INGEST_PROXY_URL` (optional proxy for yt-dlp)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_AUTO_LOGIN_ENABLED` (enable Douyin auto login guidance, default `true`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_BROWSER_PROFILE_DIR` (persistent Chromium profile dir for Douyin, default `./browser_data/douyin_media`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_LOGIN_URL` (login page opened by guidance flow, default `https://www.douyin.com/`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_ENABLED` (enable Douyin audio ASR fallback, default `true`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_BACKEND` (`auto`/`faster_whisper`/`openai`, default `auto`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_MODEL` (audio transcription model, default `whisper-1`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_LOCAL_MODEL` (local faster-whisper model, default `small`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_LOCAL_DEVICE` (`auto`/`cpu`/`cuda`, default `auto`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_LOCAL_COMPUTE_TYPE` (local faster-whisper compute type, default `int8`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_LOCAL_BEAM_SIZE` (local faster-whisper beam size, default `4`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_MAX_AUDIO_SECONDS` (max audio segment length for ASR, default `120`)
- `MERCURYDESK_MEDIA_INGEST_DOUYIN_ASR_TIMEOUT_SECONDS` (ffmpeg extraction timeout for ASR, default `80`)
- `MERCURYDESK_OAUTH_REDIRECT_BASE_URL` (OAuth callback base URL, default `http://127.0.0.1:8000`)
- `MERCURYDESK_GMAIL_CLIENT_ID` / `MERCURYDESK_GMAIL_CLIENT_SECRET`
- `MERCURYDESK_OUTLOOK_CLIENT_ID` / `MERCURYDESK_OUTLOOK_CLIENT_SECRET`
- `MERCURYDESK_GITHUB_CLIENT_ID` / `MERCURYDESK_GITHUB_CLIENT_SECRET`
