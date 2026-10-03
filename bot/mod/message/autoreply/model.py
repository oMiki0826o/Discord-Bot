"""
bot/mod/message/autoreply/model.py

Modification():

- Validated domain models for human-editable auto-reply JSON。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from string import Formatter
from typing import Any


ALLOWED_PLACEHOLDERS = frozenset(
    {"user", "username", "channel", "guild", "match"}
)


class MatchMode(StrEnum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"


@dataclass(frozen=True, slots=True)
class AutoReplyRule:
    id: str
    enabled: bool
    priority: int
    mode: MatchMode
    pattern: str
    case_sensitive: bool
    response: str
    allowed_channel_ids: tuple[int, ...] = ()
    blocked_channel_ids: tuple[int, ...] = ()
    cooldown_seconds: float = 5.0

    def validate(self) -> None:
        if not self.id.strip() or len(self.id) > 64:
            raise ValueError("規則 id 必須為 1 到 64 字")
        if not self.pattern or len(self.pattern) > 500:
            raise ValueError("pattern 必須為 1 到 500 字")
        if not self.response or len(self.response) > 2000:
            raise ValueError("response 必須為 1 到 2000 字")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds 不可小於 0")
        fields = {
            field_name
            for _, field_name, _, _ in Formatter().parse(self.response)
            if field_name
        }
        unknown = fields - ALLOWED_PLACEHOLDERS
        if unknown:
            raise ValueError(f"未知 placeholder: {', '.join(sorted(unknown))}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "priority": self.priority,
            "match": {
                "mode": self.mode.value,
                "pattern": self.pattern,
                "case_sensitive": self.case_sensitive,
            },
            "response": self.response,
            "channels": {
                "allow": list(self.allowed_channel_ids),
                "block": list(self.blocked_channel_ids),
            },
            "cooldown_seconds": self.cooldown_seconds,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AutoReplyRule:
        match = value.get("match", {})
        channels = value.get("channels", {})
        try:
            rule = cls(
                id=str(value["id"]),
                enabled=bool(value.get("enabled", True)),
                priority=int(value.get("priority", 0)),
                mode=MatchMode(str(match["mode"])),
                pattern=str(match["pattern"]),
                case_sensitive=bool(match.get("case_sensitive", False)),
                response=str(value["response"]),
                allowed_channel_ids=tuple(int(item) for item in channels.get("allow", [])),
                blocked_channel_ids=tuple(int(item) for item in channels.get("block", [])),
                cooldown_seconds=float(value.get("cooldown_seconds", 5.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"自動回覆規則格式錯誤: {exc}") from exc
        rule.validate()
        return rule


@dataclass(frozen=True, slots=True)
class AutoReplyDocument:
    schema_version: int
    guild_id: int
    rules: tuple[AutoReplyRule, ...]

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError("不支援的自動回覆 schema_version")
        ids: set[str] = set()
        for rule in self.rules:
            rule.validate()
            if rule.id in ids:
                raise ValueError(f"重複的規則 id: {rule.id}")
            ids.add(rule.id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        rules = sorted(self.rules, key=lambda item: (-item.priority, item.id))
        return {
            "schema_version": self.schema_version,
            "guild_id": self.guild_id,
            "rules": [rule.to_dict() for rule in rules],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AutoReplyDocument:
        if not isinstance(value, dict) or not isinstance(value.get("rules", []), list):
            raise ValueError("自動回覆 JSON 根節點格式錯誤")
        document = cls(
            schema_version=int(value.get("schema_version", 1)),
            guild_id=int(value["guild_id"]),
            rules=tuple(AutoReplyRule.from_dict(item) for item in value.get("rules", [])),
        )
        document.validate()
        return document
