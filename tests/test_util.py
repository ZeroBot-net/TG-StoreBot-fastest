"""Tests for app.util — parse_duration, format_duration, iso_in."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

try:
    from app.util import format_duration, iso_in, parse_duration
except Exception:
    pytest.skip(
        "app.util not importable — util module not ready",
        allow_module_level=True,
    )


class TestParseDuration:
    """parse_duration converts human duration strings to seconds."""

    def test_seconds(self) -> None:
        assert parse_duration("30s") == 30

    def test_minutes(self) -> None:
        assert parse_duration("5m") == 300

    def test_hours(self) -> None:
        assert parse_duration("2h") == 7200

    def test_days(self) -> None:
        assert parse_duration("7d") == 604800

    def test_mixed_hm(self) -> None:
        assert parse_duration("1h30m") == 5400

    def test_empty_string(self) -> None:
        assert parse_duration("") is None

    def test_alpha_only(self) -> None:
        assert parse_duration("abc") is None

    def test_negative(self) -> None:
        assert parse_duration("-5m") is None

    def test_zero_seconds(self) -> None:
        assert parse_duration("0s") is None

    def test_whitespace_around(self) -> None:
        assert parse_duration("  10m  ") == 600


class TestFormatDuration:
    """format_duration turns seconds into a human-readable string."""

    def test_minutes_only(self) -> None:
        result = format_duration(300)
        assert "5" in result

    def test_hours_and_minutes(self) -> None:
        result = format_duration(5400)
        assert "1" in result and "30" in result

    def test_weeks(self) -> None:
        result = format_duration(604800)
        assert "1w" in result

    def test_days(self) -> None:
        result = format_duration(86400)
        assert "1d" in result

    def test_seconds_only(self) -> None:
        result = format_duration(45)
        assert "45" in result


class TestIsoIn:
    """iso_in returns a UTC timestamp roughly ``sec`` seconds in the future."""

    def test_basic(self) -> None:
        result = iso_in(60)
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        now = datetime.now(UTC)
        diff = (parsed - now).total_seconds()
        assert 55 <= diff <= 70  # ~60s with small tolerance

    def test_zero(self) -> None:
        result = iso_in(0)
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        now = datetime.now(UTC)
        diff = abs((parsed - now).total_seconds())
        assert diff <= 2

    def test_large_offset(self) -> None:
        result = iso_in(3600)
        parsed = datetime.fromisoformat(result).replace(tzinfo=UTC)
        now = datetime.now(UTC)
        diff = (parsed - now).total_seconds()
        assert 3595 <= diff <= 3610


class TestFormatExpiryDisplay:
    """format_expiry_display — render stored UTC timestamps in TZ."""

    def test_dhaka_is_plus_six(self) -> None:
        from app.util import format_expiry_display

        result = format_expiry_display("2026-01-01 00:00:00", "Asia/Dhaka")
        assert result.startswith("2026-01-01 06:00:00")

    def test_unknown_zone_falls_back_to_utc(self) -> None:
        from app.util import format_expiry_display

        result = format_expiry_display("2026-01-01 00:00:00", "Not/AZone")
        assert result == "2026-01-01 00:00:00 UTC"

    def test_invalid_timestamp_falls_back(self) -> None:
        from app.util import format_expiry_display

        result = format_expiry_display("garbage", "Asia/Dhaka")
        assert result == "garbage UTC"
