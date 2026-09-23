"""Shared file delivery logic with multi-channel backup fallback."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.bot import db
from app.config import settings

logger = logging.getLogger(__name__)


async def deliver_file(bot: Bot, chat_id: int, code: str) -> str:
    """Deliver a stored file to *chat_id* by *code*.

    Tries every known channel in order (primary → backups).  Returns
    ``"ok"``, ``"not_found"``, or ``"failed"``.
    """
    cached = db.get(code)
    if cached is None:
        return "not_found"

    # Build ordered attempt list from the per-code channel list, falling
    # back to legacy single-channel fields for old rows.
    attempts: list[tuple[int, int]] = list(cached.channels) if cached.channels else []
    if not attempts:
        if cached.channel_id is not None:
            attempts = [(cached.channel_id, cached.message_id)]
        else:
            attempts = [(settings.channel_id, cached.message_id)]

    for ch, mid in attempts:
        try:
            await bot.copy_message(chat_id=chat_id, from_chat_id=ch, message_id=mid)
            return "ok"
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning("deliver failed ch=%s mid=%s code=%s: %s", ch, mid, code, exc)
        except Exception as exc:
            logger.warning("deliver failed ch=%s mid=%s code=%s: %s", ch, mid, code, exc)

    return "failed"
