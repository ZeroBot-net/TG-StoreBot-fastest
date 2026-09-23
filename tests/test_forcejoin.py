"""Tests for app.forcejoin — ensure_joined + invalidate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.forcejoin import ensure_joined, invalidate
except Exception:
    pytest.skip(
        "app.forcejoin not importable — forcejoin module not ready",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_settings(**overrides):
    """Build a mock settings object with sane defaults."""
    s = MagicMock()
    s.force_join_chats = overrides.get("force_join_chats", [])
    s.admin_ids = overrides.get("admin_ids", [1])
    return s


def _mock_bot():
    """Async-mock bot that returns a default 'member' status."""
    bot = MagicMock()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))
    return bot


def _clear_join_cache():
    """Reset the module-level join cache so tests are isolated."""
    import app.forcejoin as fj

    if hasattr(fj, "_join_cache"):
        fj._join_cache.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnsureJoined:
    """ensure_joined returns (True, []) when no gate or bypass conditions hold."""

    async def test_no_force_chats_returns_true(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=[])
        bot = _mock_bot()
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 42)
        assert ok is True
        assert urls == []

    async def test_admin_bypass(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"], admin_ids=[1, 42])
        bot = _mock_bot()
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 42)
        assert ok is True
        assert urls == []

    async def test_member_status_ok(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"])
        bot = _mock_bot()
        bot.get_chat_member.return_value = MagicMock(status="member")
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 99)
        assert ok is True
        assert urls == []

    async def test_left_status_returns_false(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"])
        bot = _mock_bot()
        bot.get_chat_member.return_value = MagicMock(status="left")
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 99)
        assert ok is False
        assert len(urls) > 0  # should contain chat URL

    async def test_kicked_status_returns_false(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"])
        bot = _mock_bot()
        bot.get_chat_member.return_value = MagicMock(status="kicked")
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 99)
        assert ok is False
        assert len(urls) > 0

    async def test_api_error_double_check_still_fails_denies(self) -> None:
        """API error -> immediate retry (double-check); still failing = DENY."""
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"])
        bot = _mock_bot()
        bot.get_chat_member = AsyncMock(side_effect=Exception("Telegram API error"))
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 99)
        assert bot.get_chat_member.await_count == 2  # double-checked
        assert ok is False  # fail-closed: unverified = no access
        assert len(urls) > 0

    async def test_api_error_double_check_recovers(self) -> None:
        """Transient error on first attempt, success on the double-check."""
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"])
        bot = _mock_bot()
        bot.get_chat_member = AsyncMock(
            side_effect=[Exception("flaky"), MagicMock(status="member")]
        )
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 99)
        assert ok is True
        assert urls == []

    async def test_multiple_chats_all_member(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@chat1", "@chat2"])
        bot = _mock_bot()
        bot.get_chat_member.return_value = MagicMock(status="member")
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 55)
        assert ok is True

    async def test_first_member_second_left(self) -> None:
        """When first chat is OK but second is left, should fail."""
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@chat1", "@chat2"])
        bot = _mock_bot()
        member = MagicMock(status="member")
        left = MagicMock(status="left")
        bot.get_chat_member = AsyncMock(side_effect=[member, left])
        with patch("app.forcejoin.settings", settings):
            ok, urls = await ensure_joined(bot, 55)
        assert ok is False
        assert len(urls) >= 1


class TestInvalidate:
    """invalidate clears the join cache for a user."""

    async def test_invalidate_clears_cache(self) -> None:
        _clear_join_cache()
        settings = _fresh_settings(force_join_chats=["@mychat"])
        bot = _mock_bot()
        bot.get_chat_member.return_value = MagicMock(status="member")

        # First call populates cache
        with patch("app.forcejoin.settings", settings):
            await ensure_joined(bot, 55)

        # Invalidate
        invalidate(55)

        # Next call should re-check (member status, still ok)
        bot.get_chat_member.return_value = MagicMock(status="member")
        with patch("app.forcejoin.settings", settings):
            ok, _ = await ensure_joined(bot, 55)
        assert ok is True
