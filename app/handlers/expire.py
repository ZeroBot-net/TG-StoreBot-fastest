"""Handle /expire — set or clear file expiry."""

from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import db, router
from app.util import format_duration, iso_in, parse_duration


@router.message(Command("expire"))
async def handle_expire(message: Message) -> None:
    """Set or clear file expiry.  Usage: ``/expire <code> <duration|off>``."""
    user_id = message.from_user.id if message.from_user else 0

    text = message.text or ""
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Usage:\n"
            "<code>/expire 1234567890 2h</code>\n"
            "<code>/expire 1234567890 off</code>",
            parse_mode="HTML",
        )
        return

    code = parts[1].strip()
    duration_str = parts[2].strip()

    # --- clear expiry ---
    if duration_str.lower() == "off":
        if db.set_expire(code, user_id, None):
            await message.answer(
                f"✅ Expiry cleared for <code>{code}</code>.",
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Not found or not yours.", parse_mode="HTML")
        return

    # --- set expiry ---
    seconds = parse_duration(duration_str)
    if seconds is None:
        await message.answer(
            "❌ Invalid duration. Use formats like <code>30s</code>, "
            "<code>5m</code>, <code>2h</code>, <code>7d</code>.",
            parse_mode="HTML",
        )
        return

    expires_at = iso_in(seconds)
    if db.set_expire(code, user_id, expires_at):
        await message.answer(
            f"⏳ Expires at <code>{expires_at}</code> UTC "
            f"(in {format_duration(seconds)})",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Not found or not yours.", parse_mode="HTML")
