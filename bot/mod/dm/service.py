"""
bot/mod/dm/service.py

Modification():

- Discord-independent routing state for the Owner DM bridge。
"""

from __future__ import annotations

from collections import OrderedDict

from .config import DMSettings


def parse_reply_target(value: str) -> tuple[str | None, str]:
    """Parse `$dm reply` content into an optional Discord ID and message body."""

    raw_parts = value.split(maxsplit=1)
    normalized = value.strip()
    if not normalized:
        raise ValueError("content must not be blank")
    if len(raw_parts) == 1 and raw_parts[0].isdecimal() and 15 <= len(raw_parts[0]) <= 20:
        raise ValueError("content must not be blank")
    parts = normalized.split(maxsplit=1)
    if len(parts) == 2 and parts[0].isdecimal() and 15 <= len(parts[0]) <= 20:
        content = parts[1].strip()
        if not content:
            raise ValueError("content must not be blank")
        return parts[0], content
    return None, normalized


class DMBridgeService:
    """Maintain bounded, non-persistent DM sender and forward mappings."""

    def __init__(self, settings: DMSettings) -> None:
        self.settings = settings
        self._recent_senders: OrderedDict[str, None] = OrderedDict()
        self._forwards: OrderedDict[str, str] = OrderedDict()

    @property
    def last_sender_id(self) -> str | None:
        return next(reversed(self._recent_senders), None)

    @property
    def recent_sender_ids(self) -> tuple[str, ...]:
        return tuple(self._recent_senders)

    def remember_sender(self, user_id: str) -> None:
        normalized = self._require_id(user_id, field_name="user_id")
        self._recent_senders[normalized] = None
        self._recent_senders.move_to_end(normalized)
        self._trim(self._recent_senders, self.settings.recent_senders_limit)

    def remember_forward(self, forwarded_message_id: str, user_id: str) -> None:
        forward_id = self._require_id(forwarded_message_id, field_name="forwarded_message_id")
        sender_id = self._require_id(user_id, field_name="user_id")
        self._forwards[forward_id] = sender_id
        self._forwards.move_to_end(forward_id)
        self._trim(self._forwards, self.settings.forward_map_limit)

    def sender_for_forward(self, forwarded_message_id: str) -> str | None:
        return self._forwards.get(str(forwarded_message_id))

    @staticmethod
    def _require_id(value: str, *, field_name: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be blank")
        return normalized

    @staticmethod
    def _trim(values: OrderedDict[str, object], limit: int) -> None:
        while len(values) > limit:
            values.popitem(last=False)
