"""
bot/mod/guild/announcement/scheduler.py

Modification():

- Recoverable announcement scheduler with atomic claims。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.core.logging.manager import LogManager
from bot.mod.guild.announcement.repository import AnnouncementRepository
from bot.mod.guild.announcement.service import (
    AnnouncementService,
    PermanentAnnouncementError,
    TransientAnnouncementError,
)


logger = LogManager().get_logger("guild.announcement.scheduler")


@dataclass(frozen=True, slots=True)
class AnnouncementRunReport:
    published: int = 0
    failed: int = 0
    retried: int = 0


class AnnouncementScheduler:
    def __init__(
        self,
        bot,
        repository: AnnouncementRepository,
        service: AnnouncementService,
        *,
        poll_seconds: float,
        max_attempts: int,
    ) -> None:
        self.bot = bot
        self.repository = repository
        self.service = service
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="announcement_scheduler")

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("公告排程週期執行失敗")
            await asyncio.sleep(self.poll_seconds)

    async def run_once(self, *, now: datetime | None = None) -> AnnouncementRunReport:
        now = now or datetime.now(timezone.utc)
        due = self.repository.claim_due(
            now=now, stale_after=timedelta(minutes=5), limit=25
        )
        published = failed = retried = 0
        for announcement in due:
            guild = self.bot.get_guild(announcement.guild_id)
            if guild is None:
                self.repository.mark_failed(
                    announcement.guild_id, announcement.id,
                    error="Bot 不在目標伺服器", retry_at=None,
                )
                failed += 1
                continue
            try:
                result = await self.service.publish(guild, announcement)
            except PermanentAnnouncementError as exc:
                self.repository.mark_failed(
                    announcement.guild_id, announcement.id, error=str(exc), retry_at=None
                )
                failed += 1
            except TransientAnnouncementError as exc:
                attempts = announcement.failure_count + 1
                retry_at = None
                if attempts < self.max_attempts:
                    retry_at = now + timedelta(seconds=min(3600, 30 * (2 ** (attempts - 1))))
                    retried += 1
                else:
                    failed += 1
                self.repository.mark_failed(
                    announcement.guild_id, announcement.id,
                    error=str(exc), retry_at=retry_at,
                )
            except Exception as exc:
                logger.exception("公告發佈發生未預期錯誤 id=%s", announcement.id)
                self.repository.mark_failed(
                    announcement.guild_id, announcement.id,
                    error=f"未預期錯誤: {type(exc).__name__}", retry_at=None,
                )
                failed += 1
            else:
                self.repository.mark_published(
                    announcement.guild_id, announcement.id,
                    message_id=result.message_id, published_at=now,
                )
                published += 1
        return AnnouncementRunReport(published, failed, retried)
