"""Handle incoming media — fan out to storage channels, generate code, reply with deep link."""

from __future__ import annotations

import contextlib
import logging
import secrets
import sqlite3

from aiogram import F
from aiogram.types import Message

from app.bot import db, get_bot_username, router
from app.config import settings
from app.util import format_expiry_display, iso_in, parse_duration

logger = logging.getLogger(__name__)

_CODE_LENGTH = 10
_MAX_CODE_ATTEMPTS = 20
_MAX_STORE_RETRIES = 5
_TTL_PREFIX = "/ttl "


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
    """Generate a random 10-digit numeric code (CSPRNG — unguessable)."""
    return "".join(secrets.choice("0123456789") for _ in range(_CODE_LENGTH))


def default_expiry() -> str | None:
    """Default TTL applied when the caption carries no explicit /ttl.

    ``DEFAULT_TTL_DAYS=7`` (default) → expires in 1 week;
    ``0`` → never expires.
    """
    days = settings.default_ttl_days
    return iso_in(days * 86400) if days > 0 else None


def _parse_ttl_caption(caption: str | None) -> tuple[str | None, str | None, str | None]:
    """Split a ``/ttl <duration>`` caption prefix.

    Returns ``(expires_at, stripped_caption, error)``.
    """
    if not caption:
        return None, caption, None

    stripped = caption.strip()
    if not stripped.lower().startswith("/ttl"):
        return None, caption, None

    tokens = stripped.split(maxsplit=1)
    rest = tokens[1].strip() if len(tokens) > 1 else ""

    # "/ttl" with no duration -> error
    if not rest:
        return None, caption, "missing duration"

    # First token is the duration; remainder is the real caption.
    dur_token, _, remainder = rest.partition(" ")
    seconds = parse_duration(dur_token)
    if seconds is None:
        return None, caption, f"invalid duration: {dur_token}"

    new_caption = remainder.strip() or None
    return iso_in(seconds), new_caption, None


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
    """Store any media: fan out to all storage channels, generate code, reply."""
    user_id = message.from_user.id if message.from_user else 0

    # --- TTL from caption ---------------------------------------------------
    expires_at, caption, ttl_error = _parse_ttl_caption(message.caption)
    if ttl_error:
        await message.answer(
            f"⚠️ TTL ignored ({ttl_error}). Use e.g. <code>/ttl 2h</code> "
            "as the start of your caption.",
            parse_mode="HTML",
        )
    explicit_ttl = expires_at is not None
    if expires_at is None:
        # No valid /ttl in caption → apply DEFAULT_TTL_DAYS (7 = 1 week).
        expires_at = default_expiry()

    # --- Fan out to primary + backup channels (redundancy) -------------
    # copy_message (not forward_message): no "Forwarded from" header in the
    # storage channels — keeps the uploader anonymous.
    channels = settings.storage_channel_ids
    stored: list[tuple[int, int]] = []  # (channel_id, message_id)
    for ch in channels:
        try:
            fwd = await message.bot.copy_message(
                chat_id=ch,
                from_chat_id=user_id,
                message_id=message.message_id,
            )
            stored.append((ch, fwd.message_id))
        except Exception:
            logger.exception("copy_message failed ch=%d user=%d", ch, user_id)

    if not stored:
        await message.answer("⚠️ Failed to store file.", parse_mode="HTML")
        return

    if len(stored) < len(channels):
        missing = len(channels) - len(stored)
        logger.warning("stored to %d/%d channels (%d failed)", len(stored), len(channels), missing)

    media_type = _detect_media_type(message)
    file_id = _extract_file_id(message)
    file_size = _extract_file_size(message)
    primary_ch, primary_mid = stored[0]

    # --- Generate unique code + store (retry on cross-process collision) ----
    code = _generate_code()
    stored_row = False
    for _attempt in range(_MAX_STORE_RETRIES):
        if db.has_code(code):
            code = _generate_code()
            continue
        try:
            db.store(
                code,
                primary_mid,
                media_type,
                file_id,
                user_id,
                caption=caption,
                file_size=file_size,
                channel_id=primary_ch,
                expires_at=expires_at,
            )
            stored_row = True
            break
        except sqlite3.IntegrityError:
            # Another bot process claimed this code between has_code + store.
            code = _generate_code()

    if not stored_row:
        logger.error("could not generate unique code after %d retries", _MAX_STORE_RETRIES)
        # Clean up orphaned channel copies — no DB row = unusable messages.
        for ch, mid in stored:
            with contextlib.suppress(Exception):
                await message.bot.delete_message(ch, mid)
        await message.answer("⚠️ Storage error — try again.", parse_mode="HTML")
        return

    # Register backup channel copies for backup fallback delivery.
    for ch, mid in stored[1:]:
        db.add_channel(code, ch, mid)

    username = await get_bot_username() or "your_bot"
    deep_link = f"https://t.me/{username}?start={code}"

    ttl_line = ""
    if expires_at:
        suffix = "" if explicit_ttl else " (default)"
        shown = format_expiry_display(expires_at, settings.tz)
        ttl_line = f"\n⏳ Expires: <code>{shown}</code>{suffix}"

    await message.answer(
        "✅ <b>Stored!</b>\n\n"
        f"📎 Type: <code>{media_type}</code>\n"
        f"🔑 Code: <code>{code}</code>\n"
        f"🌍 Channels: {len(stored)}/{len(channels)}\n"
        + ttl_line
        + f"\n🔗 <a href=\"{deep_link}\">{deep_link}</a>\n\n"
        "📤 Share the link to let others download this file.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    logger.info(
        "stored code=%s media=%s user=%d channels=%d expires=%s",
        code,
        media_type,
        user_id,
        len(stored),
        expires_at or "-",
    )
