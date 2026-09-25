"""
bot/mod/logging/extension.py

Modification():

- 註冊 Logging Module 預設 Settings。
- 載入 Logging Module 的 Discord 管理指令。

本檔為 Logging Module 的載入入口。
"""

from __future__ import annotations

from discord.ext import commands

from bot.core.settings.manager import settings
from bot.mod.logging.command import LoggingManagementCog
from bot.mod.logging.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)


# ── Module Setup ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """載入 Logging Module。"""

    settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    await bot.add_cog(
        LoggingManagementCog(bot)
    )