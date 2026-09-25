"""
bot/core/database/migration.py

Modification():

- 提供 Module 自有 Schema Migration 的執行機制。

本檔只管理版本與交易，不包含任何 Module Schema。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import sqlite3

from bot.core.database.sqlite import connect


Migration = Callable[[sqlite3.Connection], None]


def apply_migrations(
    database_path: Path,
    migrations: Sequence[Migration],
) -> None:
    """依序交易式套用尚未執行的 Module Migration。"""

    connection = connect(database_path)
    try:
        current = int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if current > len(migrations):
            raise RuntimeError("Database Schema 版本高於目前 Module")

        for version, migration in enumerate(
            migrations[current:],
            start=current + 1,
        ):
            with connection:
                migration(connection)
                connection.execute(
                    f"PRAGMA user_version = {version}"
                )
    finally:
        connection.close()
