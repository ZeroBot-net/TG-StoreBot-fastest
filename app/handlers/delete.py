"""Handle /delete — remove a stored file by code (owner only)."""

from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import db, router


@router.message(Command("delete"))
async def handle_delete(message: Message) -> None:
    """Delete a file by code. Only the owner can delete."""
    user_id = message.from_user.id if message.from_user else 0

    text = message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Usage: <code>/delete &lt;code&gt;</code>",
            parse_mode="HTML",
        )
        return

    code = parts[1].strip()

    if db.delete(code, user_id):
        await message.answer(f"🗑️ Deleted <code>{code}</code>.", parse_mode="HTML")
    else:
        await message.answer("❌ Not found or not yours.", parse_mode="HTML")
