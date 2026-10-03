"""
bot/mod/ai/memory/mirror.py

Modification():

- 將 SQLite Active Memory 匯出為 Owner 可編輯 JSON 鏡像。
- 驗證 JSON user/scope/identity/value 後，以單一 Transaction 套用新增、修改與撤銷。
- Owner 修改一律建立新 Memory 版本，不覆寫既有歷史或 Evidence。
- 記錄本程式原子寫入的內容雜湊，供 Watcher 排除自寫事件。

SQLite 仍是執行時唯一查詢來源；JSON 只作為 Owner 管理介面。
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

from ..database import AiDatabase
from .models import (
    AssertionStrength,
    MemoryCandidate,
    MemoryScopeType,
    TemporalScope,
    dump_json_value,
)
from .repository import MemoryRepository

_FILE_USER_ID = re.compile(r"\((\d{17,20})\)\.json$")


@dataclass(frozen=True, slots=True)
class MirrorApplyReport:
    """Owner JSON 套用結果。"""

    user_id: str
    added: int = 0
    updated: int = 0
    retracted: int = 0
    output_path: Path | None = None

    @property
    def changed(self) -> int:
        return self.added + self.updated + self.retracted


@dataclass(frozen=True, slots=True)
class _MirrorEntry:
    memory_id: str | None
    scope_type: MemoryScopeType
    scope_id: str
    memory_type: str
    memory_key: str
    value: object
    importance: int

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.scope_type.value,
            self.scope_id,
            self.memory_type,
            self.memory_key,
        )


class MemoryMirrorService:
    """在 Owner JSON 與 durable SQLite Memory 之間做安全同步。"""

    def __init__(
        self,
        database: AiDatabase,
        root: Path,
        *,
        clock=None,
    ) -> None:
        self.database = database
        self.root = Path(root)
        self.repository = MemoryRepository(database)
        self.clock = clock or (lambda: int(time.time()))
        self._written_hashes: dict[Path, str] = {}
        self._user_paths: dict[str, Path] = {}

    # ── Export ──────────────────────

    def export_user(
        self,
        user_id: str,
        display_name: str | None = None,
    ) -> Path:
        """匯出使用者目前的 Active Memory，不輸出歷史 Evidence 內容。"""

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT memory_id, scope_type, scope_id, memory_type, memory_key,
                       value_json, importance, status, created_at, updated_at
                FROM memories
                WHERE user_id = ? AND status = 'active'
                ORDER BY scope_type, scope_id, memory_type, memory_key, memory_id
                """,
                (user_id,),
            ).fetchall()

        if display_name is None and user_id in self._user_paths:
            path = self._user_paths[user_id]
        else:
            name = self._safe_display_name(display_name or user_id)
            path = self.root / f"{name}({user_id}).json"
            self._user_paths[user_id] = path
        document = {
            "schema_version": 1,
            "user_id": user_id,
            "memories": [
                {
                    "memory_id": str(row["memory_id"]),
                    "scope_type": str(row["scope_type"]),
                    "scope_id": str(row["scope_id"]),
                    "memory_type": str(row["memory_type"]),
                    "memory_key": str(row["memory_key"]),
                    "value": json.loads(str(row["value_json"])),
                    "importance": int(row["importance"]),
                    "status": str(row["status"]),
                    "created_at": int(row["created_at"]),
                    "updated_at": int(row["updated_at"]),
                }
                for row in rows
            ],
        }
        self._write(path, document)
        return path

    def export_all_changed(
        self,
        user_ids: Collection[str],
    ) -> tuple[Path, ...]:
        """穩定順序匯出一組使用者鏡像。"""

        return tuple(self.export_user(user_id) for user_id in sorted(set(user_ids)))

    # ── Apply Owner Changes ──────────────────────

    def apply_path(
        self,
        path: Path,
        *,
        actor_id: str = "owner-json",
    ) -> MirrorApplyReport:
        """驗證並原子套用一份 Owner JSON；任何錯誤都不修改 SQLite。"""

        path = Path(path)
        user_id, entries = self._read_document(path)
        self._user_paths[user_id] = path
        now = self.clock()
        added = 0
        updated = 0
        retracted = 0

        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT memory_id, scope_type, scope_id, memory_type, memory_key,
                       value_json, importance
                FROM memories
                WHERE user_id = ? AND status = 'active'
                """,
                (user_id,),
            ).fetchall()
            active = {str(row["memory_id"]): row for row in rows}
            incoming_ids = {
                entry.memory_id
                for entry in entries
                if entry.memory_id is not None
            }

            unknown_ids = sorted(incoming_ids - active.keys())
            if unknown_ids:
                raise ValueError(
                    "JSON 含有不是此使用者 Active Memory 的 memory_id："
                    + ", ".join(unknown_ids[:3])
                )

            # Existing entries cannot change identity/scope in place. A change
            # of identity must be represented as delete + new item without ID.
            for entry in entries:
                if entry.memory_id is None:
                    continue
                row = active[entry.memory_id]
                stored_identity = (
                    str(row["scope_type"]),
                    str(row["scope_id"]),
                    str(row["memory_type"]),
                    str(row["memory_key"]),
                )
                if entry.identity != stored_identity:
                    raise ValueError(
                        f"memory_id {entry.memory_id} 的 identity/scope 不可直接修改"
                    )

            # Duplicate active identities are rejected before any write.
            identities = [entry.identity for entry in entries]
            if len(identities) != len(set(identities)):
                raise ValueError("JSON 不可包含重複的 Memory identity/scope")

            # Deletion means explicit Owner retraction and creates an override.
            for memory_id in sorted(active.keys() - incoming_ids):
                self.repository.retract(
                    memory_id,
                    actor_id=actor_id,
                    now=now,
                    connection=connection,
                )
                retracted += 1

            for entry in entries:
                if entry.memory_id is None:
                    self.repository.owner_upsert(
                        user_id=user_id,
                        scope_type=entry.scope_type,
                        scope_id=entry.scope_id,
                        memory_type=entry.memory_type,
                        memory_key=entry.memory_key,
                        value=entry.value,
                        importance=entry.importance,
                        actor_id=actor_id,
                        now=now,
                        connection=connection,
                    )
                    added += 1
                    continue

                row = active[entry.memory_id]
                if (
                    dump_json_value(entry.value) == str(row["value_json"])
                    and entry.importance == int(row["importance"])
                ):
                    continue

                self.repository.owner_upsert(
                    user_id=user_id,
                    scope_type=entry.scope_type,
                    scope_id=entry.scope_id,
                    memory_type=entry.memory_type,
                    memory_key=entry.memory_key,
                    value=entry.value,
                    importance=entry.importance,
                    actor_id=actor_id,
                    now=now,
                    connection=connection,
                    existing_id=entry.memory_id,
                )
                updated += 1

        output = self.export_user(user_id)
        return MirrorApplyReport(
            user_id=user_id,
            added=added,
            updated=updated,
            retracted=retracted,
            output_path=output,
        )

    def apply_deleted_path(
        self,
        path: Path,
        *,
        actor_id: str = "owner-json",
    ) -> MirrorApplyReport:
        """將整份鏡像刪除解讀為撤銷該使用者全部 Active Memory。"""

        path = Path(path)
        user_id = self.user_id_from_path(path)
        if user_id is None:
            raise ValueError(f"無法從檔名判斷 user_id：{path.name}")

        now = self.clock()
        retracted = 0
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT memory_id FROM memories WHERE user_id = ? AND status = 'active'",
                (user_id,),
            ).fetchall()
            for row in rows:
                self.repository.retract(
                    str(row["memory_id"]),
                    actor_id=actor_id,
                    now=now,
                    connection=connection,
                )
                retracted += 1

        self._user_paths.pop(user_id, None)
        return MirrorApplyReport(user_id=user_id, retracted=retracted)

    # ── Startup / Watcher Coordination ──────────────────────

    def prepare_initial_state(self) -> tuple[Path, ...]:
        """先套用既有 Owner JSON，再只回填沒有鏡像檔的 SQLite 使用者。"""

        self.root.mkdir(parents=True, exist_ok=True)
        protected_user_ids: set[str] = set()
        for path in sorted(self.root.glob("*.json")):
            user_id = self.user_id_from_path(path)
            if user_id is not None:
                protected_user_ids.add(user_id)
            try:
                self.apply_path(path)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                # Invalid/pending Owner files are intentionally left untouched;
                # the watcher will retry after their content changes.
                continue

        with self.database.connect() as connection:
            user_ids = {
                str(row["user_id"])
                for row in connection.execute(
                    "SELECT DISTINCT user_id FROM memories WHERE status = 'active'"
                )
            }

        exported = []
        for user_id in sorted(user_ids - protected_user_ids):
            exported.append(self.export_user(user_id))
        return tuple(exported)

    def consume_written_hash(self, path: Path, digest: str) -> bool:
        """Watcher 取用本程式最近一次寫入雜湊，避免把自寫視為 Owner 修改。"""

        normalized = Path(path)
        if self._written_hashes.get(normalized) != digest:
            return False
        self._written_hashes.pop(normalized, None)
        return True

    @staticmethod
    def user_id_from_path(path: Path) -> str | None:
        match = _FILE_USER_ID.search(Path(path).name)
        if match is None:
            return None
        value = match.group(1).strip()
        return value or None

    # ── Validation / Atomic IO ──────────────────────

    def _read_document(self, path: Path) -> tuple[str, tuple[_MirrorEntry, ...]]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Memory mirror 根節點必須是 JSON Object")
        if raw.get("schema_version") != 1:
            raise ValueError("Memory mirror schema_version 必須是 1")

        user_id = raw.get("user_id")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("Memory mirror user_id 不得空白")
        user_id = user_id.strip()
        path_user_id = self.user_id_from_path(path)
        if path_user_id != user_id:
            raise ValueError("Memory mirror 檔名 user_id 與文件內容不一致")

        raw_memories = raw.get("memories")
        if not isinstance(raw_memories, list):
            raise ValueError("Memory mirror memories 必須是 JSON Array")

        entries: list[_MirrorEntry] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(raw_memories):
            if not isinstance(item, dict):
                raise ValueError(f"memories[{index}] 必須是 JSON Object")

            memory_id_value = item.get("memory_id")
            if memory_id_value is None:
                memory_id = None
            elif isinstance(memory_id_value, str) and memory_id_value.strip():
                memory_id = memory_id_value.strip()
                if memory_id in seen_ids:
                    raise ValueError(f"重複 memory_id：{memory_id}")
                seen_ids.add(memory_id)
            else:
                raise ValueError(f"memories[{index}].memory_id 格式錯誤")

            try:
                scope_type = MemoryScopeType(str(item["scope_type"]))
                scope_id = str(item["scope_id"]).strip()
                memory_type = str(item["memory_type"]).strip()
                memory_key = str(item["memory_key"]).strip()
                value = item["value"]
                importance = item["importance"]
            except KeyError as exc:
                raise ValueError(
                    f"memories[{index}] 缺少欄位：{exc.args[0]}"
                ) from exc

            if not scope_id:
                raise ValueError(f"memories[{index}].scope_id 不得空白")
            if isinstance(importance, bool) or not isinstance(importance, int):
                raise ValueError(f"memories[{index}].importance 必須是整數")

            # Reuse the domain model's strict identity/value validation without
            # creating a Candidate row or fake Event evidence.
            validated = MemoryCandidate(
                candidate_id=f"mirror-validation-{index}",
                source_event_id="owner-json",
                user_id=user_id,
                scope_type=scope_type,
                scope_id=scope_id,
                memory_type=memory_type,
                memory_key=memory_key,
                value=value,
                confidence=1.0,
                importance=importance,
                assertion_strength=AssertionStrength.EXPLICIT,
                temporal_scope=TemporalScope.PERMANENT,
                observed_at=0,
            )
            entries.append(
                _MirrorEntry(
                    memory_id=memory_id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    memory_type=memory_type,
                    memory_key=memory_key,
                    value=validated.value,
                    importance=validated.importance,
                )
            )

        return user_id, tuple(entries)

    @staticmethod
    def _safe_display_name(value: str) -> str:
        name = value.replace("/", "_").replace("\\", "_").strip()
        return name or "user"

    def _write(self, path: Path, document: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self._written_hashes[path] = hashlib.sha256(payload).hexdigest()
