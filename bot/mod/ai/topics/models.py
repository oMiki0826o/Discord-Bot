"""
bot/mod/ai/topics/models.py

Modification():

- 定義 Topic State、Evidence 與強制 Scope 的查詢模型。
- 驗證 optimistic version 與可公開序列化的 state。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..json_values import JsonValue, normalize_json_value


class TopicScopeType(StrEnum):
    GLOBAL = "global"
    CHANNEL = "channel"
    CONVERSATION = "conversation"


class TopicStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class PutTopicState:
    topic_id: str
    user_id: str
    scope_type: TopicScopeType
    scope_id: str
    name: str
    status: TopicStatus
    current_goal: str | None
    state: dict[str, JsonValue]
    evidence_event_id: str
    observed_at: int
    expected_version: int | None

    def __post_init__(self) -> None:
        _validate_identity(self.topic_id, self.user_id, self.scope_type, self.scope_id)
        _require_text("name", self.name, maximum=120)
        _require_text("evidence_event_id", self.evidence_event_id)
        if not isinstance(self.status, TopicStatus):
            raise ValueError("status 必須是 TopicStatus")
        if self.current_goal is not None:
            _require_text("current_goal", self.current_goal, maximum=2_000)
        normalized = normalize_json_value(self.state, field_name="state", max_bytes=20_000)
        if not isinstance(normalized, dict):
            raise ValueError("state 必須是 JSON Object")
        object.__setattr__(self, "state", normalized)
        _validate_timestamp("observed_at", self.observed_at)
        if self.expected_version is not None and (
            not isinstance(self.expected_version, int)
            or isinstance(self.expected_version, bool)
            or self.expected_version < 1
        ):
            raise ValueError("expected_version 必須是正整數")


@dataclass(frozen=True, slots=True)
class TopicState:
    topic_id: str
    user_id: str
    scope_type: TopicScopeType
    scope_id: str
    name: str
    status: TopicStatus
    current_goal: str | None
    state: dict[str, JsonValue]
    version: int
    created_at: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class TopicEvidence:
    topic_id: str
    event_id: str
    version: int
    created_at: int


@dataclass(frozen=True, slots=True)
class TopicQuery:
    topic_id: str
    user_id: str
    scope_type: TopicScopeType
    scope_id: str

    def __post_init__(self) -> None:
        _validate_identity(self.topic_id, self.user_id, self.scope_type, self.scope_id)


@dataclass(frozen=True, slots=True)
class TopicListQuery:
    user_id: str
    scope_type: TopicScopeType
    scope_id: str
    statuses: tuple[TopicStatus, ...] = field(default_factory=tuple)
    limit: int = 50

    def __post_init__(self) -> None:
        _require_text("user_id", self.user_id)
        _require_text("scope_id", self.scope_id)
        if not isinstance(self.scope_type, TopicScopeType):
            raise ValueError("scope_type 必須是 TopicScopeType")
        if any(not isinstance(status, TopicStatus) for status in self.statuses):
            raise ValueError("statuses 必須由 TopicStatus 組成")
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or not 1 <= self.limit <= 200:
            raise ValueError("limit 必須介於 1 到 200")


def _validate_identity(
    topic_id: str,
    user_id: str,
    scope_type: TopicScopeType,
    scope_id: str,
) -> None:
    _require_text("topic_id", topic_id)
    _require_text("user_id", user_id)
    _require_text("scope_id", scope_id)
    if not isinstance(scope_type, TopicScopeType):
        raise ValueError("scope_type 必須是 TopicScopeType")


def _require_text(name: str, value: object, *, maximum: int = 200) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不得空白")
    if len(value) > maximum:
        raise ValueError(f"{name} 不得超過 {maximum} 字元")


def _validate_timestamp(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} 必須是非負整數")
