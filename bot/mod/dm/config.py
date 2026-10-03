"""
bot/mod/dm/config.py

Modification():

- Configuration contract for the independent DM bridge Module。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SETTINGS_NAME = "dm"

DEFAULT_SETTINGS: dict[str, Any] = {
    "recent_senders_limit": 200,
    "forward_map_limit": 200,
    "owner_reply_prefix": "來自擁有者回覆：\n",
}


def build_settings_schema(rule_type) -> dict[str, Any]:
    """Return the Core Settings schema without importing Core at module import."""

    return {
        "recent_senders_limit": rule_type(int, minimum=1, maximum=10_000),
        "forward_map_limit": rule_type(int, minimum=1, maximum=10_000),
        "owner_reply_prefix": rule_type(
            str,
            validator=lambda value: len(value) <= 500,
            description="must be 500 characters or fewer",
        ),
    }


@dataclass(frozen=True, slots=True)
class DMSettings:
    """Validated runtime settings owned by the DM bridge Module."""

    recent_senders_limit: int
    forward_map_limit: int
    owner_reply_prefix: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DMSettings":
        settings = cls(
            recent_senders_limit=int(raw["recent_senders_limit"]),
            forward_map_limit=int(raw["forward_map_limit"]),
            owner_reply_prefix=str(raw["owner_reply_prefix"]),
        )
        if settings.recent_senders_limit < 1 or settings.forward_map_limit < 1:
            raise ValueError("DM mapping limits must be positive")
        if len(settings.owner_reply_prefix) > 500:
            raise ValueError("owner_reply_prefix is too long")
        return settings
