"""
bot/mod/guild/stats/service.py

Modification():

- Statistic calculation and Discord channel rename service。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import discord

from bot.core.logging.manager import LogManager
from bot.mod.guild.stats.model import StatChannel, StatMetric
from bot.mod.guild.stats.repository import GuildStatsRepository


logger = LogManager().get_logger("guild.stats")


@dataclass(frozen=True, slots=True)
class StatRefreshReport:
    updated: int = 0
    unchanged: int = 0
    failed: int = 0


class GuildStatsService:
    def __init__(self, repository: GuildStatsRepository, *, minimum_rename_interval_seconds: float) -> None:
        self.repository = repository
        self.minimum_rename_interval_seconds = minimum_rename_interval_seconds
        self._last_rename: dict[tuple[int, int], float] = {}

    @staticmethod
    def _count(guild: Any, config: StatChannel) -> int:
        members = tuple(getattr(guild, "members", ()))
        if config.metric is StatMetric.MEMBER_TOTAL:
            return int(getattr(guild, "member_count", None) or len(members))
        if config.metric is StatMetric.HUMAN_TOTAL:
            return sum(not member.bot for member in members)
        if config.metric is StatMetric.BOT_TOTAL:
            return sum(member.bot for member in members)
        if config.metric is StatMetric.ONLINE_TOTAL:
            state = getattr(guild, "_state", None)
            intents = getattr(state, "_intents", None)
            if intents is not None and not getattr(intents, "presences", False):
                raise ValueError("Presence Intent 未啟用，無法提供可靠在線人數")
            return sum(str(getattr(member, "status", "offline")) != "offline" for member in members)
        role = guild.get_role(config.role_id)
        if role is None:
            raise ValueError(f"找不到身分組 {config.role_id}")
        return len(role.members)

    async def refresh_guild(self, guild: Any, *, force: bool = False) -> StatRefreshReport:
        updated = unchanged = failed = 0
        now = time.monotonic()
        for config in self.repository.list_for_guild(guild.id):
            if not config.enabled:
                continue
            channel = guild.get_channel(config.channel_id)
            if channel is None:
                self.repository.update_result(guild.id, config.channel_id, name=config.last_rendered_name, error="頻道不存在")
                failed += 1
                continue
            try:
                name = config.label_template.format(count=self._count(guild, config))[:100]
                if channel.name == name:
                    self.repository.update_result(guild.id, config.channel_id, name=name, error="")
                    unchanged += 1
                    continue
                key = (guild.id, config.channel_id)
                if not force and now - self._last_rename.get(key, 0.0) < self.minimum_rename_interval_seconds:
                    unchanged += 1
                    continue
                await channel.edit(name=name, reason="更新伺服器統計頻道")
                self._last_rename[key] = now
                self.repository.update_result(guild.id, config.channel_id, name=name, error="")
                updated += 1
            except (ValueError, discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
                logger.warning("統計頻道更新失敗 guild=%s channel=%s error=%s", guild.id, config.channel_id, exc)
                self.repository.update_result(guild.id, config.channel_id, name=config.last_rendered_name, error=str(exc))
                failed += 1
        return StatRefreshReport(updated, unchanged, failed)
