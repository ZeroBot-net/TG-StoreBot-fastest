"""Force channel-join gate — no join, no access. Failures are double-checked."""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot, F
from aiogram.types import CallbackQuery

from app.bot import router
from app.config import settings
from app.deliver import deliver_file

logger = logging.getLogger(__name__)

# Cache: (user_id, chat) -> (joined_ok, monotonic_expiry)
# POSITIVE results only — a negative must always be re-checked (double check).
_join_cache: dict[tuple[int, str], tuple[bool, float]] = {}
_CACHE_TTL = 300.0
_RETRY_DELAY_S = 0.3


async def _check_member(bot: Bot, chat: str, user_id: int) -> bool | None:
    """Single membership check. Returns True/False, or None on API error."""
    try:
        member = await bot.get_chat_member(chat_id=chat, user_id=user_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return None


async def ensure_joined(bot: Bot, user_id: int) -> tuple[bool, list[str]]:
    """Check whether *user_id* has joined every ``force_join_chats`` entry.

    Strict policy — **no verified join, no access**:
    - admins bypass (they manage the channels),
    - positive results are cached for 5 min,
    - an API error triggers an immediate **double-check** (second attempt);
      if that also fails the user is DENIED (fail-closed) with the join
      links + retry button — never delivered on an unverified check.

    Returns ``(all_joined, list_of_join_urls)``.
    """
    chats = settings.force_join_chats
    if not chats:
        return True, []

    if user_id in settings.admin_ids:
        return True, []

    now = time.monotonic()
    all_joined = True
    urls: list[str] = []

    for chat in chats:
        cache_key = (user_id, chat)
        cached = _join_cache.get(cache_key)

        if cached is not None and cached[1] > now:
            joined = cached[0]
        else:
            joined = await _check_member(bot, chat, user_id)
            if joined is None:
                # Double-check: transient API errors must not grant access.
                await asyncio.sleep(_RETRY_DELAY_S)
                rechecked = await _check_member(bot, chat, user_id)
                if rechecked is None:
                    logger.warning(
                        "membership double-check failed chat=%s user=%d — denying",
                        chat,
                        user_id,
                    )
                    joined = False  # fail-closed: unverified = not joined
                else:
                    joined = rechecked

            # Cache POSITIVE results only — negatives are always re-checked
            # when the user re-opens the link after joining.
            if joined:
                _join_cache[cache_key] = (True, now + _CACHE_TTL)

        if not joined:
            all_joined = False
            url = await _build_join_url(bot, chat)
            if url:
                urls.append(url)

    return all_joined, urls


def invalidate(user_id: int) -> None:
    """Clear cache entries for *user_id* (called after they tap 'I joined')."""
    keys = [k for k in _join_cache if k[0] == user_id]
    for k in keys:
        del _join_cache[k]


async def _build_join_url(bot: Bot, chat: str) -> str | None:
    """Return a join URL for *chat*, or ``None`` on failure."""
    if chat.startswith("@"):
        return f"https://t.me/{chat[1:]}"
    try:
        chat_obj = await bot.get_chat(chat)
        if chat_obj.invite_link:
            return chat_obj.invite_link
        if chat_obj.username:
            return f"https://t.me/{chat_obj.username}"
    except Exception:
        logger.warning("get_chat failed for %s", chat)
    return None


# ---------------------------------------------------------------------------
# Callback handler — registered on the shared router at import time.
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("join:"))
async def handle_join_callback(callback: CallbackQuery) -> None:
    """Re-check membership after the user taps '✅ I joined'."""
    user_id = callback.from_user.id if callback.from_user else 0
    data = callback.data or ""
    code = data.split(":", 1)[1] if ":" in data else ""

    if not code:
        await callback.answer("Invalid callback data.", show_alert=True)
        return

    invalidate(user_id)

    bot = callback.bot
    assert bot is not None

    ok, urls = await ensure_joined(bot, user_id)

    if ok:
        status = await deliver_file(bot, user_id, code)
        if status == "ok":
            await callback.answer("✅ Joined! File delivered.", show_alert=False)
        elif status == "not_found":
            await callback.answer("❌ File not found.", show_alert=True)
        else:
            await callback.answer("⚠️ Delivery failed. Try again.", show_alert=True)
    else:
        links = "\n".join(f"• <a href=\"{u}\">{u}</a>" for u in urls)
        await callback.answer(
            f"Still need to join:\n{links}",
            show_alert=True,
        )
