"""
bot/mod/ai/memory/global_memory.py

Modification():

- Owner-managed global memory backed by the editable prompt JSON source。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from ..prompt.loader import PromptSourceLoader

_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")


class GlobalMemoryService:
    def __init__(self, path: Path, *, prompts: PromptSourceLoader) -> None:
        self.path = Path(path)
        self.prompts = prompts

    def list(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"key": item["key"], "content": item["content"], "importance": item["importance"]}
            for item in self._document()["memories"]
        )

    def upsert(self, key: str, content: str, *, importance: int = 5) -> None:
        normalized_key = key.strip().casefold()
        if _KEY.fullmatch(normalized_key) is None:
            raise ValueError("memory key must use lowercase letters, numbers, dots, hyphens, or underscores")
        normalized_content = content.strip()
        if not normalized_content or len(normalized_content) > 4_000:
            raise ValueError("memory content must be 1..4000 characters")
        if not isinstance(importance, int) or isinstance(importance, bool) or not 1 <= importance <= 5:
            raise ValueError("importance must be 1..5")
        document = self._document()
        record = {"key": normalized_key, "category": normalized_key.split(".", 1)[0], "content": normalized_content, "importance": importance}
        for index, item in enumerate(document["memories"]):
            if item["key"] == normalized_key:
                document["memories"][index] = record
                break
        else:
            document["memories"].append(record)
        self._write_reload(document)

    def remove(self, key: str) -> bool:
        document = self._document()
        normalized_key = key.strip().casefold()
        retained = [item for item in document["memories"] if item["key"] != normalized_key]
        if len(retained) == len(document["memories"]):
            return False
        document["memories"] = retained
        self._write_reload(document)
        return True

    def _document(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.is_file():
            return {"memories": []}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            raw = {"memories": raw}
        memories = raw.get("memories") if isinstance(raw, dict) else None
        if not isinstance(memories, list):
            raise ValueError("memory.json memories must be an array")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(memories):
            content = item.get("content") if isinstance(item, dict) else item
            if not isinstance(content, str) or not content.strip():
                raise ValueError("memory.json contains an invalid memory")
            key = str(item.get("key") if isinstance(item, dict) else f"general.memory_{index + 1}").strip().casefold()
            if _KEY.fullmatch(key) is None:
                key = f"general.memory_{index + 1}"
            importance = item.get("importance", 3) if isinstance(item, dict) else 3
            normalized.append({"key": key, "category": key.split(".", 1)[0], "content": content.strip(), "importance": importance if isinstance(importance, int) and 1 <= importance <= 5 else 3})
        return {"memories": normalized}

    def _write_reload(self, document: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.prompts.reload()
