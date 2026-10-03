"""
bot/mod/guild/stats/worker.py

Modification():

- Throttled dirty-event worker for Guild statistics。
"""

from __future__ import annotations

import asyncio

from discord.ext import commands

from bot.core.logging.manager import LogManager
from bot.mod.guild.stats.service import GuildStatsService


logger = LogManager().get_logger("guild.stats.worker")


class GuildStatsWorker:
    def __init__(self, bot: commands.Bot, service: GuildStatsService, *, reconcile_seconds: float) -> None:
        self.bot = bot
        self.service = service
        self.reconcile_seconds = reconcile_seconds
        self._dirty: set[int] = set()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def mark_dirty(self, guild_id: int) -> None:
        self._dirty.add(guild_id)
        self._wake.set()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="guild_stats_worker")

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
                await asyncio.wait_for(self._wake.wait(), timeout=self.reconcile_seconds)
                guild_ids = tuple(self._dirty)
            except TimeoutError:
                guild_ids = tuple(guild.id for guild in self.bot.guilds)
            self._wake.clear()
            self._dirty.difference_update(guild_ids)
            for guild_id in guild_ids:
                guild = self.bot.get_guild(guild_id)
                if guild is not None:
                    try:
                        await self.service.refresh_guild(guild)
                    except Exception:
                        logger.exception("統計頻道背景更新失敗 guild=%s", guild_id)
