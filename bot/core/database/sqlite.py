"""
bot/core/database/sqlite.py

Modification():

- 建立 Module 共用的 SQLite Connection。
- 統一套用 SQLite 安全與併發設定。

本檔只負責 SQLite 引擎連線，不管理 Module Schema 或資料表。
"""

from __future__ import annotations

from pathlib import Path
import sqlite3


def connect(
    database_path: Path,
    *,
    timeout_seconds: float = 5.0,
) -> sqlite3.Connection:
    """建立已套用專案共用 PRAGMA 的短生命週期連線。"""

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        database_path,
        timeout=timeout_seconds,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize(database_path: Path) -> None:
    """初始化 SQLite 檔案層級設定；每個 Database 建立時呼叫一次。"""

    connection = connect(database_path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
    finally:
        connection.close()
