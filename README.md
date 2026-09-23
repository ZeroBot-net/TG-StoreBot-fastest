# TG-StoreBot-fastest

Fastest Telegram file store bot — private channel as storage, 10-digit deep links, sub-200ms end-to-end delivery.

## Overview

Send any media to the bot → it forwards it to a private channel → you get a 10-digit code and a deep link. Share the link — anyone can retrieve the file instantly via Telegram's `copyMessage` (no re-upload, no forwarding header).

**Design goal:** local processing under 5 ms, end-to-end dominated only by Telegram RTT.

## Features

- **Any media type** — photos, videos, documents, audio, animations, voice, video notes, stickers
- **10-digit deep links** — `https://t.me/YourBot?start=0000000042`
- **Instant retrieval** — `copyMessage` from storage channel, no re-upload
- **Multi-bot, one DB** — run N bot instances (different `BOT_TOKEN`s) against the same `DB_PATH`; SQLite WAL + `PRAGMA data_version` keeps every process's cache in sync
- **Multi-channel backup** — upload fans out to `CHANNEL_ID` + every `BACKUP_CHANNEL_IDS`; delivery falls back channel-by-channel if the primary copy is deleted
- **TTL auto-expire** — set at upload with a `/ttl 2h` caption prefix or later via `/expire <code> <dur|off>`; a background scanner deletes the message from **all** storage channels + the DB row. (Anything a user already forwarded/saved stays with them.)
- **Force-join gate** — `FORCE_JOIN_CHATS` must be joined before delivery — **no verified join, no file**. API errors are **double-checked** (one immediate retry); if still unverifiable the user is denied with join links + an "✅ I joined" button that re-verifies on tap. Re-opening the deep link also re-checks (negatives are never cached). Admins bypass.
- **User file management** — `/list`, `/delete`
- **Admin stats** — `/stats`
- **Latency logging** — every request logged to CSV for analysis
- **SQLite + WAL** — fast local storage with in-memory cache for O(1) lookups

## Architecture

```
┌──────────┐      send media        ┌───────────────────┐
│   User   │ ─────────────────────▶ │  Bot (aiogram ×N) │  ← N processes, same DB
└──────────┘                       └────────┬──────────┘
                                            │ forward (fan-out)
                     ┌──────────────────────┼──────────────────────┐
                     ▼                      ▼                      ▼
              ┌────────────┐        ┌──────────────┐       ┌──────────────┐
              │  SQLite    │        │   Primary    │       │   Backup     │
              │ WAL+cache  │        │   Channel    │       │  Channels    │  ← backup copies
              └────────────┘        └──────────────┘       └──────────────┘
                     │                      │
                     │   /start <code> → cache lookup → copyMessage (fallback chain)
                     └──────────────────────┘
```

1. User sends media → Bot forwards to **every** storage channel → stores `message_id` per channel + metadata in SQLite → replies with deep link (and TTL if caption starts `/ttl`).
2. User opens deep link → force-join gate (if configured) → cache lookup → `copyMessage` tries primary channel first, **falls back to backups** if the copy was deleted → latency logged.
3. Background scanner: expired rows are atomically claimed (safe with multiple bots) → messages deleted from **all** channels + DB row removed.

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
| `CHANNEL_ID` | **Yes** | — | Primary storage channel ID (negative, e.g. `-1001234567890`) |
| `ADMIN_IDS` | **Yes** | — | Comma-separated Telegram user IDs for admin access (bypass force-join, `/stats`) |
| `BACKUP_CHANNEL_IDS` | No | *(none)* | Comma-separated backup channel IDs — same file fanned out to all (redundancy) |
| `FORCE_JOIN_CHATS` | No | *(none)* | Comma-separated chats users must join first (`@name` or `-100…`) |
| `EXPIRY_SCAN_INTERVAL_S` | No | `30` | Background TTL scanner interval (seconds) |
| `DB_PATH` | No | `./data/store.db` | SQLite database path — **same path = shared DB across bot instances** (same machine/volume) |
| `LOG_LEVEL` | No | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LATENCY_LOG_FILE` | No | `./data/latency.log` | CSV file for latency records |

### Multi-bot setup

All instances share one SQLite file — run them on the **same machine or shared volume** with the same `DB_PATH` (SQLite over a network filesystem is unsafe). Each instance needs its own `BOT_TOKEN`; storage channels must have **every** bot added as admin:

```bash
# instance A
BOT_TOKEN=token_A DB_PATH=./data/store.db uv run python -m app.bot
# instance B — same DB, different token
BOT_TOKEN=token_B DB_PATH=./data/store.db uv run python -m app.bot
```

Writes from one process are seen by the others via `PRAGMA data_version` cache refresh; expiry claims are atomic (`DELETE … RETURNING`-style rowcount) so a file is never double-deleted.

## Commands

| Command | Description |
|---|---|
| `/start <code>` | Retrieve a stored file by its 10-digit code (force-join gate first, channel fallback on delivery) |
| `/list` | List all your stored files |
| `/delete <code>` | Delete a file you stored (owner only) |
| `/expire <code> <dur\|off>` | Set/clear auto-expiry, e.g. `/expire 1234567890 2h` (owner only) |
| `/help` | Show usage instructions |
| `/stats` | Bot statistics — file count, unique users (admin only) |
| `/ping` | Reply with local processing latency |
| *Send any media* | Upload & store — returns a 10-digit code + deep link |
| *Caption `/ttl 2h` + media* | Upload with auto-expiry after 2h |

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
