"""
bot/mod/guild/database.py

Modification():

- 建立 Guild Module 自有的 SQLite Database。
- 保存歡迎、離開、日誌頻道與自動身分組設定。
- 提供 Guild 設定的讀取、更新與重置。

本檔只負責 Guild Module 的持久化資料。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from bot.core.database.sqlite import connect, initialize


# ── Models ──────────────────────

@dataclass(frozen=True, slots=True)
class GuildSettings:
    """單一 Guild 的持久化設定。"""

    welcome_channel_id: int = 0
    leave_channel_id: int = 0
    log_channel_id: int = 0
    auto_role_id: int = 0


# ── Database ──────────────────────

class GuildDatabase:
    """管理 Guild Module 的 SQLite 資料。"""

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
        """建立 Guild Module 所需資料表。"""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel_id INTEGER NOT NULL DEFAULT 0,
                    leave_channel_id INTEGER NOT NULL DEFAULT 0,
                    log_channel_id INTEGER NOT NULL DEFAULT 0,
                    auto_role_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get_settings(
        self,
        guild_id: int,
    ) -> GuildSettings:
        """取得 Guild 設定；不存在時使用預設值。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    welcome_channel_id,
                    leave_channel_id,
                    log_channel_id,
                    auto_role_id
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        if row is None:
            return GuildSettings()

        return GuildSettings(
            welcome_channel_id=int(
                row["welcome_channel_id"]
            ),
            leave_channel_id=int(
                row["leave_channel_id"]
            ),
            log_channel_id=int(
                row["log_channel_id"]
            ),
            auto_role_id=int(
                row["auto_role_id"]
            ),
        )

    def set_setting(
        self,
        guild_id: int,
        key: str,
        value: int,
    ) -> None:
        """更新允許的單一 Guild 設定欄位。"""

        allowed_columns = {
            "welcome_channel_id",
            "leave_channel_id",
            "log_channel_id",
            "auto_role_id",
        }

        if key not in allowed_columns:
            raise ValueError(
                f"Unsupported guild setting: {key}"
            )

        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO guild_settings (
                    guild_id,
                    {key}
                )
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    {key} = excluded.{key},
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    guild_id,
                    value,
                ),
            )

    def reset_settings(
        self,
        guild_id: int,
    ) -> None:
        """移除 Guild 自訂設定，使其回到預設狀態。"""

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
