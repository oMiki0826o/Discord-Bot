"""
bot/mod/system/slash.py

Modification():

- 提供 Owner 專用 Slash Command 同步指令。
- 支援全域 Slash Command 同步。
- 支援目前伺服器的 Slash Command 即時同步。
- 顯示同步完成後的指令數量。

本檔提供 Discord Application Commands 的 Owner 管理介面。
"""

from __future__ import annotations

import discord
from discord.ext import commands


class SlashManagementCog(commands.Cog):
    """提供 Owner 專用 Slash Command 同步指令。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── 全域同步 ──────────────────────

    @commands.group(
        name="slash",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def slash(
        self,
        ctx: commands.Context,
    ) -> None:
        """同步全域 Slash Commands。"""

        message = await ctx.send(
            "正在同步全域 Slash Commands..."
        )

        try:
            synced = await self.bot.tree.sync()
        except discord.HTTPException as exc:
            await message.edit(
                content=(
                    "全域 Slash Commands 同步失敗。\n"
                    f"`{exc}`"
                )
            )
            return

        await message.edit(
            content=(
                "全域 Slash Commands 同步完成，"
                f"共 `{len(synced)}` 個指令。"
            )
        )

    # ── Guild 同步 ──────────────────────

    @slash.command(name="guild")
    @commands.guild_only()
    @commands.is_owner()
    async def slash_guild(
        self,
        ctx: commands.Context,
    ) -> None:
        """同步目前 Guild 的 Slash Commands。"""

        guild = ctx.guild

        if guild is None:
            return

        message = await ctx.send(
            f"正在同步 `{guild.name}` 的 Slash Commands..."
        )

        try:
            self.bot.tree.copy_global_to(guild=guild)

            synced = await self.bot.tree.sync(
                guild=guild,
            )
        except discord.HTTPException as exc:
            await message.edit(
                content=(
                    "Guild Slash Commands 同步失敗。\n"
                    f"`{exc}`"
                )
            )
            return

        await message.edit(
            content=(
                f"`{guild.name}` Slash Commands 同步完成，"
                f"共 `{len(synced)}` 個指令。"
            )
        )