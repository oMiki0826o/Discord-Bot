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
