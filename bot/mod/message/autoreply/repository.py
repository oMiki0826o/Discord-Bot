"""
bot/mod/message/autoreply/repository.py

Modification():

- Atomic JSON persistence with last-known-good fallback。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile

import regex

from bot.core.logging.manager import LogManager
from bot.mod.message.autoreply.model import AutoReplyDocument


logger = LogManager().get_logger("message.autoreply.repository")


@dataclass(frozen=True, slots=True)
class RepositoryHealth:
    healthy: bool
    error: str = ""


class AutoReplyRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._cache: dict[int, AutoReplyDocument] = {}
        self._health: dict[int, RepositoryHealth] = {}
        self._file_signatures: dict[int, tuple[int, int]] = {}

    def _path(self, guild_id: int) -> Path:
        return self.directory / f"{guild_id}.json"

    def load(self, guild_id: int, *, force: bool = False) -> AutoReplyDocument:
        path = self._path(guild_id)
        if not path.exists():
            document = AutoReplyDocument(1, guild_id, ())
            self._cache[guild_id] = document
            self._health[guild_id] = RepositoryHealth(True)
            return document
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if (
            not force
            and guild_id in self._cache
            and self._file_signatures.get(guild_id) == signature
        ):
            return self._cache[guild_id]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            document = AutoReplyDocument.from_dict(raw)
            if document.guild_id != guild_id:
                raise ValueError("guild_id 與檔名不一致")
            for rule in document.rules:
                if rule.mode.value == "regex":
                    regex.compile(rule.pattern)
        except (OSError, json.JSONDecodeError, ValueError, regex.error) as exc:
            self._file_signatures[guild_id] = signature
            self._health[guild_id] = RepositoryHealth(False, str(exc))
            logger.error("自動回覆規則載入失敗 guild=%s file=%s error=%s", guild_id, path, exc)
            return self._cache.get(guild_id, AutoReplyDocument(1, guild_id, ()))
        self._cache[guild_id] = document
        self._file_signatures[guild_id] = signature
        self._health[guild_id] = RepositoryHealth(True)
        return document

    def save(self, guild_id: int, document: AutoReplyDocument) -> None:
        if document.guild_id != guild_id:
            raise ValueError("guild_id 與文件 guild 不一致")
        payload = document.to_dict()
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{guild_id}-", suffix=".tmp", dir=self.directory, text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_name, self._path(guild_id))
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        self._cache[guild_id] = AutoReplyDocument.from_dict(payload)
        stat = self._path(guild_id).stat()
        self._file_signatures[guild_id] = (stat.st_mtime_ns, stat.st_size)
        self._health[guild_id] = RepositoryHealth(True)

    def export_bytes(self, guild_id: int) -> bytes:
        document = self.load(guild_id)
        return (json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n").encode()

    def health(self, guild_id: int) -> RepositoryHealth:
        return self._health.get(guild_id, RepositoryHealth(True))
