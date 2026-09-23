"""Handle /help — usage and deep-link explanation."""

from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import Message

from app.bot import router

_HELP_TEXT = (
    "🗂 <b>File Store Bot</b>\n\n"
    "<b>How it works</b>\n"
    "1. Send me any file, photo, video, etc.\n"
    "2. I'll store it and give you a 10-digit code.\n"
    "3. Share the deep link — anyone can retrieve the file.\n\n"
    "<b>Commands</b>\n"
    "• /list — show your stored files\n"
    "• /delete <code>&lt;code&gt;</code> — remove a stored file\n"
    "• /stats — bot statistics (admin)\n"
    "• /ping — check bot responsiveness\n"
    "• /help — this message\n\n"
    "<b>Deep links</b>\n"
    "A link like <code>https://t.me/botname?start=1234567890</code> "
    "delivers the file directly when opened.\n\n"
    "💡 Works from any chat — just tap the link."
)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Handle /help."""
    await message.answer(_HELP_TEXT, parse_mode="HTML")
