"""
bot/mod/ai/history/models.py

Modification():

- 定義不可推論的原始 AI Event。
- 定義具備使用者與頻道邊界的 Event 查詢 Scope。

本檔只負責 History Domain Models 與輸入驗證。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from ..json_values import JsonValue, normalize_json_value

MAX_EVENT_CONTENT_CHARS = 20_000


# ── Event Models ──────────────────────

class EventRole(StrEnum):
    """原始事件的發話角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class EventScope:
    """讀取 History 時必須提供的隔離範圍。"""

    user_id: str
    channel_id: str
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        _require_text("user_id", self.user_id)
        _require_text("channel_id", self.channel_id)
        if self.conversation_id is not None:
            _require_text("conversation_id", self.conversation_id)


@dataclass(frozen=True, slots=True)
class NewEvent:
    """尚未寫入 Event Store 的原始事件。"""

    event_id: str
    user_id: str
    channel_id: str
    message_id: str | None
    conversation_id: str
    role: EventRole
    content: str
    created_at: int
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_event_fields(
            event_id=self.event_id,
            user_id=self.user_id,
            channel_id=self.channel_id,
            message_id=self.message_id,
            conversation_id=self.conversation_id,
            role=self.role,
            content=self.content,
            created_at=self.created_at,
            metadata=self.metadata,
        )
        normalized = normalize_json_value(
            self.metadata,
            field_name="metadata",
        )
        if not isinstance(normalized, dict):
            raise ValueError("metadata 必須是 JSON Object")
        object.__setattr__(self, "metadata", normalized)


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """已保存、可作為 Evidence 的原始事件。"""

    event_id: str
    user_id: str
    channel_id: str
    message_id: str | None
    conversation_id: str
    role: EventRole
    content: str
    created_at: int
    metadata: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        normalized = normalize_json_value(
            self.metadata,
            field_name="metadata",
        )
        if not isinstance(normalized, dict):
            raise ValueError("metadata 必須是 JSON Object")
        object.__setattr__(self, "metadata", normalized)


# ── Validation ──────────────────────

def _require_text(
    name: str,
    value: object,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不得空白")
    return value


def _validate_event_fields(
    *,
    event_id: str,
    user_id: str,
    channel_id: str,
    message_id: str | None,
    conversation_id: str,
    role: EventRole,
    content: str,
    created_at: int,
    metadata: Mapping[str, JsonValue],
) -> None:
    _require_text("event_id", event_id)
    _require_text("user_id", user_id)
    _require_text("channel_id", channel_id)
    _require_text("conversation_id", conversation_id)
    _require_text("content", content)

    if message_id is not None:
        _require_text("message_id", message_id)

    if not isinstance(role, EventRole):
        raise ValueError("role 必須是 EventRole")

    if len(content) > MAX_EVENT_CONTENT_CHARS:
        raise ValueError(
            f"content 不得超過 {MAX_EVENT_CONTENT_CHARS} 字元"
        )

    if not isinstance(created_at, int) or isinstance(created_at, bool) or created_at < 0:
        raise ValueError("created_at 必須是非負整數")

    if not isinstance(metadata, Mapping):
        raise ValueError("metadata 必須是 Mapping")

    normalize_json_value(
        metadata,
        field_name="metadata",
    )
