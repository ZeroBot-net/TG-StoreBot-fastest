"""Bot configuration loaded from environment / .env file."""

from __future__ import annotations

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Application settings — populated from env vars or a `.env` file."""

    bot_token: str
    channel_id: int
    # NoDecode: accept "1,2,3" (our format) instead of forcing a JSON array.
    admin_ids: Annotated[list[int], NoDecode]
    db_path: str = "./data/store.db"
    log_level: str = "INFO"
    latency_log_file: str = "./data/latency.log"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: str | list[int]) -> list[int]:
        """Accept comma-separated ("1,2,3"), JSON ("[1,2,3]"), or a real list."""
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                import json

                return [int(x) for x in json.loads(s)]
            return [int(x.strip()) for x in s.split(",") if x.strip()]
        return v


settings = Settings()
