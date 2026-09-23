"""Pure utility functions — duration parsing, formatting, time helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)([smhdw])")


def parse_duration(s: str) -> float | None:
    """Parse a human duration like ``30s``, ``5m``, ``2h``, ``7d``, ``1w``,
    or combined ``1h30m``.  Returns seconds as float, or ``None`` if
    invalid / zero / negative.
    """
    s = s.strip().lower()
    if not s:
        return None

    matches = _DURATION_RE.findall(s)
    if not matches:
        return None

    # Ensure the entire string was consumed (allow only the matched tokens).
    consumed = "".join(f"{v}{u}" for v, u in matches)
    if s != consumed:
        return None

    total = sum(float(val) * _UNITS[unit] for val, unit in matches)
    return total if total > 0 else None


def format_duration(seconds: float) -> str:
    """Format seconds into a human short form like ``2h 30m``."""
    if seconds <= 0:
        return "0s"

    parts: list[str] = []
    remaining = int(seconds)

    for unit, divisor in [("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)]:
        if remaining >= divisor:
            count = remaining // divisor
            parts.append(f"{count}{unit}")
            remaining -= count * divisor

    if remaining > 0 or not parts:
        parts.append(f"{remaining}s")

    return " ".join(parts)


def iso_in(seconds: float) -> str:
    """Return a UTC timestamp string ``%Y-%m-%d %H:%M:%S`` = now + *seconds*."""
    target = datetime.now(UTC).timestamp() + seconds
    return datetime.fromtimestamp(target, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
