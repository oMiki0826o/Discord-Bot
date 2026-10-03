"""
bot/mod/ai/context/models.py

Modification():

- 定義統一 Context Item 與 budget 結果。
- 保留 source、relevance、confidence 與 token cost 供後續解釋。
- 加入 initial identity/reply、Public Profile 與 Channel Context 來源。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContextSource(StrEnum):
    INITIAL = "initial"
    RECENT_HISTORY = "recent_history"
    HISTORY_SEARCH = "history_search"
    MEMORY = "memory"
    MANUAL_MEMORY = "manual_memory"
    TOPIC = "topic"
    KNOWLEDGE = "knowledge"
    TOOL = "tool"
    PUBLIC_PROFILE = "public_profile"
    CHANNEL_CONTEXT = "channel_context"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True)
class ContextItem:
    item_id: str
    dedupe_key: str
    source: ContextSource
    content: str
    relevance: float
    importance: int
    confidence: float
    timestamp: int
    token_cost: int

    def __post_init__(self) -> None:
        for name, value in (
            ("item_id", self.item_id),
            ("dedupe_key", self.dedupe_key),
            ("content", self.content),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 不得空白")
        if not isinstance(self.source, ContextSource):
            raise ValueError("source 必須是 ContextSource")
        for name, value in (
            ("relevance", self.relevance),
            ("confidence", self.confidence),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0.0 <= float(value) <= 1.0
            ):
                raise ValueError(f"{name} 必須介於 0.0 到 1.0")
        if not isinstance(self.importance, int) or isinstance(self.importance, bool) or not 1 <= self.importance <= 5:
            raise ValueError("importance 必須介於 1 到 5")
        if not isinstance(self.timestamp, int) or isinstance(self.timestamp, bool) or self.timestamp < 0:
            raise ValueError("timestamp 必須是非負整數")
        if not isinstance(self.token_cost, int) or isinstance(self.token_cost, bool) or self.token_cost < 1:
            raise ValueError("token_cost 必須是正整數")


@dataclass(frozen=True, slots=True)
class ContextPack:
    items: tuple[ContextItem, ...]
    used_tokens: int
    max_tokens: int
    omitted_count: int

    def __post_init__(self) -> None:
        if self.used_tokens != sum(item.token_cost for item in self.items):
            raise ValueError("used_tokens 與 items 不一致")
        if self.used_tokens > self.max_tokens:
            raise ValueError("ContextPack 超過 max_tokens")
        if self.omitted_count < 0:
            raise ValueError("omitted_count 不得為負數")


@dataclass(frozen=True, slots=True)
class ContextRequest:
    user_id: str
    channel_id: str
    conversation_id: str
    current_event_id: str
    max_tokens: int
    recent_limit: int = 20
    history_query: str | None = None
    include_memory: bool = True
    include_topics: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("user_id", self.user_id),
            ("channel_id", self.channel_id),
            ("conversation_id", self.conversation_id),
            ("current_event_id", self.current_event_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 不得空白")
        if not isinstance(self.max_tokens, int) or isinstance(self.max_tokens, bool) or self.max_tokens < 1:
            raise ValueError("max_tokens 必須是正整數")
        if not isinstance(self.recent_limit, int) or isinstance(self.recent_limit, bool) or not 1 <= self.recent_limit <= 200:
            raise ValueError("recent_limit 必須介於 1 到 200")
        if self.history_query is not None and not self.history_query.strip():
            raise ValueError("history_query 不得空白")
