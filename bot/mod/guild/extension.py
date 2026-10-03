"""
bot/mod/guild/extension.py

Modification():

- 提供 Guild Module 的 Discord Extension 入口。
- 註冊 Guild Module 預設 Settings。
- 建立 Guild Module 自有 Database。
- 組裝並註冊伺服器設定與成員事件 Cog。

本檔只負責 Guild Module 的組裝與註冊。
"""

from __future__ import annotations

from discord.ext import commands

from bot.config import DATABASE_DIR
from bot.core.settings.manager import settings
from bot.mod.guild.command import GuildCommandCog
from bot.mod.guild.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)
from bot.mod.guild.database import GuildDatabase
from bot.mod.guild.member import GuildMemberCog
from bot.mod.guild.announcement.repository import AnnouncementRepository
from bot.mod.guild.announcement.scheduler import AnnouncementScheduler
from bot.mod.guild.announcement.service import AnnouncementService
from bot.mod.guild.background import GuildBackgroundCog
from bot.mod.guild.stats.repository import GuildStatsRepository
from bot.mod.guild.stats.service import GuildStatsService
from bot.mod.guild.stats.worker import GuildStatsWorker

MODULE_VERSION = "0.1.0"
MODULE_DISPLAY_NAME = "伺服器設定"
MODULE_DEPENDENCIES: tuple[str, ...] = ()


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Guild Module。"""

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    database = GuildDatabase(
        DATABASE_DIR / "guild.db"
    )

    stats_repository = GuildStatsRepository(database)
    stats_configuration = configuration["stats"]
    stats_service = GuildStatsService(
        stats_repository,
        minimum_rename_interval_seconds=float(
            stats_configuration["minimum_rename_interval_seconds"]
        ),
    )
    stats_worker = GuildStatsWorker(
        bot,
        stats_service,
        reconcile_seconds=float(stats_configuration["reconcile_seconds"]),
    )

    announcement_repository = AnnouncementRepository(database)
    announcement_service = AnnouncementService()
    announcement_configuration = configuration["announcement"]
    announcement_scheduler = AnnouncementScheduler(
        bot,
        announcement_repository,
        announcement_service,
        poll_seconds=float(announcement_configuration["poll_seconds"]),
        max_attempts=int(announcement_configuration["max_publish_attempts"]),
    )

    await bot.add_cog(
        GuildCommandCog(
            bot,
            database=database,
            embed_footer=str(
                configuration["embed_footer"]
            ),
            panel_timeout_seconds=int(
                configuration[
                    "panel_timeout_seconds"
                ]
            ),
            selection_timeout_seconds=int(
                configuration[
                    "selection_timeout_seconds"
                ]
            ),
            confirmation_timeout_seconds=int(
                configuration[
                    "confirmation_timeout_seconds"
                ]
            ),
            stats_repository=stats_repository,
            stats_service=stats_service,
            announcement_repository=announcement_repository,
            announcement_service=announcement_service,
            max_stat_channels=int(stats_configuration["max_channels_per_guild"]),
        )
    )

    await bot.add_cog(
        GuildMemberCog(
            bot,
            database=database,
            welcome_template=str(
                configuration[
                    "welcome_template"
                ]
            ),
            leave_template=str(
                configuration[
                    "leave_template"
                ]
            ),
            embed_footer=str(
                configuration["embed_footer"]
            ),
        )
    )

    await bot.add_cog(
        GuildBackgroundCog(
            stats_repository=stats_repository,
            stats_worker=stats_worker,
            announcement_scheduler=announcement_scheduler,
        )
    )
