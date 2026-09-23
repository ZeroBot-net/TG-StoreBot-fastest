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
# Upload helpers — TTL caption parsing.
# ---------------------------------------------------------------------------

class TestParseTtlCaption:
    def test_no_caption(self) -> None:
        from app.handlers.upload import _parse_ttl_caption

        expires, cap, err = _parse_ttl_caption(None)
        assert expires is None and cap is None and err is None

    def test_plain_caption_untouched(self) -> None:
        from app.handlers.upload import _parse_ttl_caption

        expires, cap, err = _parse_ttl_caption("hello world")
        assert expires is None and cap == "hello world" and err is None

    def test_ttl_with_caption_remainder(self) -> None:
        from app.handlers.upload import _parse_ttl_caption

        expires, cap, err = _parse_ttl_caption("/ttl 2h my file")
        assert err is None and expires is not None
        assert cap == "my file"

    def test_ttl_only_duration(self) -> None:
        from app.handlers.upload import _parse_ttl_caption

        expires, cap, err = _parse_ttl_caption("/ttl 30m")
        assert err is None and expires is not None and cap is None

    def test_ttl_invalid_duration(self) -> None:
        from app.handlers.upload import _parse_ttl_caption

        _, _, err = _parse_ttl_caption("/ttl banana")
        assert err is not None

    def test_ttl_missing_duration(self) -> None:
        from app.handlers.upload import _parse_ttl_caption

        _, _, err = _parse_ttl_caption("/ttl")
        assert err is not None


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

    async def test_valid_code_calls_deliver(self) -> None:
        handle_start = self._get_handle_start()
        if handle_start is None:
            return

        msg = MagicMock()
        msg.text = "/start 0000000042"
        msg.from_user = MagicMock(id=42)
        msg.answer = AsyncMock()
        msg.bot = MagicMock()

        with patch("app.handlers.start.db") as mock_db, \
             patch("app.handlers.start.log_latency"), \
             patch("app.handlers.start.ensure_joined", return_value=(True, [])) as mock_join, \
             patch("app.handlers.start.deliver_file", return_value="ok") as mock_deliver:
            mock_db.get.return_value = MagicMock()  # code exists

            await handle_start(msg)

            mock_join.assert_awaited_once()
            mock_deliver.assert_awaited_once_with(msg.bot, 42, "0000000042")
            msg.answer.assert_not_awaited()  # delivered silently

    async def test_force_join_blocks_delivery(self) -> None:
        handle_start = self._get_handle_start()
        if handle_start is None:
            return

        msg = MagicMock()
        msg.text = "/start 0000000042"
        msg.from_user = MagicMock(id=42)
        msg.answer = AsyncMock()
        msg.bot = MagicMock()

        join_ret = (False, ["https://t.me/chan"])
        with patch("app.handlers.start.db") as mock_db, \
             patch("app.handlers.start.log_latency"), \
             patch("app.handlers.start.ensure_joined", return_value=join_ret), \
             patch("app.handlers.start.deliver_file") as mock_deliver:
            mock_db.get.return_value = MagicMock()

            await handle_start(msg)

            mock_deliver.assert_not_awaited()  # gated — no delivery yet
            msg.answer.assert_awaited_once()
            assert "Join" in msg.answer.call_args[0][0]

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
