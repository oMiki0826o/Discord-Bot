"""
bot/mod/ai/memory/repository.py

Modification():

- 保存 Memory Candidate Audit。
- 保存具備 Event Evidence 的 Materialized Memory。
- 提供使用者與 Scope 強制隔離的 Active Memory 查詢。
- 提供確認、取代、Owner 撤銷與 Owner 新版本所需的 Transactional Operations。

本檔只負責 Memory SQLite 存取。
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Sequence

from ..database import AiDatabase
from ..errors import (
    CandidateConflictError,
    EvidenceNotFoundError,
    EvidenceScopeError,
)
from ..history.models import EventRole
from .models import (
    CandidateStatus,
    Memory,
    MemoryCandidate,
    MemoryCandidateRecord,
    MemoryEvidence,
    MemoryQuery,
    MemoryScopeType,
    MemoryStatus,
    dump_memory,
    dump_json_value,
    load_memory,
    load_json_value,
)


# ── Memory Repository ──────────────────────

class MemoryRepository:
    """管理 Candidate、Memory 與 Evidence 的一致性寫入。"""

    def __init__(
        self,
        database: AiDatabase,
    ) -> None:
        self.database = database

    # ── Candidate Audit ──────────────────────

    def save_candidate(
        self,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> CandidateStatus:
        self._validate_evidence(candidate, connection)
        existing = self._get_candidate_with_connection(
            connection,
            candidate.candidate_id,
        )

        if existing is not None:
            if existing.candidate != candidate:
                raise CandidateConflictError(
                    "Candidate ID 已存在且內容不同"
                )
            return existing.status

        connection.execute(
            """
            INSERT INTO memory_candidates (
                candidate_id,
                source_event_id,
                user_id,
                scope_type,
                scope_id,
                memory_type,
                memory_key,
                value_json,
                confidence,
                importance,
                assertion_strength,
                temporal_scope,
                status,
                observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.candidate_id,
                candidate.source_event_id,
                candidate.user_id,
                candidate.scope_type.value,
                candidate.scope_id,
                candidate.memory_type,
                candidate.memory_key,
                dump_json_value(candidate.value),
                candidate.confidence,
                candidate.importance,
                candidate.assertion_strength.value,
                candidate.temporal_scope.value,
                CandidateStatus.PENDING.value,
                candidate.observed_at,
            ),
        )
        return CandidateStatus.PENDING

    def get_candidate(
        self,
        candidate_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> MemoryCandidateRecord | None:
        if connection is not None:
            return self._get_candidate_with_connection(
                connection,
                candidate_id,
            )

        with self.database.connect() as connection:
            return self._get_candidate_with_connection(
                connection,
                candidate_id,
            )

    def mark_candidate(
        self,
        candidate_id: str,
        status: CandidateStatus,
        connection: sqlite3.Connection,
        *,
        action: str | None = None,
        reason: str | None = None,
        memory: Memory | None = None,
    ) -> None:
        changed = connection.execute(
            """
            UPDATE memory_candidates
            SET status = ?, decided_at = ?, result_action = ?,
                result_reason = ?, result_memory_id = ?,
                result_memory_json = ?
            WHERE candidate_id = ?
            """,
            (
                status.value,
                int(time.time()),
                action,
                reason,
                None if memory is None else memory.memory_id,
                None if memory is None else dump_memory(memory),
                candidate_id,
            ),
        ).rowcount

        if changed != 1:
            raise KeyError(f"找不到 Candidate：{candidate_id}")

    # ── Memory Writes ──────────────────────

    def add(
        self,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection | None = None,
    ) -> Memory:
        if connection is None:
            with self.database.transaction() as own_connection:
                return self.add(candidate, own_connection)

        self.save_candidate(candidate, connection)

        memory_id = f"mem-{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO memories (
                memory_id,
                user_id,
                scope_type,
                scope_id,
                memory_type,
                memory_key,
                value_json,
                confidence,
                importance,
                status,
                created_at,
                updated_at,
                last_confirmed_at,
                expires_at,
                superseded_by_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                memory_id,
                candidate.user_id,
                candidate.scope_type.value,
                candidate.scope_id,
                candidate.memory_type,
                candidate.memory_key,
                dump_json_value(candidate.value),
                candidate.confidence,
                candidate.importance,
                MemoryStatus.ACTIVE.value,
                candidate.observed_at,
                candidate.observed_at,
                candidate.observed_at,
            ),
        )
        self._insert_evidence(
            connection,
            memory_id=memory_id,
            candidate=candidate,
            relation="supporting",
        )
        memory = self._get_with_connection(connection, memory_id)
        if memory is None:
            raise RuntimeError("Memory 寫入後無法讀回")
        self.mark_candidate(
            candidate.candidate_id,
            CandidateStatus.ACCEPTED,
            connection,
            action="add",
            reason="new memory",
            memory=memory,
        )
        return memory

    def confirm(
        self,
        memory_id: str,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> Memory:
        self.save_candidate(candidate, connection)
        self._require_target_matches(memory_id, candidate, connection)
        changed = connection.execute(
            """
            UPDATE memories
            SET confidence = max(confidence, ?),
                importance = max(importance, ?),
                updated_at = max(updated_at, ?),
                last_confirmed_at = max(coalesce(last_confirmed_at, 0), ?)
            WHERE memory_id = ? AND status = 'active'
            """,
            (
                candidate.confidence,
                candidate.importance,
                candidate.observed_at,
                candidate.observed_at,
                memory_id,
            ),
        ).rowcount
        if changed != 1:
            raise KeyError(f"找不到 Active Memory：{memory_id}")
        self._insert_evidence(
            connection,
            memory_id=memory_id,
            candidate=candidate,
            relation="supporting",
        )
        memory = self._get_with_connection(connection, memory_id)
        if memory is None:
            raise RuntimeError("Memory 確認後無法讀回")
        return memory

    def supersede(
        self,
        existing_id: str,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> Memory:
        self.save_candidate(candidate, connection)
        self._require_target_matches(existing_id, candidate, connection)
        changed = connection.execute(
            "UPDATE memories SET status = 'superseded', updated_at = ? "
            "WHERE memory_id = ? AND status = 'active'",
            (candidate.observed_at, existing_id),
        ).rowcount
        if changed != 1:
            raise KeyError(f"找不到 Active Memory：{existing_id}")

        replacement = self.add(candidate, connection)
        connection.execute(
            "UPDATE memories SET superseded_by_id = ? WHERE memory_id = ?",
            (replacement.memory_id, existing_id),
        )
        self._insert_evidence(
            connection,
            memory_id=existing_id,
            candidate=candidate,
            relation="contradicting",
        )
        return replacement

    # ── Memory Reads ──────────────────────

    def get(
        self,
        memory_id: str,
    ) -> Memory | None:
        with self.database.connect() as connection:
            return self._get_with_connection(connection, memory_id)

    def get_active_for_key(
        self,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> Memory | None:
        row = connection.execute(
            """
            SELECT * FROM memories
            WHERE user_id = ? AND scope_type = ? AND scope_id = ?
              AND memory_type = ? AND memory_key = ? AND status = 'active'
            """,
            (
                candidate.user_id,
                candidate.scope_type.value,
                candidate.scope_id,
                candidate.memory_type,
                candidate.memory_key,
            ),
        ).fetchone()
        return None if row is None else self._memory_from_row(row)

    def retract(
        self,
        memory_id: str,
        *,
        actor_id: str,
        now: int,
        connection: sqlite3.Connection,
    ) -> None:
        """撤銷 Active Memory，保留 Evidence 並封鎖模型自動重建同鍵。"""

        memory = self._get_with_connection(connection, memory_id)
        if memory is None or memory.status is not MemoryStatus.ACTIVE:
            raise KeyError(f"找不到 Active Memory：{memory_id}")

        connection.execute(
            "UPDATE memories SET status = 'retracted', updated_at = ? "
            "WHERE memory_id = ?",
            (now, memory_id),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO memory_owner_overrides (
                user_id, scope_type, scope_id, memory_type, memory_key,
                actor_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.user_id,
                memory.scope_type.value,
                memory.scope_id,
                memory.memory_type,
                memory.memory_key,
                actor_id,
                now,
            ),
        )
        self._audit_owner(
            connection,
            memory_id=memory_id,
            actor_id=actor_id,
            action="retract",
            now=now,
        )

    def is_owner_blocked(
        self,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> bool:
        """判斷 Candidate 的完整 identity/scope 是否被 Owner 封鎖。"""

        row = connection.execute(
            """
            SELECT 1 FROM memory_owner_overrides
            WHERE user_id = ? AND scope_type = ? AND scope_id = ?
              AND memory_type = ? AND memory_key = ?
            """,
            (
                candidate.user_id,
                candidate.scope_type.value,
                candidate.scope_id,
                candidate.memory_type,
                candidate.memory_key,
            ),
        ).fetchone()
        return row is not None

    def clear_owner_block(
        self,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> bool:
        """解除 Candidate identity 對應的 Owner 封鎖。"""

        changed = connection.execute(
            """
            DELETE FROM memory_owner_overrides
            WHERE user_id = ? AND scope_type = ? AND scope_id = ?
              AND memory_type = ? AND memory_key = ?
            """,
            (
                candidate.user_id,
                candidate.scope_type.value,
                candidate.scope_id,
                candidate.memory_type,
                candidate.memory_key,
            ),
        ).rowcount
        return changed > 0

    def owner_upsert(
        self,
        *,
        user_id: str,
        scope_type: MemoryScopeType,
        scope_id: str,
        memory_type: str,
        memory_key: str,
        value,
        importance: int,
        actor_id: str,
        now: int,
        connection: sqlite3.Connection,
        existing_id: str | None = None,
    ) -> Memory:
        """建立 Owner 來源的新 Active 版本，不偽造 Event Evidence。"""

        from .models import AssertionStrength, TemporalScope

        candidate = MemoryCandidate(
            candidate_id=f"owner-{uuid.uuid4().hex}",
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
            observed_at=now,
        )

        active = self.get_active_for_key(candidate, connection)
        previous: Memory | None = None
        if existing_id is not None:
            previous = self._require_target_matches(
                existing_id,
                candidate,
                connection,
            )
            if active is None or active.memory_id != existing_id:
                raise KeyError(f"找不到 Active Memory：{existing_id}")
        elif active is not None:
            raise ValueError(
                "Owner 新增記憶與既有 Active Memory identity 重複；"
                "請保留 memory_id 以表示修改"
            )

        if previous is not None:
            connection.execute(
                "UPDATE memories SET status = 'superseded', updated_at = ? "
                "WHERE memory_id = ? AND status = 'active'",
                (now, previous.memory_id),
            )

        memory_id = f"mem-{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO memories (
                memory_id, user_id, scope_type, scope_id, memory_type,
                memory_key, value_json, confidence, importance, status,
                created_at, updated_at, last_confirmed_at, expires_at,
                superseded_by_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL, NULL)
            """,
            (
                memory_id,
                candidate.user_id,
                candidate.scope_type.value,
                candidate.scope_id,
                candidate.memory_type,
                candidate.memory_key,
                dump_json_value(candidate.value),
                candidate.confidence,
                candidate.importance,
                now,
                now,
                now,
            ),
        )
        if previous is not None:
            connection.execute(
                "UPDATE memories SET superseded_by_id = ? WHERE memory_id = ?",
                (memory_id, previous.memory_id),
            )

        self.clear_owner_block(candidate, connection)
        self._audit_owner(
            connection,
            memory_id=memory_id,
            actor_id=actor_id,
            action="owner_update" if previous is not None else "owner_add",
            now=now,
        )
        memory = self._get_with_connection(connection, memory_id)
        if memory is None:
            raise RuntimeError("Owner Memory 寫入後無法讀回")
        return memory

    def owner_block_count(self) -> int:
        """取得目前 Owner 封鎖 identity 數量。"""

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT count(*) FROM memory_owner_overrides"
            ).fetchone()
        return int(row[0])

    def evidence_for(
        self,
        memory_id: str,
    ) -> tuple[MemoryEvidence, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_evidence
                WHERE memory_id = ?
                ORDER BY created_at, event_id, candidate_id
                """,
                (memory_id,),
            ).fetchall()
        return tuple(
            MemoryEvidence(
                memory_id=str(row["memory_id"]),
                event_id=str(row["event_id"]),
                candidate_id=str(row["candidate_id"]),
                relation=str(row["relation"]),
                created_at=int(row["created_at"]),
            )
            for row in rows
        )

    def find_active(
        self,
        query: MemoryQuery,
    ) -> tuple[Memory, ...]:
        filters = [
            "user_id = ?",
            "scope_type = ?",
            "scope_id = ?",
            "status = 'active'",
        ]
        parameters: list[object] = [
            query.user_id,
            query.scope_type.value,
            query.scope_id,
        ]

        if query.memory_type is not None:
            filters.append("memory_type = ?")
            parameters.append(query.memory_type)
        if query.memory_key is not None:
            filters.append("memory_key = ?")
            parameters.append(query.memory_key)

        parameters.append(query.limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memories WHERE "
                + " AND ".join(filters)
                + " ORDER BY importance DESC, updated_at DESC, memory_id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(self._memory_from_row(row) for row in rows)

    def count_active_for_key(
        self,
        candidate: MemoryCandidate,
    ) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT count(*) AS count FROM memories
                WHERE user_id = ? AND scope_type = ? AND scope_id = ?
                  AND memory_type = ? AND memory_key = ? AND status = 'active'
                """,
                (
                    candidate.user_id,
                    candidate.scope_type.value,
                    candidate.scope_id,
                    candidate.memory_type,
                    candidate.memory_key,
                ),
            ).fetchone()
        return int(row["count"])

    # ── Internal Helpers ──────────────────────

    def validate_evidence(
        self,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> None:
        """確認 Candidate 的 Source Event 位於允許的 Scope。"""

        self._validate_evidence(
            candidate,
            connection,
        )

    @staticmethod
    def _validate_evidence(
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> None:
        row = connection.execute(
            "SELECT user_id, channel_id, conversation_id, role, created_at "
            "FROM events WHERE event_id = ?",
            (candidate.source_event_id,),
        ).fetchone()
        if row is None:
            raise EvidenceNotFoundError(
                f"找不到 Evidence Event：{candidate.source_event_id}"
            )
        if str(row["role"]) != EventRole.USER.value:
            raise EvidenceScopeError("Memory Evidence 必須來自 user event")
        if str(row["user_id"]) != candidate.user_id:
            raise EvidenceScopeError("Evidence user_id 與 Candidate 不一致")
        if (
            candidate.scope_type is MemoryScopeType.CHANNEL
            and str(row["channel_id"]) != candidate.scope_id
        ):
            raise EvidenceScopeError("Evidence channel scope 與 Candidate 不一致")
        if (
            candidate.scope_type is MemoryScopeType.CONVERSATION
            and str(row["conversation_id"]) != candidate.scope_id
        ):
            raise EvidenceScopeError(
                "Evidence conversation scope 與 Candidate 不一致"
            )
        if int(row["created_at"]) != candidate.observed_at:
            raise EvidenceScopeError(
                "Candidate observed_at 必須對應 Evidence created_at"
            )

    @classmethod
    def _require_target_matches(
        cls,
        memory_id: str,
        candidate: MemoryCandidate,
        connection: sqlite3.Connection,
    ) -> Memory:
        memory = cls._get_with_connection(connection, memory_id)
        if memory is None or memory.status is not MemoryStatus.ACTIVE:
            raise KeyError(f"找不到 Active Memory：{memory_id}")

        expected = (
            candidate.user_id,
            candidate.scope_type,
            candidate.scope_id,
            candidate.memory_type,
            candidate.memory_key,
        )
        actual = (
            memory.user_id,
            memory.scope_type,
            memory.scope_id,
            memory.memory_type,
            memory.memory_key,
        )
        if actual != expected:
            raise EvidenceScopeError(
                "Memory target 與 Candidate identity/scope 不一致"
            )
        return memory

    @staticmethod
    def _audit_owner(
        connection: sqlite3.Connection,
        *,
        memory_id: str,
        actor_id: str,
        action: str,
        now: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO memory_owner_audit (
                memory_id, actor_id, action, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (memory_id, actor_id, action, now),
        )

    @staticmethod
    def _insert_evidence(
        connection: sqlite3.Connection,
        *,
        memory_id: str,
        candidate: MemoryCandidate,
        relation: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO memory_evidence (
                memory_id, event_id, candidate_id, relation, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                candidate.source_event_id,
                candidate.candidate_id,
                relation,
                candidate.observed_at,
            ),
        )

    @classmethod
    def _get_with_connection(
        cls,
        connection: sqlite3.Connection,
        memory_id: str,
    ) -> Memory | None:
        row = connection.execute(
            "SELECT * FROM memories WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        return None if row is None else cls._memory_from_row(row)

    @classmethod
    def _get_candidate_with_connection(
        cls,
        connection: sqlite3.Connection,
        candidate_id: str,
    ) -> MemoryCandidateRecord | None:
        row = connection.execute(
            "SELECT * FROM memory_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return None if row is None else cls._candidate_from_row(row)

    @staticmethod
    def _candidate_from_row(
        row: Sequence[object],
    ) -> MemoryCandidateRecord:
        from .models import AssertionStrength, TemporalScope

        candidate = MemoryCandidate(
            candidate_id=str(row["candidate_id"]),
            source_event_id=str(row["source_event_id"]),
            user_id=str(row["user_id"]),
            scope_type=MemoryScopeType(str(row["scope_type"])),
            scope_id=str(row["scope_id"]),
            memory_type=str(row["memory_type"]),
            memory_key=str(row["memory_key"]),
            value=load_json_value(str(row["value_json"])),
            confidence=float(row["confidence"]),
            importance=int(row["importance"]),
            assertion_strength=AssertionStrength(str(row["assertion_strength"])),
            temporal_scope=TemporalScope(str(row["temporal_scope"])),
            observed_at=int(row["observed_at"]),
        )
        return MemoryCandidateRecord(
            candidate=candidate,
            status=CandidateStatus(str(row["status"])),
            decided_at=None if row["decided_at"] is None else int(row["decided_at"]),
            result_action=None if row["result_action"] is None else str(row["result_action"]),
            result_reason=None if row["result_reason"] is None else str(row["result_reason"]),
            result_memory_id=(
                None
                if row["result_memory_id"] is None
                else str(row["result_memory_id"])
            ),
            result_memory=(
                None
                if row["result_memory_json"] is None
                else load_memory(str(row["result_memory_json"]))
            ),
        )

    @staticmethod
    def _memory_from_row(
        row: Sequence[object],
    ) -> Memory:
        return Memory(
            memory_id=str(row["memory_id"]),
            user_id=str(row["user_id"]),
            scope_type=MemoryScopeType(str(row["scope_type"])),
            scope_id=str(row["scope_id"]),
            memory_type=str(row["memory_type"]),
            memory_key=str(row["memory_key"]),
            value=load_json_value(str(row["value_json"])),
            confidence=float(row["confidence"]),
            importance=int(row["importance"]),
            status=MemoryStatus(str(row["status"])),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            last_confirmed_at=(
                None
                if row["last_confirmed_at"] is None
                else int(row["last_confirmed_at"])
            ),
            expires_at=(
                None
                if row["expires_at"] is None
                else int(row["expires_at"])
            ),
            superseded_by_id=(
                None
                if row["superseded_by_id"] is None
                else str(row["superseded_by_id"])
            ),
        )
