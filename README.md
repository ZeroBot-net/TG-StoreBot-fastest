# TG-StoreBot-fastest

Fastest Telegram file store bot — private channel as storage, 10-digit deep links, sub-200ms end-to-end delivery.

## Overview

Send any media to the bot → it forwards it to a private channel → you get a 10-digit code and a deep link. Share the link — anyone can retrieve the file instantly via Telegram's `copyMessage` (no re-upload, no forwarding header).

**Design goal:** local processing under 5 ms, end-to-end dominated only by Telegram RTT.

## Features

- **Any media type** — photos, videos, documents, audio, animations, voice, video notes, stickers
- **10-digit deep links** — `https://t.me/YourBot?start=0000000042`
- **Instant retrieval** — `copyMessage` from the private channel, no re-upload
- **User file management** — `/list`, `/delete`
- **Admin stats** — `/stats`
- **Latency logging** — every request logged to CSV for analysis
- **SQLite + WAL** — fast local storage with in-memory cache for O(1) lookups

## Architecture

```
┌──────────┐      send media       ┌──────────────┐
│   User   │ ─────────────────────▶│   Bot (aiogram)│
└──────────┘                       └──────┬───────┘
                                          │
                            ┌─────────────┼─────────────┐
                            ▼             ▼              ▼
                     ┌────────────┐ ┌──────────┐ ┌──────────────┐
                     │  SQLite    │ │  Private │ │  Latency     │
                     │  (cache)   │ │  Channel │ │  CSV Log     │
                     └────────────┘ └──────────┘ └──────────────┘
                            │             │
                            │   copyMessage on /start <code>
                            └─────────────┘
```

1. User sends media → Bot forwards to private channel → Bot stores `message_id` + metadata in SQLite → replies with deep link.
2. User opens deep link → Bot looks up `message_id` from SQLite cache → `copyMessage` from private channel to user.

## Setup

1. **Get a bot token** from [@BotFather](https://t.me/BotFather).
2. **Create a private channel**, add the bot as an admin (with "Post messages" permission). Copy the `CHANNEL_ID` (negative number like `-1001234567890`).
3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env — fill in BOT_TOKEN, CHANNEL_ID, ADMIN_IDS
   ```
4. **Install dependencies:**
   ```bash
   uv sync
   ```
5. **Run the bot:**
   ```bash
   uv run python -m app.bot
   ```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | **Yes** | — | Telegram bot token from @BotFather |
| `CHANNEL_ID` | **Yes** | — | Private channel ID (negative, e.g. `-1001234567890`) |
| `ADMIN_IDS` | **Yes** | — | Comma-separated Telegram user IDs for admin access |
| `DB_PATH` | No | `./data/store.db` | SQLite database path (`:memory:` for testing) |
| `LOG_LEVEL` | No | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LATENCY_LOG_FILE` | No | `./data/latency.log` | CSV file for latency records |

## Commands

| Command | Description |
|---|---|
| `/start <code>` | Retrieve a stored file by its 10-digit code |
| `/list` | List all your stored files |
| `/delete <code>` | Delete a file you stored (owner only) |
| `/help` | Show usage instructions |
| `/stats` | Bot statistics — file count, unique users (admin only) |
| `/ping` | Reply with local processing latency |
| *Send any media* | Upload & store — returns a 10-digit code + deep link |

## Latency

- **Local processing target:** < 5 ms (in-memory cache lookup + DB write)
- **End-to-end:** dominated by Telegram API RTT (typically 50–200 ms)
- **Measurement:** every `copyMessage` / storage event is logged to the latency CSV

### CSV format (`latency.log`)

```
epoch,code,user_id,latency_ms,success
```

| Field | Type | Description |
|---|---|---|
| `epoch` | int | Unix timestamp (seconds) |
| `code` | str | 10-digit file code |
| `user_id` | int | Telegram user ID |
| `latency_ms` | float | Processing time in milliseconds |
| `success` | bool | `True` if file was delivered/stored successfully |

## Development

```bash
# Run tests
uv run pytest tests/ -q

# Lint
uv run ruff check .

# Benchmark (100k inserts + 200k lookups)
uv run python scripts/benchmark.py
```
