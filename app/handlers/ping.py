"""Handle /ping — reply with local processing latency."""

from __future__ import annotations

import time

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import router


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    """Reply with a real DB round-trip time (the actual hot-path work)."""
    t0 = time.monotonic()
    from app.bot import db

    db.has_code("0000000000")  # cheapest real hot-path operation
    lookup_ms = (time.monotonic() - t0) * 1000
    await message.answer(
        f"🏓 Pong — cache lookup {lookup_ms:.2f}ms",
        parse_mode="HTML",
    )
