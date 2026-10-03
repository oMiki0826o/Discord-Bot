"""
bot/mod/ticket/database.py

Modification():

- 建立 Ticket Module 自有的 SQLite Database。
- 保存工單紀錄、狀態、建立者與關閉者。
- 保存每個 Guild 的工單類別、支援身分組與流水號。
- 提供工單建立、關閉、查詢與統計操作。

本檔只負責 Ticket Module 的持久化資料。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time

from bot.core.database.sqlite import connect, initialize


# ── Models ──────────────────────

@dataclass(frozen=True, slots=True)
class TicketRecord:
    """單筆工單紀錄。"""

    ticket_id: int
    guild_id: int
    channel_id: int
    user_id: int
    topic: str
    status: str
    created_at: int
    closed_at: int | None
    closed_by: int | None


@dataclass(frozen=True, slots=True)
class TicketGuildSettings:
    """單一 Guild 的 Ticket Module 設定。"""

    category_id: int = 0
    support_role_id: int = 0
    ticket_count: int = 0


@dataclass(frozen=True, slots=True)
class TicketStats:
    """Guild 工單統計。"""

    total: int
    open_count: int
    closed_count: int


# ── Database ──────────────────────

class TicketDatabase:
    """管理 Ticket Module 的 SQLite 資料。"""

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
        """建立 Ticket Module 所需資料表與索引。"""

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    topic TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open', 'closed')),
                    created_at INTEGER NOT NULL,
                    closed_at INTEGER,
                    closed_by INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_tickets_guild_user_status
                ON tickets(guild_id, user_id, status);

                CREATE INDEX IF NOT EXISTS idx_tickets_guild_status
                ON tickets(guild_id, status);

                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    category_id INTEGER NOT NULL DEFAULT 0,
                    support_role_id INTEGER NOT NULL DEFAULT 0,
                    ticket_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    # ── Guild Settings ──────────────────────

    def get_guild_settings(
        self,
        guild_id: int,
    ) -> TicketGuildSettings:
        """取得 Guild 的 Ticket Module 設定。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    category_id,
                    support_role_id,
                    ticket_count
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        if row is None:
            return TicketGuildSettings()

        return TicketGuildSettings(
            category_id=int(row["category_id"]),
            support_role_id=int(row["support_role_id"]),
            ticket_count=int(row["ticket_count"]),
        )

    def set_guild_setting(
        self,
        guild_id: int,
        key: str,
        value: int,
    ) -> None:
        """更新 Ticket Module 允許的 Guild 設定欄位。"""

        allowed = {
            "category_id",
            "support_role_id",
        }

        if key not in allowed:
            raise ValueError(
                f"Unsupported ticket setting: {key}"
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
                (guild_id, value),
            )

    def next_ticket_number(
        self,
        guild_id: int,
    ) -> int:
        """原子增加 Guild 工單流水號並回傳新值。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_settings (
                    guild_id,
                    ticket_count
                )
                VALUES (?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET
                    ticket_count = ticket_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (guild_id,),
            )
            row = connection.execute(
                """
                SELECT ticket_count
                FROM guild_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        return int(row["ticket_count"]) if row else 1

    # ── Tickets ──────────────────────

    def create_ticket(
        self,
        *,
        guild_id: int,
        channel_id: int,
        user_id: int,
        topic: str,
    ) -> int:
        """建立工單紀錄並回傳 Ticket ID。"""

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tickets (
                    guild_id,
                    channel_id,
                    user_id,
                    topic,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'open', ?)
                """,
                (
                    guild_id,
                    channel_id,
                    user_id,
                    topic,
                    int(time.time()),
                ),
            )

        return int(cursor.lastrowid)

    def get_ticket_by_channel(
        self,
        channel_id: int,
    ) -> TicketRecord | None:
        """依 Discord 頻道 ID 取得工單。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM tickets
                WHERE channel_id = ?
                """,
                (channel_id,),
            ).fetchone()

        return (
            self._row_to_ticket(row)
            if row is not None
            else None
        )

    def get_open_tickets_by_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[TicketRecord]:
        """取得使用者在 Guild 中所有開啟工單。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM tickets
                WHERE guild_id = ?
                  AND user_id = ?
                  AND status = 'open'
                ORDER BY created_at
                """,
                (guild_id, user_id),
            ).fetchall()

        return [
            self._row_to_ticket(row)
            for row in rows
        ]

    def close_ticket(
        self,
        channel_id: int,
        closed_by: int,
    ) -> bool:
        """以條件 UPDATE 原子關閉工單。"""

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tickets
                SET
                    status = 'closed',
                    closed_at = ?,
                    closed_by = ?
                WHERE channel_id = ?
                  AND status = 'open'
                """,
                (
                    int(time.time()),
                    closed_by,
                    channel_id,
                ),
            )

        return cursor.rowcount == 1

    def get_guild_stats(
        self,
        guild_id: int,
    ) -> TicketStats:
        """取得 Guild 工單總數與狀態統計。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END)
                        AS open_count,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END)
                        AS closed_count
                FROM tickets
                WHERE guild_id = ?
                """,
                (guild_id,),
            ).fetchone()

        if row is None:
            return TicketStats(
                total=0,
                open_count=0,
                closed_count=0,
            )

        return TicketStats(
            total=int(row["total"] or 0),
            open_count=int(row["open_count"] or 0),
            closed_count=int(row["closed_count"] or 0),
        )

    # ── Serialization ──────────────────────

    @staticmethod
    def _row_to_ticket(
        row: sqlite3.Row,
    ) -> TicketRecord:
        """將 SQLite Row 轉為 TicketRecord。"""

        return TicketRecord(
            ticket_id=int(row["ticket_id"]),
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            user_id=int(row["user_id"]),
            topic=str(row["topic"]),
            status=str(row["status"]),
            created_at=int(row["created_at"]),
            closed_at=(
                int(row["closed_at"])
                if row["closed_at"] is not None
                else None
            ),
            closed_by=(
                int(row["closed_by"])
                if row["closed_by"] is not None
                else None
            ),
        )
