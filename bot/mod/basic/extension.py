"""
bot/mod/basic/extension.py

Modification():

- 提供 Basic Module 的 Discord Extension 入口。
- 統一註冊 Basic Module 所有 Cog。

本檔只負責 Basic Module 的組裝與註冊，
不實作個別 Discord 指令。
"""

from __future__ import annotations

from discord.ext import commands

from bot.mod.basic.botinfo import BotInfoCog
from bot.mod.basic.help.command import HelpCog
from bot.mod.basic.ping import PingCog


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Basic Module。"""

    await bot.add_cog(
        PingCog(bot)
    )

    await bot.add_cog(
        BotInfoCog(bot)
    )

    await bot.add_cog(
        HelpCog(bot)
    )