"""
bot/mod/ai/profiles/repository.py

Modification():

- 建立明確公開、可供其他使用者查詢的 Profile Repository。
- 提供只针對公開欄位的名稱／內容查找。

本檔案不會從私人 Memory 自動複製資料。
"""

from __future__ import annotations

import json
from typing import Any

from ..database import AiDatabase
from ..json_values import normalize_json_value


class PublicProfileRepository:
    def __init__(self, database: AiDatabase) -> None:
        self.database = database

    def put(self, user_id: str, key: str, value: Any, *, now: int) -> None:
        if not user_id.strip() or not key.strip():
            raise ValueError("user_id/key must not be blank")
        normalized = normalize_json_value(value, field_name="public profile", max_bytes=4000)
        payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public_profiles (user_id, profile_key, value_json, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, profile_key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                (user_id, key, payload, now),
            )

    def get(self, user_id: str) -> dict[str, Any]:
        if not user_id.strip():
            raise ValueError("user_id must not be blank")
        with self.database.connect() as connection:
            rows = connection.execute("SELECT profile_key, value_json FROM public_profiles WHERE user_id = ? ORDER BY profile_key", (user_id,)).fetchall()
        return {str(row["profile_key"]): json.loads(str(row["value_json"])) for row in rows}

    def search(self, query: str, *, limit: int = 10) -> tuple[tuple[str, dict[str, Any]], ...]:
        normalized = query.strip().casefold()
        if not normalized:
            raise ValueError("query must not be blank")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT user_id, profile_key, value_json FROM public_profiles "
                "ORDER BY user_id, profile_key"
            ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        searchable: dict[str, list[str]] = {}
        for row in rows:
            user_id = str(row["user_id"])
            key = str(row["profile_key"])
            value_json = str(row["value_json"])
            grouped.setdefault(user_id, {})[key] = json.loads(value_json)
            searchable.setdefault(user_id, [user_id.casefold()]).extend((key.casefold(), value_json.casefold()))
        matches = [
            (user_id, grouped[user_id])
            for user_id in sorted(grouped)
            if normalized in " ".join(searchable[user_id])
        ]
        return tuple(matches[:limit])

    def remove(self, user_id: str, key: str) -> bool:
        with self.database.transaction() as connection:
            return connection.execute("DELETE FROM public_profiles WHERE user_id = ? AND profile_key = ?", (user_id, key)).rowcount == 1
