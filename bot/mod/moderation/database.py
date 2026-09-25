"""
bot/mod/moderation/database.py

Modification():

- 建立 Moderation Module 自有的 SQLite Database。
- 保存警告紀錄與一般管理動作紀錄。
- 提供警告新增、查詢、計數與清除操作。
- 提供管理紀錄查詢與模組專屬日誌頻道設定。

本檔只負責 Moderation Module 的持久化資料。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time

from bot.core.database.sqlite import connect, initialize


# ── Models ──────────────────────

@dataclass(frozen=True, slots=True)
class WarningRecord:
    """單筆警告紀錄。"""

    reason: str
    moderator_id: int
    created_at: int


@dataclass(frozen=True, slots=True)
class ModerationRecord:
    """單筆管理動作紀錄。"""

    action: str
    user_id: int
    moderator_id: int
    reason: str
    duration_min: int | None
    created_at: int


# ── Database ──────────────────────

class ModerationDatabase:
    """管理 Moderation Module 的 SQLite 資料。"""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        initialize(self.database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """建立短生命週期 SQLite Connection。"""

        return connect(self.database_path)

    def _initialize(self) -> None:
        """建立 Moderation Module 所需資料表與索引。"""

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS warnings (
                    warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_warnings_guild_user
                ON warnings(guild_id, user_id);

                CREATE TABLE IF NOT EXISTS moderation_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    duration_min INTEGER,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_moderation_log_guild
                ON moderation_log(guild_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    # ── Warnings ──────────────────────

    def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> int:
        """新增警告並回傳目前累計警告數。"""

        created_at = int(time.time())

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO warnings (
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    created_at,
                ),
            )

            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM warnings
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            ).fetchone()

        return int(row["total"]) if row else 0

    def get_warnings(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[WarningRecord]:
        """取得指定成員的警告紀錄。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT reason, moderator_id, created_at
                FROM warnings
                WHERE guild_id = ? AND user_id = ?
                ORDER BY created_at ASC, warning_id ASC
                """,
                (guild_id, user_id),
            ).fetchall()

        return [
            WarningRecord(
                reason=str(row["reason"]),
                moderator_id=int(row["moderator_id"]),
                created_at=int(row["created_at"]),
            )
            for row in rows
        ]

    def count_warnings(
        self,
        guild_id: int,
        user_id: int,
    ) -> int:
        """取得指定成員的警告數量。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM warnings
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            ).fetchone()

        return int(row["total"]) if row else 0

    def clear_warnings(
        self,
        guild_id: int,
        user_id: int,
    ) -> int:
        """清除指定成員的全部警告並回傳刪除數。"""

        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM warnings
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )

        return max(cursor.rowcount, 0)

    # ── Moderation Log ──────────────────────

    def log_action(
        self,
        guild_id: int,
        action: str,
        user_id: int,
        moderator_id: int,
        reason: str,
        duration_min: int | None = None,
    ) -> None:
        """記錄管理動作。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO moderation_log (
                    guild_id,
                    action,
                    user_id,
                    moderator_id,
                    reason,
                    duration_min,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    action,
                    user_id,
                    moderator_id,
                    reason,
                    duration_min,
                    int(time.time()),
                ),
            )

    def get_mod_log(
        self,
        guild_id: int,
        *,
        limit: int,
    ) -> list[ModerationRecord]:
        """取得 Guild 最近的管理動作。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    action,
                    user_id,
                    moderator_id,
                    reason,
                    duration_min,
                    created_at
                FROM moderation_log
                WHERE guild_id = ?
                ORDER BY created_at DESC, log_id DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ).fetchall()

        return [
            ModerationRecord(
                action=str(row["action"]),
                user_id=int(row["user_id"]),
                moderator_id=int(row["moderator_id"]),
                reason=str(row["reason"]),
                duration_min=(
                    int(row["duration_min"])
                    if row["duration_min"] is not None
                    else None
                ),
                created_at=int(row["created_at"]),
            )
            for row in rows
        ]

    # ── Guild Settings ──────────────────────

    def get_log_channel_id(
        self,
        guild_id: int,
    ) -> int:
        """取得 Moderation Module 的 Discord 日誌頻道。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT log_channel_id
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        return int(row["log_channel_id"]) if row else 0

    def set_log_channel_id(
        self,
        guild_id: int,
        channel_id: int,
    ) -> None:
        """設定 Moderation Module 的 Discord 日誌頻道。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_settings (
                    guild_id,
                    log_channel_id
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    log_channel_id = excluded.log_channel_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id, channel_id),
            )
