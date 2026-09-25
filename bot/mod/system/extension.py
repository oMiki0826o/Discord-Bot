"""
bot/mod/system/extension.py

Modification():

- 提供 System Module 載入入口。
- 註冊 Owner Prefix Commands。
- 註冊 Bot 系統控制面板。

本檔負責將 System Module 的所有 Discord 功能註冊至 Bot。
"""

from __future__ import annotations

from discord.ext import commands

from bot.mod.system.bot.command import BotManagementCog
from bot.mod.system.prefix_help.help import OwnerHelpCog
from bot.mod.system.prefix_help.mod import ModuleManagementCog
from bot.mod.system.presence import PresenceManagementCog
from bot.mod.system.settings import SettingsManagementCog
from bot.mod.system.slash import SlashManagementCog


# ── Extension 入口 ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """載入 System Module。"""

    await bot.add_cog(
        OwnerHelpCog(bot)
    )

    await bot.add_cog(
        ModuleManagementCog(bot)
    )

    await bot.add_cog(
        SettingsManagementCog(bot)
    )

    await bot.add_cog(
        SlashManagementCog(bot)
    )

    await bot.add_cog(
        PresenceManagementCog(bot)
    )

    await bot.add_cog(
        BotManagementCog(bot)
    )