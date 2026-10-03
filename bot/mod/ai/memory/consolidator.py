"""
bot/mod/ai/memory/consolidator.py

Modification():

- 在單一 Transaction 內套用 Memory Consolidation Decision。
- 保存 Candidate Audit、Memory Mutation 與 Event Evidence。
- 支援已完成 Candidate 的 Idempotent Retry。
- 尊重 Owner 撤銷封鎖，保留 rejected Candidate Audit 而不重建記憶。

本檔負責 Memory Consolidation Application Flow。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..database import AiDatabase
from .models import (
    CandidateStatus,
    Memory,
    MemoryCandidate,
    MemoryCandidateRecord,
)
from .policy import Action, ConflictResolver, ConsolidationDecision
from .repository import MemoryRepository


# ── Results ──────────────────────

@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    candidate_id: str
    action: Action
    reason: str
    memory: Memory | None


# ── Consolidator ──────────────────────

class MemoryConsolidator:
    """將單一 Candidate 安全整併進目前 Memory State。"""

    _TERMINAL_STATUSES = frozenset({
        CandidateStatus.ACCEPTED,
        CandidateStatus.IGNORED,
        CandidateStatus.CONFLICT,
        CandidateStatus.REJECTED,
    })

    def __init__(
        self,
        *,
        database: AiDatabase,
        repository: MemoryRepository,
        resolver: ConflictResolver,
    ) -> None:
        self.database = database
        self.repository = repository
        self.resolver = resolver

    def consolidate(
        self,
        candidate: MemoryCandidate,
    ) -> ConsolidationResult:
        """整併 Candidate；失敗時回滾整個決策。"""

        with self.database.transaction() as connection:
            self.repository.validate_evidence(
                candidate,
                connection,
            )
            status = self.repository.save_candidate(
                candidate,
                connection,
            )
            record = self.repository.get_candidate(
                candidate.candidate_id,
                connection,
            )

            if record is None:
                raise RuntimeError("Candidate 保存後無法讀回")

            if status in self._TERMINAL_STATUSES:
                return self._result_from_record(record)

            if self.repository.is_owner_blocked(candidate, connection):
                decision = ConsolidationDecision(
                    action=Action.IGNORE,
                    reason="owner_retracted",
                )
                self.repository.mark_candidate(
                    candidate.candidate_id,
                    CandidateStatus.REJECTED,
                    connection,
                    action=decision.action.value,
                    reason=decision.reason,
                )
                return ConsolidationResult(
                    candidate_id=candidate.candidate_id,
                    action=decision.action,
                    reason=decision.reason,
                    memory=None,
                )

            existing = self.repository.get_active_for_key(
                candidate,
                connection,
            )
            decision = self.resolver.decide(
                candidate,
                existing,
            )
            memory = self._apply(
                candidate=candidate,
                existing=existing,
                decision=decision,
                connection=connection,
            )
            candidate_status = self._candidate_status(
                decision.action
            )
            self.repository.mark_candidate(
                candidate.candidate_id,
                candidate_status,
                connection,
                action=decision.action.value,
                reason=decision.reason,
                memory=memory,
            )

            return ConsolidationResult(
                candidate_id=candidate.candidate_id,
                action=decision.action,
                reason=decision.reason,
                memory=memory,
            )

    def _apply(
        self,
        *,
        candidate: MemoryCandidate,
        existing: Memory | None,
        decision: ConsolidationDecision,
        connection,
    ) -> Memory | None:
        if decision.action is Action.ADD:
            return self.repository.add(
                candidate,
                connection,
            )

        if decision.action is Action.CONFIRM:
            if existing is None:
                raise RuntimeError(
                    "CONFIRM Decision 缺少 Active Memory"
                )
            return self.repository.confirm(
                existing.memory_id,
                candidate,
                connection,
            )

        if decision.action is Action.SUPERSEDE:
            if existing is None:
                raise RuntimeError(
                    "SUPERSEDE Decision 缺少 Active Memory"
                )
            return self.repository.supersede(
                existing.memory_id,
                candidate,
                connection,
            )

        if decision.action in {Action.IGNORE, Action.CONFLICT}:
            return None

        raise RuntimeError(
            f"P0 尚未支援 Consolidation Action：{decision.action.value}"
        )

    def _result_from_record(
        self,
        record: MemoryCandidateRecord,
    ) -> ConsolidationResult:
        if record.result_action is None or record.result_reason is None:
            raise RuntimeError(
                "Terminal Candidate 缺少 Result Audit"
            )

        memory = record.result_memory
        if record.result_memory_id is not None and memory is None:
            raise RuntimeError("Candidate Result 缺少 Memory Snapshot")

        return ConsolidationResult(
            candidate_id=record.candidate.candidate_id,
            action=Action(record.result_action),
            reason=record.result_reason,
            memory=memory,
        )

    @staticmethod
    def _candidate_status(
        action: Action,
    ) -> CandidateStatus:
        if action in {
            Action.ADD,
            Action.CONFIRM,
            Action.UPDATE,
            Action.SUPERSEDE,
            Action.EXPIRE,
        }:
            return CandidateStatus.ACCEPTED
        if action is Action.IGNORE:
            return CandidateStatus.IGNORED
        if action is Action.CONFLICT:
            return CandidateStatus.CONFLICT
        raise RuntimeError(
            f"未知 Consolidation Action：{action.value}"
        )
