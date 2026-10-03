"""
bot/mod/voice/database.py

Modification():

- 保存每個 Guild 的 JTC 設定。
- 保存現存臨時語音頻道及其擁有者與狀態。
- 提供與舊 vc_repository 相同的非同步資料存取介面。
- Database 僅在 Module setup 時初始化，不在 import 時產生生命週期副作用。

本檔負責 Voice Module 的 SQLite 持久化資料。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3

from bot.core.database.sqlite import connect, initialize


# ── Runtime Database Path ──────────────────────

_database_path: Path | None = None


def configure(database_path: Path) -> None:
    """設定 Voice Module Database 路徑並建立資料表。"""

    global _database_path
    _database_path = database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    initialize(database_path)
    init_tables()


def _connect() -> sqlite3.Connection:
    """建立 Voice Module SQLite Connection。"""

    if _database_path is None:
        raise RuntimeError("Voice Database 尚未 configure()")

    return connect(_database_path)


# ── 初始化 ──────────────────────

def init_tables() -> None:
    """建立語音頻道相關資料表。"""

    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS guild_vc_settings (
            guild_id        INTEGER PRIMARY KEY,
            create_channel  INTEGER DEFAULT 0,
            category_id     INTEGER DEFAULT 0,
            name_template   TEXT    DEFAULT '{username} 的頻道',
            default_limit   INTEGER DEFAULT 0,
            updated_at      REAL    NOT NULL DEFAULT (unixepoch('now'))
        );

        CREATE TABLE IF NOT EXISTS temp_voice_channels (
            channel_id  INTEGER PRIMARY KEY,
            guild_id    INTEGER NOT NULL,
            owner_id    TEXT    NOT NULL,
            name        TEXT    NOT NULL DEFAULT '',
            user_limit  INTEGER NOT NULL DEFAULT 0,
            is_locked   INTEGER NOT NULL DEFAULT 0,
            created_at  REAL    NOT NULL DEFAULT (unixepoch('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_tvc_guild
            ON temp_voice_channels(guild_id);
        """
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


# ── Async Bridge ──────────────────────

async def _to_thread(function, /, *args, **kwargs):
    """將短暫 SQLite 操作委派至背景執行緒。"""

    return await asyncio.to_thread(function, *args, **kwargs)


# ── 伺服器 JTC 設定 ──────────────────────

def _get_vc_settings(guild_id: int) -> dict:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM guild_vc_settings WHERE guild_id = ?",
        (guild_id,),
    ).fetchone()
    conn.close()

    if row:
        return dict(row)

    return {
        "guild_id": guild_id,
        "create_channel": 0,
        "category_id": 0,
        "name_template": "{username} 的頻道",
        "default_limit": 0,
    }


async def get_vc_settings(guild_id: int) -> dict:
    """取得伺服器的 JTC 設定。"""

    return await _to_thread(_get_vc_settings, guild_id)


def _set_vc_setting(guild_id: int, key: str, value) -> None:
    allowed = frozenset({
        "create_channel",
        "category_id",
        "name_template",
        "default_limit",
    })
    if key not in allowed:
        raise ValueError(f"不允許的設定欄位: {key}")

    conn = _connect()
    conn.execute(
        f"""
        INSERT INTO guild_vc_settings (guild_id, {key})
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            {key} = excluded.{key},
            updated_at = unixepoch('now')
        """,
        (guild_id, value),
    )
    conn.commit()
    conn.close()


async def set_vc_setting(guild_id: int, key: str, value) -> None:
    """更新 JTC 設定的單一欄位。"""

    await _to_thread(_set_vc_setting, guild_id, key, value)


# ── 臨時語音頻道 ──────────────────────

def _create_channel(
    channel_id: int,
    guild_id: int,
    owner_id: str,
    name: str,
    user_limit: int = 0,
) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO temp_voice_channels
            (channel_id, guild_id, owner_id, name, user_limit)
        VALUES (?, ?, ?, ?, ?)
        """,
        (channel_id, guild_id, owner_id, name, user_limit),
    )
    conn.commit()
    conn.close()


async def create_channel(
    channel_id: int,
    guild_id: int,
    owner_id: str,
    name: str,
    user_limit: int = 0,
) -> None:
    """記錄新建立的臨時語音頻道。"""

    await _to_thread(
        _create_channel,
        channel_id,
        guild_id,
        owner_id,
        name,
        user_limit,
    )


def _delete_channel(channel_id: int) -> None:
    conn = _connect()
    conn.execute(
        "DELETE FROM temp_voice_channels WHERE channel_id = ?",
        (channel_id,),
    )
    conn.commit()
    conn.close()


async def delete_channel(channel_id: int) -> None:
    """移除臨時語音頻道紀錄。"""

    await _to_thread(_delete_channel, channel_id)


def _get_channel(channel_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM temp_voice_channels WHERE channel_id = ?",
        (channel_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


async def get_channel(channel_id: int) -> dict | None:
    """依頻道 ID 查詢臨時頻道資料。"""

    return await _to_thread(_get_channel, channel_id)


def _get_all_channels(guild_id: int) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM temp_voice_channels WHERE guild_id = ?",
        (guild_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


async def get_all_channels(guild_id: int) -> list[dict]:
    """取得伺服器所有現存的臨時語音頻道。"""

    return await _to_thread(_get_all_channels, guild_id)


def _update_channel(channel_id: int, key: str, value) -> None:
    allowed = frozenset({
        "owner_id",
        "name",
        "user_limit",
        "is_locked",
    })
    if key not in allowed:
        raise ValueError(f"不允許的欄位: {key}")

    conn = _connect()
    conn.execute(
        f"""
        UPDATE temp_voice_channels
        SET {key} = ?
        WHERE channel_id = ?
        """,
        (value, channel_id),
    )
    conn.commit()
    conn.close()


async def update_channel(channel_id: int, key: str, value) -> None:
    """更新臨時頻道的單一屬性。"""

    await _to_thread(_update_channel, channel_id, key, value)


def _is_temp_channel(channel_id: int) -> bool:
    conn = _connect()
    found = conn.execute(
        "SELECT 1 FROM temp_voice_channels WHERE channel_id = ?",
        (channel_id,),
    ).fetchone() is not None
    conn.close()
    return found


async def is_temp_channel(channel_id: int) -> bool:
    """快速判斷頻道是否為本系統管理的臨時頻道。"""

    return await _to_thread(_is_temp_channel, channel_id)
