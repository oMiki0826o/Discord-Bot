"""
bot/mod/ai/access.py

Modification():

- 建立私人、公開 Profile、頻道可見與 Owner 授權資料的統一政策。

本檔案是 Agent Tool 讀取資料前的程式強制邊界。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Visibility(StrEnum):
    PRIVATE_USER = "private_user"
    PUBLIC_PROFILE = "public_profile"
    CHANNEL_VISIBLE = "channel_visible"
    OWNER_AUTHORIZED = "owner_authorized"


@dataclass(frozen=True, slots=True)
class AccessContext:
    requester_user_id: str
    current_channel_id: str
    can_read_channel: bool = False
    is_owner: bool = False
    owner_authorized: bool = False


class AccessPolicy:
    def can_read(self, visibility: Visibility, *, owner_user_id: str | None, channel_id: str | None, context: AccessContext) -> bool:
        if visibility is Visibility.PRIVATE_USER:
            return owner_user_id == context.requester_user_id
        if visibility is Visibility.PUBLIC_PROFILE:
            return True
        if visibility is Visibility.CHANNEL_VISIBLE:
            return context.can_read_channel and channel_id == context.current_channel_id
        if visibility is Visibility.OWNER_AUTHORIZED:
            return context.is_owner and context.owner_authorized
        return False

