"""
bot/mod/moderation/extension.py

Modification():

- 提供 Moderation Module 的 Discord Extension 入口。
- 註冊 Moderation Module 預設 Settings。
- 建立 Moderation Module 自有 Database。
- 組裝 Moderation Service 並註冊 Discord Cog。

本檔只負責 Moderation Module 的組裝與註冊。
"""

from __future__ import annotations

from discord.ext import commands

from bot.config import DATABASE_DIR
from bot.core.settings.manager import settings
from bot.mod.moderation.command import ModerationCog
from bot.mod.moderation.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)
from bot.mod.moderation.database import ModerationDatabase
from bot.mod.moderation.service import ModerationService


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Moderation Module。"""

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    database = ModerationDatabase(
        DATABASE_DIR / "moderation.db"
    )

    service = ModerationService(
        bot,
        database=database,
        default_mute_minutes=int(
            configuration[
                "default_mute_minutes"
            ]
        ),
        max_mute_minutes=int(
            configuration[
                "max_mute_minutes"
            ]
        ),
        dm_target_on_warn=bool(
            configuration[
                "dm_target_on_warn"
            ]
        ),
        dm_target_on_mute=bool(
            configuration[
                "dm_target_on_mute"
            ]
        ),
        embed_footer=str(
            configuration[
                "embed_footer"
            ]
        ),
        modlog_limit=int(
            configuration[
                "modlog_limit"
            ]
        ),
    )

    await bot.add_cog(
        ModerationCog(
            bot,
            service=service,
            panel_timeout_seconds=int(
                configuration[
                    "panel_timeout_seconds"
                ]
            ),
            member_selection_timeout_seconds=int(
                configuration[
                    "member_selection_timeout_seconds"
                ]
            ),
            confirmation_timeout_seconds=int(
                configuration[
                    "confirmation_timeout_seconds"
                ]
            ),
        )
    )
