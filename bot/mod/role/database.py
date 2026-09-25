"""
bot/mod/role/database.py

Modification():

- 建立 Role Module 自有的 SQLite Database。
- 保存身分組自助領取面板與按鈕設定。
- 提供面板查詢、建立、更新與刪除操作。
- 將 JSON 儲存的身分組資料轉換為結構化 Python 資料。

本檔只負責 Role Module 的持久化資料。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from bot.core.database.sqlite import connect, initialize


# ── Models ──────────────────────

@dataclass(frozen=True, slots=True)
class RoleButtonData:
    """身分組面板中的單一按鈕資料。"""

    role_id: int
    label: str
    emoji: str | None
    description: str
    style: str


@dataclass(frozen=True, slots=True)
class RolePanelData:
    """單一身分組自助領取面板。"""

    panel_id: int
    guild_id: int
    channel_id: int
    message_id: int
    title: str
    description: str
    roles: tuple[RoleButtonData, ...]


# ── Database ──────────────────────

class RoleDatabase:
    """管理 Role Module 的 SQLite 資料。"""

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
        """建立 Role Module 所需資料表與索引。"""

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS role_panels (
                    panel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    roles TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_role_panels_guild
                ON role_panels(guild_id);
                """
            )

    def get_panels(
        self,
        guild_id: int,
    ) -> list[RolePanelData]:
        """取得指定 Guild 的全部身分組面板。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM role_panels
                WHERE guild_id = ?
                ORDER BY panel_id
                """,
                (guild_id,),
            ).fetchall()

        return [
            self._row_to_panel(row)
            for row in rows
        ]

    def get_all_panels(
        self,
    ) -> list[RolePanelData]:
        """取得全部面板，用於重建 Persistent View。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM role_panels
                ORDER BY panel_id
                """
            ).fetchall()

        return [
            self._row_to_panel(row)
            for row in rows
        ]

    def get_panel_by_message(
        self,
        message_id: int,
    ) -> RolePanelData | None:
        """依 Discord 訊息 ID 取得面板。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM role_panels
                WHERE message_id = ?
                """,
                (message_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_panel(row)

    def save_panel(
        self,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
        title: str,
        description: str,
        roles: tuple[RoleButtonData, ...],
    ) -> None:
        """建立或更新身分組面板。"""

        payload = json.dumps(
            [
                {
                    "role_id": role.role_id,
                    "label": role.label,
                    "emoji": role.emoji,
                    "description": role.description,
                    "style": role.style,
                }
                for role in roles
            ],
            ensure_ascii=False,
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO role_panels (
                    guild_id,
                    channel_id,
                    message_id,
                    title,
                    description,
                    roles
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    roles = excluded.roles,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    guild_id,
                    channel_id,
                    message_id,
                    title,
                    description,
                    payload,
                ),
            )

    def delete_panel(
        self,
        message_id: int,
    ) -> None:
        """刪除指定身分組面板資料。"""

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM role_panels
                WHERE message_id = ?
                """,
                (message_id,),
            )

    # ── Serialization ──────────────────────

    @staticmethod
    def _row_to_panel(
        row: sqlite3.Row,
    ) -> RolePanelData:
        """將 SQLite Row 轉為 RolePanelData。"""

        try:
            raw_roles = json.loads(
                str(row["roles"])
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            raw_roles = []

        roles: list[RoleButtonData] = []

        if isinstance(raw_roles, list):
            for item in raw_roles:
                if not isinstance(item, dict):
                    continue

                try:
                    roles.append(
                        RoleButtonData(
                            role_id=int(item["role_id"]),
                            label=str(
                                item.get(
                                    "label",
                                    "身分組",
                                )
                            ),
                            emoji=(
                                str(item["emoji"])
                                if item.get("emoji")
                                else None
                            ),
                            description=str(
                                item.get(
                                    "description",
                                    "",
                                )
                            ),
                            style=str(
                                item.get(
                                    "style",
                                    "secondary",
                                )
                            ),
                        )
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    continue

        return RolePanelData(
            panel_id=int(row["panel_id"]),
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            message_id=int(row["message_id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            roles=tuple(roles),
        )
