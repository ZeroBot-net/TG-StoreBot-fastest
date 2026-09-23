#!/usr/bin/env python3
"""Benchmark: 100k inserts + 200k get() lookups on Database.

Usage::

    uv run python scripts/benchmark.py
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time

# ---------------------------------------------------------------------------
# Env defaults — must precede any app.config import (Settings() is module-level).
# ---------------------------------------------------------------------------
os.environ.setdefault("BOT_TOKEN", "123:bench")
os.environ.setdefault("CHANNEL_ID", "-1001")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("LATENCY_LOG_FILE", "/dev/null")

from app.db import Database  # noqa: E402

_NUM_INSERTS = 100_000
_NUM_LOOKUPS = 200_000


def main() -> None:
    db_path = os.path.join(tempfile.gettempdir(), "bench_store.db")
    with contextlib.suppress(FileNotFoundError):
        os.unlink(db_path)

    db = Database(db_path)

    # --- Inserts ----------------------------------------------------------
    print(f"Inserting {_NUM_INSERTS:,} rows …")
    t0 = time.perf_counter()
    for i in range(_NUM_INSERTS):
        db.store(
            f"{i:010d}",
            i,
            "photo",
            f"fid_{i}",
            i % 1000,
        )
    insert_ms = (time.perf_counter() - t0) * 1000
    print(f"  inserts: {insert_ms:.0f} ms  ({_NUM_INSERTS / insert_ms * 1000:,.0f} ops/sec)")

    # --- Lookups ----------------------------------------------------------
    print(f"Running {_NUM_LOOKUPS:,} get() lookups …")
    t1 = time.perf_counter()
    for j in range(_NUM_LOOKUPS):
        code = f"{j % _NUM_INSERTS:010d}"
        db.get(code)
    lookup_ms = (time.perf_counter() - t1) * 1000
    avg_us = lookup_ms * 1000 / _NUM_LOOKUPS
    ops_sec = _NUM_LOOKUPS / (lookup_ms / 1000)

    print(f"  lookups: {lookup_ms:.0f} ms total")
    print(f"  avg per lookup: {avg_us:.1f} µs")
    print(f"  throughput: {ops_sec:,.0f} ops/sec")

    db.close()
    with contextlib.suppress(FileNotFoundError):
        os.unlink(db_path)


if __name__ == "__main__":
    main()
