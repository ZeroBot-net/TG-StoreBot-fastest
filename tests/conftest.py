# ruff: noqa: E402, SIM115, F401
"""Shared fixtures for tg-storebot-fastest tests.

Env vars MUST be set before any ``app.*`` import — ``app.config.settings`` is
created at module level.  pytest loads conftest.py before test collection, so
the top-level ``os.environ.setdefault`` calls run first.
"""

from __future__ import annotations

import os
import tempfile

# ---------------------------------------------------------------------------
# Env defaults — must precede every ``from app.* import ...`` in the suite.
# ---------------------------------------------------------------------------
os.environ.setdefault("BOT_TOKEN", "123:test-token")
os.environ.setdefault("CHANNEL_ID", "-1001")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
_latency_tmp = tempfile.NamedTemporaryFile(suffix=".csv", prefix="latency_", delete=False)
_latency_tmp.close()
os.environ.setdefault("LATENCY_LOG_FILE", _latency_tmp.name)

# ---------------------------------------------------------------------------
# Imports (safe now — env is populated).
# ---------------------------------------------------------------------------
import pytest  # noqa: E402

from app.db import CachedFile, Database  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db() -> Database:
    """Fresh in-memory ``Database`` for each test."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture()
def stored_file(db: Database):
    """Pre-stored file so tests can exercise get/delete/stats without setup."""
    db.store(
        "0000000042",
        7,
        "photo",
        "AgACAgIAAxkBAAI",
        12345,
        caption="test caption",
        file_size=1024,
    )
    return db
