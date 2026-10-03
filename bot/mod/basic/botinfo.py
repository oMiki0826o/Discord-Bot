"""
bot/mod/basic/botinfo.py

Modification():

- 提供 Bot Info Slash Command。
- 顯示 Bot 基本資訊。
- 顯示 Discord WebSocket 延遲。
- 顯示 Bot 目前服務的伺服器與使用者數量。
- 顯示 Bot 本次執行時間。

本檔只負責 /botinfo 指令，
不負責 Basic Module 註冊或 Bot 生命週期管理。
"""

from __future__ import annotations

import time

import discord

from discord import app_commands
from discord.ext import commands


# ── 時間格式化 ──────────────────────

def _format_uptime(seconds: float) -> str:
    """將執行秒數轉換為易讀時間。"""

    total_seconds = max(
        0,
        int(seconds),
    )

    days, remainder = divmod(
        total_seconds,
        86400,
    )

    hours, remainder = divmod(
        remainder,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    parts: list[str] = []

    if days:
        parts.append(
            f"{days} 天"
        )

    if hours:
        parts.append(
            f"{hours} 小時"
        )

    if minutes:
        parts.append(
            f"{minutes} 分"
        )

    parts.append(
        f"{seconds} 秒"
    )

    return " ".join(parts)


# ── Bot Info Cog ──────────────────────

class BotInfoCog(commands.Cog):
    """提供 Bot 基本資訊查詢功能。"""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot


    # ── Bot Info ──────────────────────

    @app_commands.command(
        name="botinfo",
        description="查看 Bot 基本資訊。",
    )
    async def botinfo(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """顯示 Bot 基本資訊。"""

        if self.bot.user is None:
            await interaction.response.send_message(
                "目前無法取得 Bot 資訊。",
                ephemeral=True,
            )
            return

        latency_ms = round(
            self.bot.latency * 1000
        )

        user_count = sum(
            guild.member_count or 0
            for guild in self.bot.guilds
        )

        startup_time = getattr(
            self.bot,
            "startup_time",
            None,
        )

        if isinstance(
            startup_time,
            (int, float),
        ):
            uptime = _format_uptime(
                time.perf_counter()
                - startup_time
            )
        else:
            uptime = "無法取得"

        embed = discord.Embed(
            title="Bot 資訊",
            color=discord.Color.blurple(),
        )

        embed.set_thumbnail(
            url=self.bot.user.display_avatar.url
        )

        embed.add_field(
            name="名稱",
            value=str(self.bot.user),
            inline=True,
        )

        embed.add_field(
            name="Discord ID",
            value=str(self.bot.user.id),
            inline=True,
        )

        embed.add_field(
            name="延遲",
            value=f"{latency_ms} ms",
            inline=True,
        )

        embed.add_field(
            name="伺服器數量",
            value=str(len(self.bot.guilds)),
            inline=True,
        )

        embed.add_field(
            name="使用者數量",
            value=str(user_count),
            inline=True,
        )

        embed.add_field(
            name="執行時間",
            value=uptime,
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed
        )