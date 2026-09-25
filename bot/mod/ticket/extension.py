"""
bot/mod/ticket/extension.py

Modification():

- 提供 Ticket Module 的 Discord Extension 入口。
- 註冊 Ticket Module 預設 Settings。
- 建立 Ticket Module 自有 Database。
- 組裝 Ticket Service 並註冊 Discord Cog。

本檔只負責 Ticket Module 的組裝與註冊。
"""

from __future__ import annotations

from discord.ext import commands

from bot.config import DATABASE_DIR
from bot.core.settings.manager import settings
from bot.mod.ticket.command import TicketCog
from bot.mod.ticket.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)
from bot.mod.ticket.database import TicketDatabase
from bot.mod.ticket.ticket import TicketService


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Ticket Module。"""

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    database = TicketDatabase(
        DATABASE_DIR / "ticket.db"
    )

    service = TicketService(
        bot,
        database=database,
        cooldown_seconds=int(
            configuration[
                "cooldown_seconds"
            ]
        ),
        max_per_user=int(
            configuration[
                "max_per_user"
            ]
        ),
        channel_prefix=str(
            configuration[
                "channel_prefix"
            ]
        ),
        category_name=str(
            configuration[
                "category_name"
            ]
        ),
        archive_category=str(
            configuration[
                "archive_category"
            ]
        ),
        close_delay_seconds=int(
            configuration[
                "close_delay_seconds"
            ]
        ),
        panel_title=str(
            configuration[
                "panel_title"
            ]
        ),
        panel_description=str(
            configuration[
                "panel_description"
            ]
        ),
    )

    await bot.add_cog(
        TicketCog(
            bot,
            service=service,
            management_timeout_seconds=int(
                configuration[
                    "management_timeout_seconds"
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
