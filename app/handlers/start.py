"""Handle /start — deliver stored files via deep-link payload."""

from __future__ import annotations

import logging
import time

from aiogram import F
from aiogram.types import Message

from app.bot import db, router
from app.config import settings
from app.latency import log_latency

logger = logging.getLogger(__name__)


@router.message(F.text.startswith("/start"))
async def handle_start(message: Message) -> None:
    """Deliver file on deep link, or show welcome when no payload."""
    t0 = time.monotonic()
    user_id = message.from_user.id if message.from_user else 0

    text = message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "🗂 <b>File Store Bot</b>\n\n"
            "Send me any file and I'll give you a shareable link.\n\n"
            "💡 Open a deep link like <code>/start 1234567890</code> to retrieve a file.",
            parse_mode="HTML",
        )
        return

    code = parts[1].strip()

    if len(code) != 10 or not code.isdigit():
        await message.answer("❌ Invalid code.", parse_mode="HTML")
        log_latency(code, t0, user_id, success=False)
        return

    cached = db.get(code)
    if cached is None:
        await message.answer("❌ File not found.", parse_mode="HTML")
        log_latency(code, t0, user_id, success=False)
        return

    # No awaits between lookup and copy — keeps latency minimal.
    try:
        await message.bot.copy_message(
            chat_id=user_id,
            from_chat_id=settings.channel_id,
            message_id=cached.message_id,
        )
    except Exception:
        logger.exception("copy_message failed for code=%s user=%d", code, user_id)
        await message.answer("⚠️ Delivery failed. Try again later.", parse_mode="HTML")
        log_latency(code, t0, user_id, success=False)
        return

    latency_ms = round((time.monotonic() - t0) * 1000, 2)
    logger.info("delivered code=%s user=%d in %.1fms", code, user_id, latency_ms)
    log_latency(code, t0, user_id, success=True)
