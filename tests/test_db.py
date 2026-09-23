"""Tests for app.db.Database — the core storage layer."""

from __future__ import annotations

import sqlite3

import pytest

from app.db import CachedFile, Database


class TestStoreAndGet:
    """Round-trip: store a row, retrieve it, verify every field."""

    def test_get_returns_cached_file(self, db: Database) -> None:
        db.store("0000000042", 7, "photo", "file_abc", 100, caption="hello", file_size=2048)
        result = db.get("0000000042")
        assert result is not None
        assert isinstance(result, CachedFile)
        assert result.message_id == 7
        assert result.media_type == "photo"
        assert result.file_id == "file_abc"
        assert result.user_id == 100

    def test_get_missing_returns_none(self, db: Database) -> None:
        assert db.get("9999999999") is None


class TestHasCode:
    def test_has_code_true(self, stored_file: Database) -> None:
        assert stored_file.has_code("0000000042") is True

    def test_has_code_false(self, db: Database) -> None:
        assert db.has_code("0000000000") is False


class TestDelete:
    def test_owner_can_delete(self, stored_file: Database) -> None:
        assert stored_file.delete("0000000042", 12345) is True

    def test_other_user_cannot_delete(self, stored_file: Database) -> None:
        assert stored_file.delete("0000000042", 99999) is False

    def test_cache_purged_after_delete(self, stored_file: Database) -> None:
        stored_file.delete("0000000042", 12345)
        assert stored_file.get("0000000042") is None

    def test_delete_nonexistent_returns_false(self, db: Database) -> None:
        assert db.delete("0000000000", 1) is False


class TestListUserFiles:
    def test_returns_only_that_users_rows(self, db: Database) -> None:
        db.store("1111111111", 1, "photo", "f1", 100)
        db.store("2222222222", 2, "video", "f2", 100)
        db.store("3333333333", 3, "document", "f3", 200)
        files = db.list_user_files(100)
        assert len(files) == 2
        # list_user_files returns (code, media_type, caption, created_at) tuples
        codes = {row[0] for row in files}
        assert codes == {"1111111111", "2222222222"}

    def test_empty_when_no_files(self, db: Database) -> None:
        assert db.list_user_files(42) == []


class TestStats:
    def test_counts_match(self, db: Database) -> None:
        db.store("1000000001", 1, "photo", "a", 10, file_size=100)
        db.store("1000000002", 2, "video", "b", 20, file_size=200)
        db.store("1000000003", 3, "audio", "c", 20, file_size=300)
        s = db.stats()
        assert s["total_files"] == 3
        assert s["unique_users"] == 2
        assert s["total_bytes"] == 600

    def test_empty_db(self, db: Database) -> None:
        s = db.stats()
        assert s["total_files"] == 0
        assert s["unique_users"] == 0


class TestTenDigitCodes:
    """Ensure 10-digit string codes are accepted as primary keys."""

    def test_longest_digit_code(self, db: Database) -> None:
        code = "9999999999"
        db.store(code, 1, "photo", "x", 1)
        assert db.get(code) is not None

    def test_min_digit_code(self, db: Database) -> None:
        code = "0000000000"
        db.store(code, 2, "video", "y", 2)
        assert db.get(code) is not None


class TestStoreChannelIdAndExpiry:
    """store() with channel_id + expires_at — get() reflects all fields."""

    def test_store_with_channel_id_and_expires(self, db: Database) -> None:
        db.store(
            "1111111111", 42, "photo", "file_xyz", 100,
            channel_id=123456789, expires_at="2099-01-01 00:00:00",
        )
        result = db.get("1111111111")
        assert result is not None
        assert result.channel_id == 123456789
        assert result.expires_at == "2099-01-01 00:00:00"
        assert result.channels == ((123456789, 42),)

    def test_store_without_channel_id(self, db: Database) -> None:
        db.store("2222222222", 10, "video", "vid_1", 200)
        result = db.get("2222222222")
        assert result is not None
        assert result.channel_id is None
        assert result.expires_at is None
        assert result.channels == ()

    def test_channel_id_writes_file_channels_row(self, db: Database) -> None:
        db.store(
            "3333333333", 55, "document", "doc_1", 300,
            channel_id=999999999,
        )
        # Direct SQL check — file_channels row exists
        cur = db._conn.execute(
            "SELECT channel_id, message_id FROM file_channels WHERE code = ?",
            ("3333333333",),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["channel_id"] == 999999999
        assert rows[0]["message_id"] == 55


class TestAddChannel:
    """add_channel adds a backup channel entry."""

    def test_add_second_backup_channel(self, db: Database) -> None:
        db.store("4444444444", 10, "photo", "f", 1, channel_id=111)
        db.add_channel("4444444444", 222, 20)
        result = db.get("4444444444")
        assert result is not None
        assert len(result.channels) == 2
        assert (111, 10) in result.channels
        assert (222, 20) in result.channels

    def test_add_duplicate_channel_ignored(self, db: Database) -> None:
        db.store("5555555555", 10, "photo", "f", 1, channel_id=111)
        db.add_channel("5555555555", 111, 10)  # same channel, same msg
        result = db.get("5555555555")
        assert len(result.channels) == 1  # deduped

    def test_add_channel_nonexistent_code(self, db: Database) -> None:
        # Should not raise — just a no-op on cache
        db.add_channel("0000000000", 999, 99)
        assert db.get("0000000000") is None


class TestSetExpire:
    """set_expire — owner-only set/clear."""

    def test_owner_can_set(self, db: Database) -> None:
        db.store("6666666666", 10, "photo", "f", 42)
        assert db.set_expire("6666666666", 42, "2099-12-31 23:59:59") is True
        result = db.get("6666666666")
        assert result.expires_at == "2099-12-31 23:59:59"

    def test_non_owner_cannot_set(self, db: Database) -> None:
        db.store("7777777777", 10, "photo", "f", 42)
        assert db.set_expire("7777777777", 99, "2099-12-31 23:59:59") is False
        result = db.get("7777777777")
        assert result.expires_at is None

    def test_none_clears_expiry(self, db: Database) -> None:
        db.store("8888888888", 10, "photo", "f", 42, expires_at="2099-12-31 23:59:59")
        assert db.set_expire("8888888888", 42, None) is True
        result = db.get("8888888888")
        assert result.expires_at is None

    def test_set_expire_on_nonexistent_code(self, db: Database) -> None:
        assert db.set_expire("0000000000", 1, "2099-01-01 00:00:00") is False


class TestClaimExpired:
    """claim_expired — multi-process safe expiry claiming."""

    def test_expired_row_is_claimed(self, db: Database) -> None:
        # Store with expires_at in the past
        db.store(
            "9999999999", 30, "video", "v", 50,
            channel_id=111, expires_at="2000-01-01 00:00:00",
        )
        claimed = db.claim_expired()
        assert len(claimed) == 1
        code, channels = claimed[0]
        assert code == "9999999999"
        assert (111, 30) in channels

    def test_claimed_file_gone_from_get(self, db: Database) -> None:
        db.store(
            "9898989898", 10, "photo", "p", 1,
            channel_id=222, expires_at="2000-01-01 00:00:00",
        )
        db.claim_expired()
        assert db.get("9898989898") is None

    def test_second_claim_returns_empty(self, db: Database) -> None:
        db.store(
            "9797979797", 10, "photo", "p", 1,
            expires_at="2000-01-01 00:00:00",
        )
        first = db.claim_expired()
        assert len(first) == 1
        second = db.claim_expired()
        assert len(second) == 0

    def test_future_expires_not_claimed(self, db: Database) -> None:
        db.store(
            "9696969696", 10, "photo", "p", 1,
            expires_at="2099-12-31 23:59:59",
        )
        claimed = db.claim_expired()
        assert len(claimed) == 0
        assert db.get("9696969696") is not None

    def test_claim_with_channels_collected(self, db: Database) -> None:
        db.store(
            "9595959595", 10, "photo", "p", 1,
            channel_id=111, expires_at="2000-01-01 00:00:00",
        )
        db.add_channel("9595959595", 222, 20)
        claimed = db.claim_expired()
        assert len(claimed) == 1
        _, channels = claimed[0]
        assert len(channels) == 2
        assert (111, 10) in channels
        assert (222, 20) in channels

    def test_claim_removes_file_channels_rows(self, db: Database) -> None:
        db.store(
            "9494949494", 10, "photo", "p", 1,
            channel_id=111, expires_at="2000-01-01 00:00:00",
        )
        db.add_channel("9494949494", 222, 20)
        db.claim_expired()
        cur = db._conn.execute(
            "SELECT * FROM file_channels WHERE code = ?", ("9494949494",)
        )
        assert cur.fetchall() == []


class TestDuplicateStore:
    """Duplicate store must raise IntegrityError."""

    def test_duplicate_code_raises(self, db: Database) -> None:
        db.store("0000000042", 1, "photo", "a", 1)
        with pytest.raises(sqlite3.IntegrityError):
            db.store("0000000042", 2, "video", "b", 2)
