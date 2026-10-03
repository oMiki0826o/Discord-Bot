"""
bot/mod/ai/memory/manual_source.py

Modification():

讀取 Owner 維護的 ``data/ai/users_memory/*.json``。

這是手動資料來源，不是 Evidence-driven 自動長期記憶。每次查詢都重新讀檔，
因此使用者修改 JSON 後無須等待索引或重啟；資料庫也不會成為它的第二份真相。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..history.lexical import normalize_lexical_document

_FILE_PATTERN = re.compile(r"^.+\((?P<user_id>\d{17,20})\)\.json$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ManualMemoryItem:
    user_id: str
    key: str
    value: Any
    memory_type: str
    importance: int
    source_file: str


class ManualMemorySource:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._errors: tuple[str, ...] = ()

    def validation_errors(self) -> tuple[str, ...]:
        return self._errors

    def search(self, *, user_id: str, query: str, limit: int) -> tuple[ManualMemoryItem, ...]:
        if not user_id.strip() or not query.strip() or not 1 <= limit <= 100:
            raise ValueError("invalid manual memory query")
        records, errors = self._read_user(user_id)
        self._errors = errors
        tokens = set(normalize_lexical_document(query).split())
        ranked: list[tuple[int, int, str, ManualMemoryItem]] = []
        for item in records:
            searchable = normalize_lexical_document(
                f"{item.memory_type} {item.key} {json.dumps(item.value, ensure_ascii=False, sort_keys=True)}"
            )
            score = len(tokens.intersection(searchable.split()))
            if tokens and score == 0:
                continue
            ranked.append((score, item.importance, item.key, item))
        ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
        return tuple(row[3] for row in ranked[:limit])

    def _read_user(self, user_id: str) -> tuple[tuple[ManualMemoryItem, ...], tuple[str, ...]]:
        if not self.root.is_dir():
            return (), ()
        records: list[ManualMemoryItem] = []
        errors: list[str] = []
        for path in sorted(self.root.glob("*.json")):
            match = _FILE_PATTERN.fullmatch(path.name)
            if match is None or match.group("user_id") != user_id:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                records.extend(self._parse(path, user_id, payload))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                errors.append(f"{path.name}: {error}")
        return tuple(records), tuple(errors)

    @staticmethod
    def _parse(path: Path, user_id: str, payload: Any) -> tuple[ManualMemoryItem, ...]:
        if not isinstance(payload, dict) or str(payload.get("user_id", "")) != user_id:
            raise ValueError("user_id must match the file name")
        items: list[ManualMemoryItem] = []
        preferences = payload.get("preferences", {})
        if not isinstance(preferences, dict):
            raise ValueError("preferences must be an object")
        for key, value in preferences.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("preference key must not be blank")
            items.append(ManualMemoryItem(user_id, key, value, "manual_preference", 4, path.name))
        memories = payload.get("memories", [])
        if not isinstance(memories, list):
            raise ValueError("memories must be an array")
        for index, entry in enumerate(memories):
            if not isinstance(entry, dict) or not isinstance(entry.get("content"), str) or not entry["content"].strip():
                raise ValueError("memory content must not be blank")
            importance = entry.get("importance", 3)
            if not isinstance(importance, int) or isinstance(importance, bool) or not 1 <= importance <= 5:
                raise ValueError("memory importance must be between 1 and 5")
            category = entry.get("category", "manual_note")
            if not isinstance(category, str) or not category.strip():
                raise ValueError("memory category must not be blank")
            items.append(ManualMemoryItem(user_id, f"{category}:{index}", entry["content"], category, importance, path.name))
        return tuple(items)
