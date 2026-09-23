"""Handle incoming media — forward to channel, generate code, reply with deep link."""

from __future__ import annotations

import logging
import random

from aiogram import F
from aiogram.types import Message

from app.bot import db, get_bot_username, router
from app.config import settings

logger = logging.getLogger(__name__)

_CODE_LENGTH = 10
_MAX_CODE_ATTEMPTS = 20


def _detect_media_type(message: Message) -> str:
    """Return a human-readable media type string."""
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    if message.animation:
        return "animation"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    return "unknown"


def _extract_file_id(message: Message) -> str:
    """Extract the file_id from a media message."""
    if message.photo:
        # Photo is a list of sizes — use the largest (last element).
        return message.photo[-1].file_id
    if message.video:
        return message.video.file_id
    if message.document:
        return message.document.file_id
    if message.audio:
        return message.audio.file_id
    if message.animation:
        return message.animation.file_id
    if message.voice:
        return message.voice.file_id
    if message.video_note:
        return message.video_note.file_id
    if message.sticker:
        return message.sticker.file_id
    return ""


def _extract_file_size(message: Message) -> int | None:
    """Extract the file size in bytes, or None if unavailable."""
    if message.photo:
        return message.photo[-1].file_size
    if message.video:
        return message.video.file_size
    if message.document:
        return message.document.file_size
    if message.audio:
        return message.audio.file_size
    if message.animation:
        return message.animation.file_size
    if message.voice:
        return message.voice.file_size
    if message.video_note:
        return message.video_note.file_size
    if message.sticker:
        return message.sticker.file_size
    return None


def _generate_code() -> str:
    """Generate a random 10-digit numeric code."""
    return "".join(random.choices("0123456789", k=_CODE_LENGTH))


# Note: media_group messages arrive as individual items — each gets its own code.
@router.message(
    F.photo
    | F.video
    | F.document
    | F.audio
    | F.animation
    | F.voice
    | F.video_note
    | F.sticker
)
async def handle_media(message: Message) -> None:
    """Store any media message: forward to channel, generate code, reply."""
    user_id = message.from_user.id if message.from_user else 0

    # Forward the media to the storage channel.
    try:
        forwarded = await message.bot.forward_message(
            chat_id=settings.channel_id,
            from_chat_id=user_id,
            message_id=message.message_id,
        )
    except Exception:
        logger.exception("forward_message failed for user=%d", user_id)
        await message.answer("⚠️ Failed to store file.", parse_mode="HTML")
        return

    media_type = _detect_media_type(message)
    file_id = _extract_file_id(message)
    file_size = _extract_file_size(message)
    caption = message.caption

    # Generate a unique 10-digit code.
    code = _generate_code()
    attempts = 0
    while db.has_code(code) and attempts < _MAX_CODE_ATTEMPTS:
        code = _generate_code()
        attempts += 1

    if db.has_code(code):
        logger.error("could not generate unique code after %d attempts", _MAX_CODE_ATTEMPTS)
        await message.answer("⚠️ Storage error — try again.", parse_mode="HTML")
        return

    db.store(
        code=code,
        message_id=forwarded.message_id,
        media_type=media_type,
        file_id=file_id,
        user_id=user_id,
        caption=caption,
        file_size=file_size,
    )

    try:
        username = await get_bot_username()
    except RuntimeError:
        username = "your_bot"

    deep_link = f"https://t.me/{username}?start={code}"

    await message.answer(
        "✅ <b>Stored!</b>\n\n"
        f"📎 Type: <code>{media_type}</code>\n"
        f"🔑 Code: <code>{code}</code>\n"
        f"🔗 <a href=\"{deep_link}\">{deep_link}</a>\n\n"
        "📤 Share the link to let others download this file.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    logger.info("stored code=%s media=%s user=%d", code, media_type, user_id)
