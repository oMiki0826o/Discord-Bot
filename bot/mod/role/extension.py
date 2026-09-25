"""
bot/mod/role/extension.py

Modification():

- 提供 Role Module 的 Discord Extension 入口。
- 註冊 Role Module 預設 Settings。
- 建立 Role Module 自有 Database。
- 組裝身分組面板服務並註冊 Discord Cog。

本檔只負責 Role Module 的組裝與註冊。
"""

from __future__ import annotations

from discord.ext import commands

from bot.config import DATABASE_DIR
from bot.core.settings.manager import settings
from bot.mod.role.command import RoleCommandCog
from bot.mod.role.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)
from bot.mod.role.database import RoleDatabase
from bot.mod.role.panel import RolePanelService


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Role Module。"""

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    database = RoleDatabase(
        DATABASE_DIR / "role.db"
    )
    service = RolePanelService(
        bot,
        database,
    )

    await bot.add_cog(
        RoleCommandCog(
            bot,
            service=service,
            default_panel_title=str(
                configuration[
                    "panel_title"
                ]
            ),
            default_panel_description=str(
                configuration[
                    "panel_description"
                ]
            ),
            management_timeout_seconds=int(
                configuration[
                    "management_timeout_seconds"
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
