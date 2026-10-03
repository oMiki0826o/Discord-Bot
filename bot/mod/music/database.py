"""
bot/mod/music/database.py

Modification():

- 保存使用者音樂收藏清單。
- 提供新增、刪除、查詢、清空與存在檢查。
- 使用 Music Module 自有 SQLite Database。
- SQLite 工作移至背景執行緒，避免阻塞 Discord Event Loop。

本檔負責 Music Module 的持久化資料。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3

from bot.core.database.sqlite import connect, initialize


# ── Database ──────────────────────

class MusicDatabase:
    """Music Module 的 SQLite Database。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        initialize(self.database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return connect(self.database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS music_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    duration INTEGER DEFAULT 0,
                    added_at REAL NOT NULL DEFAULT (unixepoch('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_fav_user
                    ON music_favorites(user_id, added_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_fav_unique
                    ON music_favorites(user_id, url);
                """
            )
            connection.execute("PRAGMA user_version = 1")

    async def _run(self, function, /, *args):
        return await asyncio.to_thread(function, *args)

    def _add_favorite(self, user_id: str, title: str, url: str, duration: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO music_favorites
                    (user_id, title, url, duration)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, title, url, duration),
            )
            return cursor.rowcount > 0

    async def add_favorite(self, user_id: str, title: str, url: str, duration: int = 0) -> bool:
        return await self._run(self._add_favorite, user_id, title, url, duration)

    def _remove_favorite(self, user_id: str, url: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM music_favorites WHERE user_id = ? AND url = ?",
                (user_id, url),
            )
            return cursor.rowcount > 0

    async def remove_favorite(self, user_id: str, url: str) -> bool:
        return await self._run(self._remove_favorite, user_id, url)

    def _clear_favorites(self, user_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM music_favorites WHERE user_id = ?",
                (user_id,),
            )
            return max(cursor.rowcount, 0)

    async def clear_favorites(self, user_id: str) -> int:
        return await self._run(self._clear_favorites, user_id)

    def _get_favorites(self, user_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT title, url, duration, added_at
                FROM music_favorites
                WHERE user_id = ?
                ORDER BY added_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    async def get_favorites(self, user_id: str) -> list[dict]:
        return await self._run(self._get_favorites, user_id)

    def _is_favorite(self, user_id: str, url: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM music_favorites
                WHERE user_id = ? AND url = ?
                """,
                (user_id, url),
            ).fetchone()
        return row is not None

    async def is_favorite(self, user_id: str, url: str) -> bool:
        return await self._run(self._is_favorite, user_id, url)
