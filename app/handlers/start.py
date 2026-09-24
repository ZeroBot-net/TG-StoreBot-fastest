"""Handle /start — deliver stored files via deep-link payload."""

from __future__ import annotations

import logging
import time

from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import db, router
from app.deliver import deliver_file
from app.forcejoin import ensure_joined
from app.latency import log_latency

logger = logging.getLogger(__name__)


@router.message(CommandStart(deep_link=True))
async def handle_start_with_payload(message: Message) -> None:
    """Deliver file from a deep-link payload: /start <10-digit code>."""
    await _handle_start(message)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Welcome / delivery entry point."""
    await _handle_start(message)


async def _handle_start(message: Message) -> None:
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

    if not db.has_code(code):
        await message.answer("❌ File not found.", parse_mode="HTML")
        log_latency(code, t0, user_id, success=False)
        return

    # --- Force-join gate: no verified join, no access (double-checked) -----
    bot = message.bot
    ok, urls = await ensure_joined(bot, user_id)
    if not ok:
        # Buttons: join links two-per-row, then a single retry button.
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(text="📢 Join", url=u)
                for u in urls[i : i + 2]
            ]
            for i in range(0, len(urls), 2)
        ]
        rows.append(
            [InlineKeyboardButton(text="✅ I joined", callback_data=f"join:{code}")]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        links = "\n".join(f"• <a href=\"{u}\">{u}</a>" for u in urls)
        await message.answer(
            "🔒 <b>Join required</b>\n\n"
            f"{links}\n\n"
            "Join kore niche <b>I joined</b> e tap koro.",
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        log_latency(code, t0, user_id, success=False)
        return

    # --- Deliver with multi-channel fallback (backup channels) -------------
    status = await deliver_file(bot, user_id, code)

    if status == "ok":
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        logger.info("delivered code=%s user=%d in %.1fms", code, user_id, latency_ms)
        log_latency(code, t0, user_id, success=True)
    elif status == "not_found":
        await message.answer("❌ File not found.", parse_mode="HTML")
        log_latency(code, t0, user_id, success=False)
    else:
        await message.answer("⚠️ Delivery failed. Try again later.", parse_mode="HTML")
        log_latency(code, t0, user_id, success=False)
