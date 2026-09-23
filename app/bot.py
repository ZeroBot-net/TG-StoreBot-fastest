"""Aiogram 3 bot bootstrap — creates Bot, Dispatcher, shared Router, and DB singleton."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import settings
from app.db import Database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons (shared by handlers via import)
# ---------------------------------------------------------------------------

router = Router()
db = Database(settings.db_path)

BOT_USERNAME: str = ""
_bot: Bot | None = None
_dp: Dispatcher | None = None
_session: AiohttpSession | None = None


def create_bot() -> None:
    """Create Bot + Dispatcher with a reusable AiohttpSession."""
    global _bot, _dp, _session  # noqa: PLW0603
    _session = AiohttpSession()
    _bot = Bot(token=settings.bot_token, session=_session)
    _dp = Dispatcher()


async def get_bot_username() -> str:
    """Return cached username, falling back to an API call."""
    if BOT_USERNAME:
        return BOT_USERNAME
    if _bot is not None:
        me = await _bot.get_me()
        return me.username or ""
    return ""


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------


async def _on_startup() -> None:
    """Fetch bot info and pre-warm the channel cache."""
    global BOT_USERNAME  # noqa: PLW0603

    assert _bot is not None
    me = await _bot.get_me()
    _bot.me = me
    BOT_USERNAME = me.username or ""
    logger.info("Bot started as @%s", BOT_USERNAME)

    try:
        await _bot.get_chat(settings.channel_id)
    except Exception:
        logger.warning("Could not pre-warm channel %s", settings.channel_id, exc_info=True)


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


def _register_handlers() -> None:
    """Import handler modules so their @router.message(...) decorators fire."""
    try:
        import app.handlers  # noqa: F401
    except ImportError:
        logger.warning("Handler modules not available — bot will start without command handlers")


async def _expiry_scheduler() -> None:
    """Background loop that claims and deletes expired messages."""
    interval_s = settings.expiry_scan_interval_m * 60
    while True:
        await asyncio.sleep(interval_s)
        try:
            # Sync SQLite work off the event loop — never block handlers.
            claimed = await asyncio.to_thread(db.claim_expired)
            for code, channels in claimed:
                for ch, mid in channels:
                    try:
                        await _bot.delete_message(ch, mid)  # type: ignore[union-attr]
                    except Exception:
                        logger.warning(
                            "failed to delete expired msg ch=%s mid=%s code=%s",
                            ch,
                            mid,
                            code,
                        )
                logger.info("expired %s (%d channels)", code, len(channels))
        except Exception:
            logger.exception("expiry scheduler error")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    # Optional file logging (LOG_FILE= disables with an empty value).
    if settings.log_file:
        try:
            from pathlib import Path

            log_path = Path(settings.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
                )
            )
            logging.getLogger().addHandler(fh)
            logger.info("logging to file: %s", log_path)
        except OSError:
            logger.warning("could not open LOG_FILE=%s", settings.log_file)

    create_bot()
    assert _dp is not None and _bot is not None and _session is not None

    _dp.include_router(router)
    _register_handlers()

    _dp.startup.register(_on_startup)

    sched_task: asyncio.Task[None] | None = None
    if settings.expiry_scan_interval_m > 0:
        sched_task = asyncio.create_task(_expiry_scheduler())
    else:
        logger.info(
            "EXPIRY_SCAN_INTERVAL_M=0 — auto-expire disabled "
            "(files will never be auto-removed)"
        )
    try:
        await _dp.start_polling(
            _bot, allowed_updates=["message", "callback_query"]
        )
    finally:
        if sched_task is not None:
            sched_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sched_task
        db.close()
        from app.latency import close_handle

        close_handle()
        await _session.close()


if __name__ == "__main__":
    if sys.platform != "win32":
        import uvloop  # noqa: PLC0415

        uvloop.install()
    asyncio.run(main())
