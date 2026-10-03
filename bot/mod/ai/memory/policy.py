"""
bot/mod/ai/memory/policy.py

Modification():

- 判斷 Memory Candidate 應新增、確認、忽略、衝突或取代。
- 將暫時資訊與正式狀態更新分開處理。

本檔提供不含 I/O 的 Deterministic Conflict Policy。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import (
    AssertionStrength,
    Memory,
    MemoryCandidate,
    MemoryStatus,
    TemporalScope,
    dump_json_value,
)


# ── Policy Models ──────────────────────

class Action(StrEnum):
    ADD = "add"
    CONFIRM = "confirm"
    UPDATE = "update"
    SUPERSEDE = "supersede"
    IGNORE = "ignore"
    CONFLICT = "conflict"
    EXPIRE = "expire"


@dataclass(frozen=True, slots=True)
class ConsolidationPolicy:
    add_confidence: float = 0.75
    supersede_confidence: float = 0.85

    def __post_init__(self) -> None:
        for name, value in (
            ("add_confidence", self.add_confidence),
            ("supersede_confidence", self.supersede_confidence),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0.0 <= float(value) <= 1.0
            ):
                raise ValueError(f"{name} threshold 必須介於 0.0 到 1.0")

        if self.supersede_confidence < self.add_confidence:
            raise ValueError(
                "supersede threshold 不得低於 add threshold"
            )


@dataclass(frozen=True, slots=True)
class ConsolidationDecision:
    action: Action
    reason: str


# ── Conflict Resolver ──────────────────────

class ConflictResolver:
    """依明確規則判斷 Candidate，不修改任何狀態。"""

    def __init__(
        self,
        policy: ConsolidationPolicy | None = None,
    ) -> None:
        self.policy = policy or ConsolidationPolicy()

    def decide(
        self,
        candidate: MemoryCandidate,
        existing: Memory | None,
    ) -> ConsolidationDecision:
        """回傳 Candidate 對目前狀態的決策。"""

        if existing is None or existing.status is not MemoryStatus.ACTIVE:
            if candidate.temporal_scope is TemporalScope.TEMPORARY:
                return ConsolidationDecision(
                    action=Action.IGNORE,
                    reason="temporary information is not durable state",
                )

            if candidate.confidence < self.policy.add_confidence:
                return ConsolidationDecision(
                    action=Action.IGNORE,
                    reason="confidence is below add threshold",
                )

            return ConsolidationDecision(
                action=Action.ADD,
                reason="no active memory exists for this key",
            )

        if dump_json_value(candidate.value) == dump_json_value(existing.value):
            return ConsolidationDecision(
                action=Action.CONFIRM,
                reason="candidate confirms the active value",
            )

        if candidate.observed_at < existing.updated_at:
            return ConsolidationDecision(
                action=Action.CONFLICT,
                reason="older evidence cannot replace newer active state",
            )

        if candidate.temporal_scope is TemporalScope.TEMPORARY:
            return ConsolidationDecision(
                action=Action.IGNORE,
                reason="temporary contradiction does not replace durable state",
            )

        if (
            candidate.assertion_strength is AssertionStrength.EXPLICIT
            and candidate.temporal_scope
            in {TemporalScope.ONGOING, TemporalScope.PERMANENT}
            and candidate.confidence >= self.policy.supersede_confidence
        ):
            return ConsolidationDecision(
                action=Action.SUPERSEDE,
                reason="explicit durable update exceeds supersede threshold",
            )

        return ConsolidationDecision(
            action=Action.CONFLICT,
            reason="contradicting evidence is insufficient to replace active memory",
        )
