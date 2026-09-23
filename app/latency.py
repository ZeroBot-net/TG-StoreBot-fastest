"""Lightweight latency logger — one CSV line per request."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TextIO

from app.config import settings

logger = logging.getLogger("latency")

_handle: TextIO | None = None


def _get_handle() -> TextIO:
    """Return a lazily-opened append-mode file handle for the latency CSV."""
    global _handle  # noqa: PLW0603
    if _handle is None or _handle.closed:
        Path(settings.latency_log_file).parent.mkdir(parents=True, exist_ok=True)
        _handle = open(settings.latency_log_file, "a", encoding="utf-8")  # noqa: SIM115
    return _handle


def log_latency(code: str, t0: float, user_id: int, success: bool) -> None:
    """Compute latency in ms and append a CSV row. Never raises."""
    try:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
        level = logging.WARNING if elapsed_ms > 200 else logging.INFO
        logger.log(
            level,
            "latency=%.1fms code=%s user=%d success=%s",
            elapsed_ms,
            code,
            user_id,
            success,
        )

        fh = _get_handle()
        epoch_s = int(time.time())
        fh.write(f"{epoch_s},{code},{user_id},{elapsed_ms},{success}\n")
        fh.flush()
    except Exception:
        pass
