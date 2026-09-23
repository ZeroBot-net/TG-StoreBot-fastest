"""Handle /ping — reply with local processing latency."""

from __future__ import annotations

import time

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import router


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    """Reply with local processing time in ms."""
    t0 = time.monotonic()
    ms = round((time.monotonic() - t0) * 1000, 1)
    await message.answer(f"🏓 Pong — handled in {ms:.1f}ms", parse_mode="HTML")
