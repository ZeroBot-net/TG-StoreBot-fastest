"""Handle /list — show the user's stored files."""

from __future__ import annotations

import logging

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import db, get_bot_username, router

logger = logging.getLogger(__name__)

_MAX_DISPLAY = 50


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    """List all files stored by this user."""
    user_id = message.from_user.id if message.from_user else 0
    rows = db.list_user_files(user_id)

    if not rows:
        await message.answer(
            "📂 <b>No files stored.</b>\n\nSend me any file to get started!",
            parse_mode="HTML",
        )
        return

    try:
        username = await get_bot_username()
    except RuntimeError:
        username = "your_bot"

    truncated = len(rows) > _MAX_DISPLAY
    display_rows = rows[:_MAX_DISPLAY]

    lines = [f"📂 <b>Your files</b> ({len(rows)} total)\n"]
    for code, media_type, _caption, _created_at in display_rows:
        deep_link = f"https://t.me/{username}?start={code}"
        lines.append(
            f"• <code>{code}</code> ({media_type}) — "
            f"<a href=\"{deep_link}\">{deep_link}</a>"
        )

    if truncated:
        lines.append(f"\n… and {len(rows) - _MAX_DISPLAY} more (limit {_MAX_DISPLAY})")

    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
