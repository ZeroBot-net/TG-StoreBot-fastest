"""Bot configuration loaded from environment / .env file."""

from __future__ import annotations

import json as _json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


def _parse_int_list(v: str | list[int]) -> list[int]:
    """Accept comma-separated, JSON array, or real list — strip to int."""
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        if s.startswith("["):
            return [int(x) for x in _json.loads(s)]
        return [int(x.strip()) for x in s.split(",") if x.strip()]
    return v


def _parse_str_list(v: str | list[str]) -> list[str]:
    """Accept comma-separated, JSON array, or real list — keep stripped strings."""
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        if s.startswith("["):
            return [x.strip() for x in _json.loads(s) if x.strip()]
        return [x.strip() for x in s.split(",") if x.strip()]
    return v


class Settings(BaseSettings):
    """Application settings — populated from env vars or a `.env` file."""

    bot_token: str
    channel_id: int
    # NoDecode: accept "1,2,3" (our format) instead of forcing a JSON array.
    admin_ids: Annotated[list[int], NoDecode]
    db_path: str = "./data/store.db"
    log_level: str = "INFO"
    # Empty = console-only logging; otherwise also append logs to this file.
    log_file: str = "./data/bot.log"
    latency_log_file: str = "./data/latency.log"

    # --- new fields ---
    backup_channel_ids: Annotated[list[int], NoDecode] = []
    force_join_chats: Annotated[list[str], NoDecode] = []
    # TTL scanner interval in MINUTES: 0 = auto-expire disabled entirely,
    # 1 = sweep every minute, 30 = sweep every 30 minutes.
    expiry_scan_interval_m: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # -- validators --------------------------------------------------------

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: str | list[int]) -> list[int]:
        """Accept comma-separated ("1,2,3"), JSON ("[1,2,3]"), or a real list."""
        return _parse_int_list(v)

    @field_validator("backup_channel_ids", mode="before")
    @classmethod
    def _parse_backup_channel_ids(cls, v: str | list[int]) -> list[int]:
        return _parse_int_list(v)

    @field_validator("force_join_chats", mode="before")
    @classmethod
    def _parse_force_join_chats(cls, v: str | list[str]) -> list[str]:
        return _parse_str_list(v)

    # -- properties --------------------------------------------------------

    @property
    def storage_channel_ids(self) -> list[int]:
        """Primary + backup channel ids, deduped preserving order."""
        seen: set[int] = set()
        out: list[int] = []
        for cid in (self.channel_id, *self.backup_channel_ids):
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
        return out


settings = Settings()
