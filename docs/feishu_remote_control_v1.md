# Feishu Remote Control V1

## Overview

This document describes the current `feature/remote-control` implementation.

Goal:

- send a command from a phone through a Feishu bot
- receive the command on the local Aelin backend through Feishu long connection
- execute a validated desktop action on the computer
- send the result back to the same Feishu chat

This V1 does not allow arbitrary shell execution. Only a fixed command set is supported.

## Supported Commands

Private chat examples:

- `help`
- `status`
- `screenshot`
- `top cpu 5`
- `processes memory 8`
- `mode focus`
- `mode normal`
- `open Aelin`
- `open url https://example.com`

Group chat examples:

- `/aelin status`
- `/aelin screenshot`

Notes:

- Group chat requires the configured prefix by default.
- Default prefix: `/aelin`

## Architecture

Backend:

- `backend/app/services/feishu_bot.py`
  - owns the Feishu long connection
  - receives message events
  - replies back to Feishu chats
- `backend/app/services/remote_control.py`
  - parses text commands
  - validates the whitelisted command set
  - stores execution history in `remote_commands`
- `backend/app/routers/aelin_remote_control.py`
  - local status endpoint
  - local execute endpoint
  - command history endpoint
- `backend/app/services/device_center.py`
  - bridges backend actions to the local desktop plugin

Desktop:

- `desktop/src/main.cjs`
  - exposes the local desktop plugin API
  - screen capture
  - open URL
  - activate the Aelin window

## Feishu App Setup

### 1. Create the app

In Feishu Open Platform:

1. Create a self-built app.
2. Enable the bot capability.
3. Copy `App ID` and `App Secret`.

### 2. Configure long connection

In the Feishu app console:

1. Open the events page.
2. Select long connection mode.
3. Make sure the local backend is already running.
4. Save the long connection configuration.

Important:

- This implementation does not need a public webhook URL.
- Feishu only lets you save long connection mode after it detects a live client connection from the local app.

### 3. Add the message event

Add this event:

- `im.message.receive_v1`

### 4. Grant minimum permissions

Required permissions:

- `im:message:p2p_msg:readonly`
  - read private chat messages sent to the bot
- `im:message:send_as_bot`
  - send replies as the bot

Optional later:

- group message read permissions if you want to use the bot in group chats

### 5. Publish the app

After events and permissions are ready:

1. create an app version
2. publish it inside the tenant
3. add the bot to a private chat or test group

## Local Configuration

### 1. Install backend dependencies

```powershell
cd backend
python -m pip install -r requirements.txt
```

### 2. Configure backend env

Use `backend/.env` or environment variables.

Minimum Feishu configuration:

```dotenv
MERCURYDESK_FEISHU_BOT_ENABLED=true
MERCURYDESK_FEISHU_APP_ID=cli_xxx
MERCURYDESK_FEISHU_APP_SECRET=your_secret
MERCURYDESK_FEISHU_BOT_WORKSPACE=default
MERCURYDESK_FEISHU_BOT_COMMAND_PREFIX=/aelin
MERCURYDESK_FEISHU_BOT_GROUP_REQUIRE_PREFIX=true
MERCURYDESK_FEISHU_BOT_ALLOWED_OPEN_IDS_CSV=
MERCURYDESK_FEISHU_BOT_ALLOWED_CHAT_IDS_CSV=
MERCURYDESK_FEISHU_BOT_BIND_USER_EMAIL=
```

Recommended hardening:

- rotate the secret immediately if it was ever exposed
- set `MERCURYDESK_FEISHU_BOT_ALLOWED_OPEN_IDS_CSV` for sender allowlisting
- set `MERCURYDESK_FEISHU_BOT_ALLOWED_CHAT_IDS_CSV` if chat-level allowlisting is needed

## Startup

### Backend-only mode

Use this to verify Feishu connectivity and backend-side commands such as `status`.

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Full desktop mode

Use this for screenshot, opening URLs, and activating the desktop window.

Frontend dependencies:

```powershell
cd frontend
npm install
```

Desktop dependencies:

```powershell
cd desktop
npm install
```

Start the desktop runtime:

```powershell
cd desktop
npm run dev
```

When Electron starts, it also starts the backend with the desktop plugin endpoint injected into backend env.

## Validation Checklist

### Step 1. Verify Feishu connectivity

In a private chat with the bot, send:

```text
status
```

Expected:

- the bot replies
- desktop plugin may still be reported as unavailable if Electron is not running yet

### Step 2. Verify desktop plugin connectivity

After Electron is running, send:

```text
status
```

Expected:

- desktop plugin is reported as online

### Step 3. Verify functional commands

Recommended order:

```text
top cpu 5
mode focus
mode normal
screenshot
open Aelin
open url https://example.com
```

Expected:

- `top cpu 5`: returns top processes
- `mode focus`: applies focus mode
- `mode normal`: restores the normal mode
- `screenshot`: returns screenshot metadata and local saved path
- `open Aelin`: activates the Electron app window
- `open url ...`: opens the system browser

## Local APIs

Useful local endpoints:

- `GET /api/v1/aelin/remote-control/status`
- `POST /api/v1/aelin/remote-control/execute`
- `GET /api/v1/aelin/remote-control/commands`

## Troubleshooting

### Long connection cannot be saved in Feishu

Check:

1. backend is running
2. `MERCURYDESK_FEISHU_BOT_ENABLED=true`
3. `App ID` and `App Secret` are correct
4. `lark-oapi` is installed

### Bot receives nothing

Check:

1. app has been published
2. `im.message.receive_v1` has been added
3. the bot is in the chat
4. private chat is tested first

### Bot replies but screenshot/open actions fail

Check:

1. Electron desktop runtime is running
2. `status` shows the desktop plugin as online

### Group chat commands are ignored

By default, group chat requires the prefix:

```text
/aelin status
```

## Current Limitations

- command set is intentionally small and whitelisted
- screenshot currently returns metadata and a local saved path, not an image upload to Feishu
- no arbitrary shell execution
- group chat support depends on additional Feishu permissions if needed later

