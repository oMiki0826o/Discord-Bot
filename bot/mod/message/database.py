"""
bot/mod/message/database.py

Modification():

- 建立 Message Module 自有的 SQLite Database。
- 保存各 Guild 是否要求訊息管理權限。
- 提供 Message Module 權限設定的讀取與更新。

本檔只負責 Message Module 的持久化資料。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bot.core.database.sqlite import connect, initialize


# ── Database ──────────────────────

class MessageDatabase:
    """管理 Message Module 的 Guild 設定資料。"""

    def __init__(
        self,
        database_path: Path,
        *,
        default_require_management: bool,
    ) -> None:
        self.database_path = database_path
        self.default_require_management = default_require_management

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
        """建立 Message Module 所需資料表。"""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    require_management INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def requires_management(
        self,
        guild_id: int,
    ) -> bool:
        """取得 Guild 是否要求管理權限。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT require_management
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        if row is None:
            return self.default_require_management

        return bool(
            row["require_management"]
        )

    def set_require_management(
        self,
        guild_id: int,
        enabled: bool,
    ) -> None:
        """更新 Guild 的管理權限限制。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_settings (
                    guild_id,
                    require_management
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    require_management = excluded.require_management,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    guild_id,
                    int(enabled),
                ),
            )
