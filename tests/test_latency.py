"""Tests for app.latency.log_latency."""

from __future__ import annotations

import time


class TestLogLatency:
    def test_writes_csv_line_with_five_fields(self, tmp_path) -> None:
        log_file = str(tmp_path / "lat.csv")
        # Patch settings before import / call
        import app.config as cfg_mod
        import app.latency as lat_mod

        orig = cfg_mod.settings.latency_log_file
        cfg_mod.settings.latency_log_file = log_file
        # Force module-level handle to reset
        lat_mod._handle = None
        try:
            t0 = time.monotonic() - 0.05  # simulate 50ms ago
            lat_mod.log_latency("1234567890", t0, 42, success=True)

            with open(log_file, encoding="utf-8") as f:
                line = f.readline().strip()
            parts = line.split(",")
            assert len(parts) == 5, f"Expected 5 CSV fields, got {len(parts)}: {parts}"
            assert parts[0].isdigit()  # epoch
            assert parts[1] == "1234567890"
            assert parts[2] == "42"
            assert parts[3].replace(".", "").isdigit()  # latency_ms
            assert parts[4] == "True"
        finally:
            cfg_mod.settings.latency_log_file = orig
            lat_mod._handle = None

    def test_never_raises_on_bad_path(self) -> None:
        import app.config as cfg_mod
        import app.latency as lat_mod

        orig = cfg_mod.settings.latency_log_file
        cfg_mod.settings.latency_log_file = "/nonexistent-dir/x/log.csv"
        lat_mod._handle = None
        try:
            # Must not raise even though path is invalid.
            lat_mod.log_latency("0000000000", time.monotonic(), 1, success=False)
        finally:
            cfg_mod.settings.latency_log_file = orig
            lat_mod._handle = None

    def test_success_false_written(self, tmp_path) -> None:
        log_file = str(tmp_path / "lat2.csv")
        import app.config as cfg_mod
        import app.latency as lat_mod

        orig = cfg_mod.settings.latency_log_file
        cfg_mod.settings.latency_log_file = log_file
        lat_mod._handle = None
        try:
            lat_mod.log_latency("9999999999", time.monotonic(), 7, success=False)
            with open(log_file, encoding="utf-8") as f:
                line = f.readline().strip()
            parts = line.split(",")
            assert parts[4] == "False"
        finally:
            cfg_mod.settings.latency_log_file = orig
            lat_mod._handle = None
