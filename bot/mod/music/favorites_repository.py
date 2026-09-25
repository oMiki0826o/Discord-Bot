"""
bot/mod/music/favorites_repository.py

Modification():

- 提供收藏功能既有的非同步 Repository 介面。
- 將所有收藏操作轉交 MusicDatabase。
- 避免 Favorites UI 直接持有 SQLite Connection 或 Database Path。

本檔是 Music Module 內部的收藏資料介面。
"""

from __future__ import annotations

from bot.mod.music.database import MusicDatabase


_database: MusicDatabase | None = None


def bind(database: MusicDatabase) -> None:
    global _database
    _database = database


def _get_database() -> MusicDatabase:
    if _database is None:
        raise RuntimeError("Music Database 尚未綁定")
    return _database


async def add_favorite(user_id: str, title: str, url: str, duration: int = 0) -> bool:
    return await _get_database().add_favorite(user_id, title, url, duration)


async def remove_favorite(user_id: str, url: str) -> bool:
    return await _get_database().remove_favorite(user_id, url)


async def clear_favorites(user_id: str) -> int:
    return await _get_database().clear_favorites(user_id)


async def get_favorites(user_id: str) -> list[dict]:
    return await _get_database().get_favorites(user_id)


async def is_favorite(user_id: str, url: str) -> bool:
    return await _get_database().is_favorite(user_id, url)
