"""Handle /stats — admin-only bot statistics."""

from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import db, router
from app.config import settings


@router.message(Command("stats"))
async def handle_stats(message: Message) -> None:
    """Show bot statistics — admin only."""
    user_id = message.from_user.id if message.from_user else 0

    if user_id not in settings.admin_ids:
        await message.answer("⛔ Admin only.", parse_mode="HTML")
        return

    s = db.stats()
    total_mb = round(s["total_bytes"] / (1024 * 1024), 2)

    await message.answer(
        "📊 <b>Bot Statistics</b>\n\n"
        f"Files: <code>{s['total_files']}</code>\n"
        f"Storage: <code>{total_mb}</code> MB\n"
        f"Uploaders: <code>{s['unique_users']}</code>",
        parse_mode="HTML",
    )
