"""
bot/mod/guild/background.py

Modification():

- Guild feature background lifecycle and dirty event listeners。
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.mod.guild.announcement.scheduler import AnnouncementScheduler
from bot.mod.guild.stats.repository import GuildStatsRepository
from bot.mod.guild.stats.worker import GuildStatsWorker


class GuildBackgroundCog(commands.Cog):
    def __init__(
        self,
        *,
        stats_repository: GuildStatsRepository,
        stats_worker: GuildStatsWorker,
        announcement_scheduler: AnnouncementScheduler,
    ) -> None:
        self.stats_repository = stats_repository
        self.stats_worker = stats_worker
        self.announcement_scheduler = announcement_scheduler

    async def cog_load(self) -> None:
        await self.stats_worker.start()
        await self.announcement_scheduler.start()

    async def cog_unload(self) -> None:
        await self.stats_worker.close()
        await self.announcement_scheduler.close()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        self.stats_worker.mark_dirty(member.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        self.stats_worker.mark_dirty(member.guild.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        self.stats_worker.mark_dirty(after.guild.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        self.stats_worker.mark_dirty(after.guild.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        self.stats_repository.delete(channel.guild.id, channel.id)
