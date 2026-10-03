"""
bot/mod/basic/ping.py

Modification():

- 提供 Ping Slash Command。
- 顯示 Discord WebSocket 延遲。

本檔只負責 /ping 指令，
不負責 Basic Module 註冊或其他基礎功能。
"""

from __future__ import annotations

import discord

from discord import app_commands
from discord.ext import commands


# ── Ping Cog ──────────────────────

class PingCog(commands.Cog):
    """提供 Bot 延遲查詢功能。"""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot


    # ── Ping ──────────────────────

    @app_commands.command(
        name="ping",
        description="查看 Bot 目前延遲。",
    )
    async def ping(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """顯示 Discord WebSocket 延遲。"""

        latency_ms = round(
            self.bot.latency * 1000
        )

        await interaction.response.send_message(
            f"Ping：**{latency_ms} ms**"
        )