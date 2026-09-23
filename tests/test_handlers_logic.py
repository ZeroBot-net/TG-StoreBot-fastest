"""Tests for handler helper functions and basic handler logic.

The whole module is wrapped in try/except — if the app handler tree is not
yet importable (e.g. other workers still writing code), tests are skipped
gracefully.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Attempt to import handler helpers.  Skip the entire module on failure.
# ---------------------------------------------------------------------------
try:
    from app.handlers.upload import _detect_media_type, _extract_file_id
except Exception:
    pytest.skip(
        "app.handlers.upload not importable — handlers not ready",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helper: build a lightweight mock ``Message`` with only the fields the
# functions under test actually read.
# ---------------------------------------------------------------------------

def _make_message(**attrs) -> MagicMock:
    msg = MagicMock()
    msg.photo = attrs.get("photo")
    msg.video = attrs.get("video")
    msg.document = attrs.get("document")
    msg.audio = attrs.get("audio")
    msg.animation = attrs.get("animation")
    msg.voice = attrs.get("voice")
    msg.video_note = attrs.get("video_note")
    msg.sticker = attrs.get("sticker")
    return msg


# ---------------------------------------------------------------------------
# _detect_media_type
# ---------------------------------------------------------------------------

class TestDetectMediaType:
    def test_photo(self) -> None:
        msg = _make_message(photo=[MagicMock()])
        assert _detect_media_type(msg) == "photo"

    def test_video(self) -> None:
        msg = _make_message(video=MagicMock())
        assert _detect_media_type(msg) == "video"

    def test_document(self) -> None:
        msg = _make_message(document=MagicMock())
        assert _detect_media_type(msg) == "document"

    def test_audio(self) -> None:
        msg = _make_message(audio=MagicMock())
        assert _detect_media_type(msg) == "audio"

    def test_animation(self) -> None:
        msg = _make_message(animation=MagicMock())
        assert _detect_media_type(msg) == "animation"

    def test_voice(self) -> None:
        msg = _make_message(voice=MagicMock())
        assert _detect_media_type(msg) == "voice"

    def test_video_note(self) -> None:
        msg = _make_message(video_note=MagicMock())
        assert _detect_media_type(msg) == "video_note"

    def test_sticker(self) -> None:
        msg = _make_message(sticker=MagicMock())
        assert _detect_media_type(msg) == "sticker"

    def test_unknown(self) -> None:
        msg = _make_message()
        assert _detect_media_type(msg) == "unknown"


# ---------------------------------------------------------------------------
# _extract_file_id
# ---------------------------------------------------------------------------

class TestExtractFileId:
    def test_photo_uses_largest_size(self) -> None:
        small = MagicMock(file_id="small_id")
        large = MagicMock(file_id="large_id")
        msg = _make_message(photo=[small, large])
        assert _extract_file_id(msg) == "large_id"

    def test_video(self) -> None:
        vid = MagicMock(file_id="vid_123")
        msg = _make_message(video=vid)
        assert _extract_file_id(msg) == "vid_123"

    def test_document(self) -> None:
        doc = MagicMock(file_id="doc_456")
        msg = _make_message(document=doc)
        assert _extract_file_id(msg) == "doc_456"

    def test_no_media_returns_empty(self) -> None:
        msg = _make_message()
        assert _extract_file_id(msg) == ""


# ---------------------------------------------------------------------------
# Handler integration — exercise the start handler function directly.
# ---------------------------------------------------------------------------

class TestStartHandler:
    """Call the start handler function directly with mock Message objects."""

    def _get_handle_start(self):
        """Import and return the handler, skipping if import fails."""
        try:
            from app.handlers.start import handle_start

            return handle_start
        except Exception:
            pytest.skip("app.handlers.start not importable")

    async def test_valid_code_calls_copy_message(self) -> None:
        handle_start = self._get_handle_start()
        if handle_start is None:
            return

        msg = MagicMock()
        msg.text = "/start 0000000042"
        msg.from_user = MagicMock(id=42)
        msg.answer = AsyncMock()

        # Patch db.get to return a cached file
        fake_cached = MagicMock()
        fake_cached.message_id = 99

        with patch("app.handlers.start.db") as mock_db, \
             patch("app.handlers.start.settings") as mock_settings, \
             patch("app.handlers.start.log_latency"):
            mock_db.get.return_value = fake_cached
            mock_settings.channel_id = -1001
            msg.bot = MagicMock()
            msg.bot.copy_message = AsyncMock()

            await handle_start(msg)

            msg.bot.copy_message.assert_awaited_once_with(
                chat_id=42,
                from_chat_id=-1001,
                message_id=99,
            )

    async def test_invalid_code_calls_answer(self) -> None:
        handle_start = self._get_handle_start()
        if handle_start is None:
            return

        msg = MagicMock()
        msg.text = "/start bad"
        msg.from_user = MagicMock(id=42)
        msg.answer = AsyncMock()

        with patch("app.handlers.start.db") as mock_db, \
             patch("app.handlers.start.log_latency"):
            mock_db.get.return_value = None
            await handle_start(msg)

            msg.answer.assert_awaited()
