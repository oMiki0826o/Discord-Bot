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

from bot.core.database.migration import apply_migrations
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
        """交易式升級 Guild Module Schema。"""

        def version_1(connection: sqlite3.Connection) -> None:
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

        def version_2(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_stat_channels (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    metric TEXT NOT NULL,
                    label_template TEXT NOT NULL,
                    role_id INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_rendered_name TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id)
                )
                """
            )

        def version_3(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_announcements (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    target_channel_id INTEGER NOT NULL,
                    mention_role_id INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    color INTEGER NOT NULL,
                    image_url TEXT NOT NULL DEFAULT '',
                    attachment_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    scheduled_at TEXT,
                    claimed_at TEXT,
                    published_at TEXT,
                    discord_message_id INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

        def version_4(connection: sqlite3.Connection) -> None:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_announcements_due "
                "ON guild_announcements(status, scheduled_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_announcements_history "
                "ON guild_announcements(guild_id, created_at DESC)"
            )

        apply_migrations(
            self.database_path,
            (version_1, version_2, version_3, version_4),
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
