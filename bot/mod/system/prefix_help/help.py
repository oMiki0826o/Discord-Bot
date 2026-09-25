"""
bot/mod/system/prefix_help/help.py

Modification():

- 提供 Owner 專用 Prefix Help 指令。
- 顯示 System Module 的頂層管理指令。
- 支援查詢各管理指令的詳細說明。

本檔負責 Owner Prefix Commands 的說明介面。
"""

from __future__ import annotations

import discord
from discord.ext import commands


# ── Help 資料 ──────────────────────

_HELP_ENTRIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "mod": (
        "管理 Bot Modules。",
        (
            "$mod",
            "$mod list",
            "$mod load <module>",
            "$mod unload <module>",
            "$mod reload <module>",
            "$mod reload-all",
        ),
    ),
    "settings": (
        "查看與重新載入 Bot 設定。",
        (
            "$settings",
            "$settings show [name]",
            "$settings reload [name]",
            "$settings reload-all",
        ),
    ),
    "slash": (
        "同步 Discord Slash Commands。",
        (
            "$slash",
            "$slash guild",
        ),
    ),
    "presence": (
        "查看與管理 Bot Presence。",
        (
            "$presence",
            "$presence show",
            "$presence set <type> <text>",
            "$presence reload",
        ),
    ),
    "bot": (
        "管理 Bot Runtime 與生命週期。",
        (
            "$bot",
            "$bot status",
            "$bot stop",
        ),
    ),
}


# ── Owner Help ──────────────────────

class OwnerHelpCog(commands.Cog):
    """提供 Owner 專用 Prefix Help。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="help")
    @commands.is_owner()
    async def help_command(
        self,
        ctx: commands.Context,
        command_name: str | None = None,
    ) -> None:
        """顯示 Owner Prefix Commands 說明。"""

        if command_name is None:
            await self._send_overview(ctx)
            return

        await self._send_command_help(ctx, command_name.lower())

    async def _send_overview(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="Owner 管理指令",
            description="Bot 的系統管理指令。",
        )

        for name, (description, _) in _HELP_ENTRIES.items():
            embed.add_field(
                name=f"${name}",
                value=description,
                inline=False,
            )

        embed.set_footer(text="$help <command> 查看詳細用法")

        await ctx.send(embed=embed)

    async def _send_command_help(
        self,
        ctx: commands.Context,
        command_name: str,
    ) -> None:
        entry = _HELP_ENTRIES.get(command_name)

        if entry is None:
            await ctx.send(f"找不到 Owner 指令：`{command_name}`")
            return

        description, usages = entry

        embed = discord.Embed(
            title=f"${command_name}",
            description=description,
        )

        embed.add_field(
            name="用法",
            value="\n".join(f"`{usage}`" for usage in usages),
            inline=False,
        )

        await ctx.send(embed=embed)
