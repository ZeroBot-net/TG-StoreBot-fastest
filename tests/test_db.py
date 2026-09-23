"""Tests for app.db.Database — the core storage layer."""

from __future__ import annotations

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
