"""
bot/mod/ai/memory/models.py

Modification():

- 定義 Memory Candidate、Memory、Evidence 與 Query Models。
- 分離 Candidate Audit 狀態與 Materialized Memory 狀態。
- 驗證 Scope、可信度、重要性與 JSON Value。

本檔只負責 Memory Domain Models。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ..json_values import (
    JsonValue,
    dump_json_value as dump_strict_json_value,
    normalize_json_value,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
MAX_MEMORY_VALUE_BYTES = 4_000


# ── Enums ──────────────────────

class MemoryScopeType(StrEnum):
    GLOBAL = "global"
    CHANNEL = "channel"
    CONVERSATION = "conversation"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    UNCERTAIN = "uncertain"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"
    RETRACTED = "retracted"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    IGNORED = "ignored"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class AssertionStrength(StrEnum):
    TENTATIVE = "tentative"
    OBSERVED = "observed"
    EXPLICIT = "explicit"


class TemporalScope(StrEnum):
    TEMPORARY = "temporary"
    ONGOING = "ongoing"
    PERMANENT = "permanent"


# ── Models ──────────────────────

@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    candidate_id: str
    source_event_id: str
    user_id: str
    scope_type: MemoryScopeType
    scope_id: str
    memory_type: str
    memory_key: str
    value: JsonValue
    confidence: float
    importance: int
    assertion_strength: AssertionStrength
    temporal_scope: TemporalScope
    observed_at: int

    def __post_init__(self) -> None:
        _require_text("candidate_id", self.candidate_id)
        _require_text("source_event_id", self.source_event_id)
        _require_text("user_id", self.user_id)
        _require_text("scope_id", self.scope_id)
        _validate_name("memory_type", self.memory_type)
        _validate_name("memory_key", self.memory_key)
        normalized_value = _validate_json_value(self.value)
        object.__setattr__(self, "value", normalized_value)
        _validate_score("confidence", self.confidence)

        if (
            not isinstance(self.importance, int)
            or isinstance(self.importance, bool)
            or not 1 <= self.importance <= 5
        ):
            raise ValueError("importance 必須介於 1 到 5")

        if not isinstance(self.scope_type, MemoryScopeType):
            raise ValueError("scope_type 必須是 MemoryScopeType")
        if not isinstance(self.assertion_strength, AssertionStrength):
            raise ValueError("assertion_strength 必須是 AssertionStrength")
        if not isinstance(self.temporal_scope, TemporalScope):
            raise ValueError("temporal_scope 必須是 TemporalScope")
        if (
            not isinstance(self.observed_at, int)
            or isinstance(self.observed_at, bool)
            or self.observed_at < 0
        ):
            raise ValueError("observed_at 必須是非負整數")

    @property
    def evidence_event_ids(self) -> tuple[str, ...]:
        return (self.source_event_id,)


@dataclass(frozen=True, slots=True)
class Memory:
    memory_id: str
    user_id: str
    scope_type: MemoryScopeType
    scope_id: str
    memory_type: str
    memory_key: str
    value: JsonValue
    confidence: float
    importance: int
    status: MemoryStatus
    created_at: int
    updated_at: int
    last_confirmed_at: int | None
    expires_at: int | None
    superseded_by_id: str | None

    def __post_init__(self) -> None:
        normalized_value = _validate_json_value(self.value)
        object.__setattr__(self, "value", normalized_value)


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    memory_id: str
    event_id: str
    candidate_id: str
    relation: str
    created_at: int


@dataclass(frozen=True, slots=True)
class MemoryCandidateRecord:
    candidate: MemoryCandidate
    status: CandidateStatus
    decided_at: int | None
    result_action: str | None
    result_reason: str | None
    result_memory_id: str | None
    result_memory: Memory | None


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    user_id: str
    scope_type: MemoryScopeType
    scope_id: str
    memory_type: str | None = None
    memory_key: str | None = None
    limit: int = 50

    def __post_init__(self) -> None:
        _require_text("user_id", self.user_id)
        _require_text("scope_id", self.scope_id)
        if not isinstance(self.scope_type, MemoryScopeType):
            raise ValueError("scope_type 必須是 MemoryScopeType")
        if self.memory_type is not None:
            _validate_name("memory_type", self.memory_type)
        if self.memory_key is not None:
            _validate_name("memory_key", self.memory_key)
        if (
            not isinstance(self.limit, int)
            or isinstance(self.limit, bool)
            or not 1 <= self.limit <= 200
        ):
            raise ValueError("limit 必須介於 1 到 200")


# ── Serialization ──────────────────────

def dump_json_value(value: JsonValue) -> str:
    return dump_strict_json_value(
        value,
        field_name="value",
        max_bytes=MAX_MEMORY_VALUE_BYTES,
    )


def load_json_value(value: str) -> JsonValue:
    import json

    return _validate_json_value(json.loads(value))


# ── Validation ──────────────────────

def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不得空白")
    return value


def _validate_name(name: str, value: object) -> str:
    if not isinstance(value, str) or _NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} 格式錯誤")
    return value


def _validate_score(name: str, value: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{name} 必須介於 0.0 到 1.0")
    return float(value)


def _validate_json_value(value: object) -> JsonValue:
    normalized = normalize_json_value(
        value,
        field_name="value",
        max_bytes=MAX_MEMORY_VALUE_BYTES,
    )
    if value is None or value == "" or value == [] or value == {}:
        raise ValueError("value 不得為空")
    return normalized


def dump_memory(memory: Memory) -> str:
    return dump_strict_json_value(
        {
            "memory_id": memory.memory_id,
            "user_id": memory.user_id,
            "scope_type": memory.scope_type.value,
            "scope_id": memory.scope_id,
            "memory_type": memory.memory_type,
            "memory_key": memory.memory_key,
            "value": memory.value,
            "confidence": memory.confidence,
            "importance": memory.importance,
            "status": memory.status.value,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
            "last_confirmed_at": memory.last_confirmed_at,
            "expires_at": memory.expires_at,
            "superseded_by_id": memory.superseded_by_id,
        },
        field_name="memory snapshot",
    )


def load_memory(value: str) -> Memory:
    import json

    raw = normalize_json_value(
        json.loads(value),
        field_name="memory snapshot",
    )
    if not isinstance(raw, dict):
        raise ValueError("memory snapshot 必須是 JSON Object")
    return Memory(
        memory_id=str(raw["memory_id"]),
        user_id=str(raw["user_id"]),
        scope_type=MemoryScopeType(str(raw["scope_type"])),
        scope_id=str(raw["scope_id"]),
        memory_type=str(raw["memory_type"]),
        memory_key=str(raw["memory_key"]),
        value=raw["value"],
        confidence=float(raw["confidence"]),
        importance=int(raw["importance"]),
        status=MemoryStatus(str(raw["status"])),
        created_at=int(raw["created_at"]),
        updated_at=int(raw["updated_at"]),
        last_confirmed_at=(
            None
            if raw["last_confirmed_at"] is None
            else int(raw["last_confirmed_at"])
        ),
        expires_at=(
            None
            if raw["expires_at"] is None
            else int(raw["expires_at"])
        ),
        superseded_by_id=(
            None
            if raw["superseded_by_id"] is None
            else str(raw["superseded_by_id"])
        ),
    )
