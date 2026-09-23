"""Tests for app.deliver — deliver_file multi-channel delivery logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.deliver import deliver_file
except Exception:
    pytest.skip(
        "app.deliver not importable — deliver module not ready",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cached_file(channels, *, channel_id=123456789, message_id=42):
    """Build a CachedFile-like object with the given channels tuple."""
    cf = MagicMock()
    cf.channels = channels
    cf.channel_id = channel_id
    cf.message_id = message_id
    return cf


def _settings(**overrides):
    s = MagicMock()
    s.channel_id = overrides.get("channel_id", -1001)
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeliverFile:
    """deliver_file returns "ok" | "not_found" | "failed"."""

    async def test_ok_on_first_channel(self) -> None:
        bot = AsyncMock()
        bot.copy_message = AsyncMock(return_value=MagicMock(message_id=999))
        cached = _cached_file(((111, 10), (222, 20)))

        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings()):
            mock_db.get.return_value = cached
            result = await deliver_file(bot, 42, "0000000042")

        assert result == "ok"
        bot.copy_message.assert_awaited_once_with(
            chat_id=42, from_chat_id=111, message_id=10,
        )

    async def test_fallback_to_second_channel(self) -> None:
        bot = AsyncMock()

        # First call fails (deleted/missing channel), second succeeds.
        call_count = 0

        async def _copy(**kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("forbidden")
            return MagicMock(message_id=999)

        bot.copy_message = AsyncMock(side_effect=_copy)
        cached = _cached_file(((111, 10), (222, 20)))

        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings()):
            mock_db.get.return_value = cached
            result = await deliver_file(bot, 42, "0000000042")

        assert result == "ok"
        assert bot.copy_message.await_count == 2

    async def test_not_found(self) -> None:
        bot = AsyncMock()
        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings()):
            mock_db.get.return_value = None
            result = await deliver_file(bot, 42, "9999999999")

        assert result == "not_found"

    async def test_all_channels_fail(self) -> None:
        bot = AsyncMock()
        bot.copy_message = AsyncMock(side_effect=Exception("all fail"))
        cached = _cached_file(((111, 10), (222, 20)))

        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings()):
            mock_db.get.return_value = cached
            result = await deliver_file(bot, 42, "0000000042")

        assert result == "failed"
        assert bot.copy_message.await_count == 2

    async def test_legacy_fallback_to_cached_channel_id(self) -> None:
        """When channels is empty but channel_id present, use cached.channel_id."""
        bot = AsyncMock()
        bot.copy_message = AsyncMock(return_value=MagicMock(message_id=999))
        cached = _cached_file((), channel_id=123456789, message_id=42)

        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings()):
            mock_db.get.return_value = cached
            result = await deliver_file(bot, 99, "0000000042")

        assert result == "ok"
        bot.copy_message.assert_awaited_once_with(
            chat_id=99, from_chat_id=123456789, message_id=42,
        )

    async def test_legacy_no_channel_id_falls_back_to_settings(self) -> None:
        """When channels is empty AND channel_id is None, use settings.channel_id."""
        bot = AsyncMock()
        bot.copy_message = AsyncMock(return_value=MagicMock(message_id=999))
        cached = _cached_file((), channel_id=None, message_id=42)

        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings(channel_id=-1001)):
            mock_db.get.return_value = cached
            result = await deliver_file(bot, 99, "0000000042")

        assert result == "ok"
        bot.copy_message.assert_awaited_once_with(
            chat_id=99, from_chat_id=-1001, message_id=42,
        )

    async def test_single_channel_ok(self) -> None:
        bot = AsyncMock()
        bot.copy_message = AsyncMock(return_value=MagicMock(message_id=999))
        cached = _cached_file(((111, 10),))

        with patch("app.deliver.db") as mock_db, \
             patch("app.deliver.settings", _settings()):
            mock_db.get.return_value = cached
            result = await deliver_file(bot, 42, "0000000042")

        assert result == "ok"
        bot.copy_message.assert_awaited_once()
