"""SQLite storage with WAL mode and an in-memory cache."""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from typing import NamedTuple


class CachedFile(NamedTuple):
    message_id: int
    media_type: str
    file_id: str | None
    user_id: int
    channel_id: int | None = None
    expires_at: str | None = None
    channels: tuple[tuple[int, int], ...] = ()


class Database:
    """Synchronous SQLite database with write-locking and an in-memory code→file cache."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            path, check_same_thread=False, timeout=10
        )
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()
        self._create_tables()
        self._migrate()
        self._cache: dict[str, CachedFile] = {}
        self._data_version: int = 0
        self._last_refresh: float = 0.0
        self._load_cache()
        self._data_version = self._read_data_version()

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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS file_channels (
                code        TEXT    NOT NULL,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                PRIMARY KEY (code, channel_id)
            )
            """
        )
        self._conn.commit()

    # -- migration -------------------------------------------------------------

    def _migrate(self) -> None:
        """Add new columns/tables to existing databases in-place."""
        cur = self._conn.cursor()
        existing = {
            row["name"] for row in cur.execute("PRAGMA table_info(files)")
        }
        if "channel_id" not in existing:
            cur.execute("ALTER TABLE files ADD COLUMN channel_id INTEGER")
        if "expires_at" not in existing:
            cur.execute("ALTER TABLE files ADD COLUMN expires_at TEXT")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_expires ON files(expires_at)"
        )
        self._conn.commit()

    # -- data-version for multi-process cache refresh --------------------------

    def _read_data_version(self) -> int:
        row = self._conn.execute("PRAGMA data_version").fetchone()
        return row[0] if row else 0

    def _maybe_refresh(self) -> None:
        """Reload full cache when another process bumped data_version.

        Throttled to once per second — a PRAGMA on every single lookup would
        dominate the hot path for zero benefit in single-process mode.
        """
        now = time.monotonic()
        if now - self._last_refresh < 1.0:
            return
        self._last_refresh = now
        dv = self._read_data_version()
        if dv != self._data_version:
            self._load_cache()
            self._data_version = dv

    def _bump_data_version(self) -> None:
        """Sync data_version after a local write so the next read skips a reload."""
        self._data_version = self._read_data_version()
        self._last_refresh = time.monotonic()

    # -- cache -----------------------------------------------------------------

    def _load_cache(self) -> None:
        """Eagerly load every row into an in-memory dict for O(1) reads."""
        self._cache.clear()
        cur = self._conn.execute(
            """
            SELECT f.code, f.message_id, f.media_type, f.file_id, f.user_id,
                   f.channel_id, f.expires_at,
                   GROUP_CONCAT(fc.channel_id || ':' || fc.message_id) AS chans
            FROM files f
            LEFT JOIN file_channels fc ON fc.code = f.code
            GROUP BY f.code
            """
        )
        for row in cur:
            channels: tuple[tuple[int, int], ...] = ()
            raw = row["chans"]
            if raw:
                channels = tuple(
                    (
                        int(c.strip().split(":")[0]),
                        int(c.strip().split(":")[1]),
                    )
                    for c in raw.split(",")
                    if ":" in c
                )
            self._cache[row["code"]] = CachedFile(
                message_id=row["message_id"],
                media_type=row["media_type"],
                file_id=row["file_id"],
                user_id=row["user_id"],
                channel_id=row["channel_id"],
                expires_at=row["expires_at"],
                channels=channels,
            )

    # -- public API ------------------------------------------------------------

    def has_code(self, code: str) -> bool:
        """Fast collision check against the in-memory cache."""
        self._maybe_refresh()
        return code in self._cache

    def get(self, code: str) -> CachedFile | None:
        """Return cached file metadata or ``None``."""
        self._maybe_refresh()
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
        *,
        channel_id: int | None = None,
        expires_at: str | None = None,
    ) -> None:
        """Insert a new file record and update the cache."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO files
                    (code, message_id, media_type, file_id, user_id,
                     caption, file_size, channel_id, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    message_id,
                    media_type,
                    file_id,
                    user_id,
                    caption,
                    file_size,
                    channel_id,
                    expires_at,
                ),
            )
            if channel_id is not None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO file_channels"
                    " (code, channel_id, message_id)"
                    " VALUES (?, ?, ?)",
                    (code, channel_id, message_id),
                )
            self._conn.commit()
            channels: tuple[tuple[int, int], ...] = ()
            if channel_id is not None:
                channels = ((channel_id, message_id),)
            self._cache[code] = CachedFile(
                message_id=message_id,
                media_type=media_type,
                file_id=file_id,
                user_id=user_id,
                channel_id=channel_id,
                expires_at=expires_at,
                channels=channels,
            )
            self._bump_data_version()

    def add_channel(
        self, code: str, channel_id: int, message_id: int
    ) -> None:
        """Add a backup channel entry for an existing code."""
        if code not in self._cache:
            self._maybe_refresh()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO file_channels"
                " (code, channel_id, message_id)"
                " VALUES (?, ?, ?)",
                (code, channel_id, message_id),
            )
            self._conn.commit()
            cf = self._cache.get(code)
            if cf is not None and (channel_id, message_id) not in cf.channels:
                self._cache[code] = cf._replace(
                    channels=cf.channels + ((channel_id, message_id),)
                )
            self._bump_data_version()

    def set_expire(
        self, code: str, user_id: int, expires_at: str | None
    ) -> bool:
        """Set or clear expiry for a file. Owner-only. Returns True on success."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE files SET expires_at = ?"
                " WHERE code = ? AND user_id = ?",
                (expires_at, code, user_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                return False
            cf = self._cache.get(code)
            if cf is not None:
                self._cache[code] = cf._replace(expires_at=expires_at)
            self._bump_data_version()
        return True

    def claim_expired(
        self,
    ) -> list[tuple[str, tuple[tuple[int, int], ...]]]:
        """Multi-process safe expiry claim under a single transaction.

        Returns list of ``(code, channels)`` for files we successfully claimed.
        """
        claimed: list[tuple[str, tuple[tuple[int, int], ...]]] = []
        with self._lock:
            cur = self._conn.execute(
                "SELECT code FROM files"
                " WHERE expires_at IS NOT NULL"
                " AND expires_at <= datetime('now')"
            )
            expired_codes = [row["code"] for row in cur]

            to_pop: list[str] = []
            for code in expired_codes:
                # Collect channels BEFORE deleting the files row (another
                # process may claim between our SELECT and DELETE).
                chans_cur = self._conn.execute(
                    "SELECT channel_id, message_id"
                    " FROM file_channels WHERE code = ?",
                    (code,),
                )
                channels: tuple[tuple[int, int], ...] = tuple(
                    (r["channel_id"], r["message_id"]) for r in chans_cur
                )

                # Legacy rows: no file_channels entry — read the primary
                # channel straight from the DB row (never from the cache,
                # which may be stale when another process wrote it).
                if not channels:
                    prim = self._conn.execute(
                        "SELECT channel_id, message_id"
                        " FROM files WHERE code = ?",
                        (code,),
                    ).fetchone()
                    if prim is not None and prim["channel_id"] is not None:
                        channels = ((prim["channel_id"], prim["message_id"]),)

                del_cur = self._conn.execute(
                    "DELETE FROM files WHERE code = ?"
                    " AND expires_at IS NOT NULL"
                    " AND expires_at <= datetime('now')",
                    (code,),
                )
                if del_cur.rowcount == 0:
                    continue  # another process claimed it

                self._conn.execute(
                    "DELETE FROM file_channels WHERE code = ?",
                    (code,),
                )
                to_pop.append(code)
                claimed.append((code, channels))

            self._conn.commit()
            # Only purge cache after a successful commit.
            for code in to_pop:
                self._cache.pop(code, None)
            if to_pop:
                self._bump_data_version()
        return claimed

    def list_user_files(
        self, user_id: int
    ) -> list[tuple[str, str, str | None, str]]:
        """Return ``(code, media_type, caption, created_at)`` for *user_id*."""
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
        return [
            (
                row["code"],
                row["media_type"],
                row["caption"],
                row["created_at"],
            )
            for row in cur
        ]

    def delete(self, code: str, user_id: int) -> bool:
        """Delete file if *code* belongs to *user_id*. Returns True on success."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM files WHERE code = ? AND user_id = ?",
                (code, user_id),
            )
            if cur.rowcount > 0:
                self._conn.execute(
                    "DELETE FROM file_channels WHERE code = ?", (code,)
                )
                self._conn.commit()
                self._cache.pop(code, None)
                self._bump_data_version()
                return True
            self._conn.commit()
            return False

    def stats(self) -> dict[str, int]:
        """Return basic aggregate statistics."""
        cur = self._conn.execute(
            "SELECT COUNT(*) AS total,"
            " COALESCE(SUM(file_size), 0) AS bytes FROM files"
        )
        row = cur.fetchone()
        total_files: int = row["total"]  # type: ignore[index]
        total_bytes: int = row["bytes"]  # type: ignore[index]
        cur2 = self._conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS users FROM files"
        )
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
