"""
bot/mod/guild/announcement/model.py

Modification():

- Announcement state machine and persisted domain model。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class AnnouncementStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    FAILED = "failed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Announcement:
    id: str
    guild_id: int
    author_id: int
    target_channel_id: int
    mention_role_id: int
    title: str
    content: str
    color: int
    status: AnnouncementStatus
    created_at: datetime
    updated_at: datetime
    image_url: str = ""
    attachment_path: str = ""
    scheduled_at: datetime | None = None
    claimed_at: datetime | None = None
    published_at: datetime | None = None
    discord_message_id: int = 0
    failure_count: int = 0
    last_error: str = ""

    def validate(self) -> None:
        if not self.id or len(self.id) > 64:
            raise ValueError("公告 id 格式錯誤")
        if not self.title or len(self.title) > 256:
            raise ValueError("公告標題必須為 1 到 256 字")
        if not self.content or len(self.content) > 4096:
            raise ValueError("公告內容必須為 1 到 4096 字")
        if not 0 <= self.color <= 0xFFFFFF:
            raise ValueError("公告顏色超出範圍")
        if self.status is AnnouncementStatus.SCHEDULED and self.scheduled_at is None:
            raise ValueError("排程公告缺少 scheduled_at")
