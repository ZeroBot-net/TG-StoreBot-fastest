"""SQLite storage with WAL mode and an in-memory cache."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from typing import NamedTuple


class CachedFile(NamedTuple):
    message_id: int
    media_type: str
    file_id: str | None
    user_id: int


class Database:
    """Synchronous SQLite database with write-locking and an in-memory code→file cache."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()
        self._create_tables()
        self._cache: dict[str, CachedFile] = {}
        self._load_cache()

    # -- pragmas ---------------------------------------------------------------

    def _apply_pragmas(self) -> None:
        cur = self._conn.cursor()
        for stmt in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA cache_size=-64000",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=268435456",
        ):
            with contextlib.suppress(Exception):
                cur.execute(stmt)
        with contextlib.suppress(Exception):
            self._conn.commit()

    # -- schema ----------------------------------------------------------------

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                code        TEXT PRIMARY KEY,
                message_id  INTEGER NOT NULL,
                media_type  TEXT    NOT NULL,
                file_id     TEXT,
                user_id     INTEGER NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                file_size   INTEGER,
                caption     TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at)")
        self._conn.commit()

    # -- cache -----------------------------------------------------------------

    def _load_cache(self) -> None:
        """Eagerly load every row into an in-memory dict for O(1) reads."""
        cur = self._conn.execute("SELECT code, message_id, media_type, file_id, user_id FROM files")
        for row in cur:
            self._cache[row["code"]] = CachedFile(
                message_id=row["message_id"],
                media_type=row["media_type"],
                file_id=row["file_id"],
                user_id=row["user_id"],
            )

    # -- public API ------------------------------------------------------------

    def has_code(self, code: str) -> bool:
        """Fast collision check against the in-memory cache."""
        return code in self._cache

    def get(self, code: str) -> CachedFile | None:
        """Return cached file metadata or ``None``."""
        return self._cache.get(code)

    def store(
        self,
        code: str,
        message_id: int,
        media_type: str,
        file_id: str | None,
        user_id: int,
        caption: str | None = None,
        file_size: int | None = None,
    ) -> None:
        """Insert a new file record and update the cache."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO files
                    (code, message_id, media_type, file_id, user_id, caption, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (code, message_id, media_type, file_id, user_id, caption, file_size),
            )
            self._conn.commit()
        self._cache[code] = CachedFile(
            message_id=message_id,
            media_type=media_type,
            file_id=file_id,
            user_id=user_id,
        )

    def list_user_files(self, user_id: int) -> list[tuple[str, str, str | None, str]]:
        """Return ``(code, media_type, caption, created_at)`` tuples for *user_id*."""
        cur = self._conn.execute(
            """
            SELECT code, media_type, caption, created_at
            FROM files
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (user_id,),
        )
        return [(row["code"], row["media_type"], row["caption"], row["created_at"]) for row in cur]

    def delete(self, code: str, user_id: int) -> bool:
        """Delete file if *code* belongs to *user_id*. Returns ``True`` on success."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM files WHERE code = ? AND user_id = ?", (code, user_id)
            )
            self._conn.commit()
            if cur.rowcount > 0:
                self._cache.pop(code, None)
                return True
            return False

    def stats(self) -> dict[str, int]:
        """Return basic aggregate statistics."""
        cur = self._conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(file_size), 0) AS bytes FROM files"
        )
        row = cur.fetchone()
        total_files: int = row["total"]  # type: ignore[index]
        total_bytes: int = row["bytes"]  # type: ignore[index]
        cur2 = self._conn.execute("SELECT COUNT(DISTINCT user_id) AS users FROM files")
        users_row = cur2.fetchone()
        unique_users: int = users_row["users"]  # type: ignore[index]
        return {
            "total_files": total_files,
            "total_bytes": total_bytes,
            "unique_users": unique_users,
        }

    def close(self) -> None:
        """Flush and close the connection."""
        self._conn.close()
