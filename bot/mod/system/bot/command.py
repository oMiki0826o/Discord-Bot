"""
bot/mod/system/bot/command.py

Modification():

- 提供 Owner 專用 Bot 控制面板指令。
- 支援透過 $bot 開啟 Bot System 控制面板。
- 支援查看 Bot 執行狀態。
- 支援向 Application 請求安全關閉 Bot。

本檔提供 Bot Runtime 與系統控制面板的 Owner 管理介面。
"""

from __future__ import annotations

import time

import discord
from discord.ext import commands

from bot.core.discord.client import DiscordBot
from bot.mod.system.bot.view import BotPanelView


# ── Runtime 資訊 ──────────────────────

def _format_uptime(
    seconds: float,
) -> str:
    """將執行秒數格式化為易讀時間。"""

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

    if hours or days:
        parts.append(
            f"{hours} 小時"
        )

    if minutes or hours or days:
        parts.append(
            f"{minutes} 分"
        )

    parts.append(
        f"{seconds} 秒"
    )

    return " ".join(parts)


def _get_member_count(
    bot: commands.Bot,
) -> int:
    """取得目前 Bot 可見 Guild 的成員總數。"""

    return sum(
        guild.member_count or 0
        for guild in bot.guilds
    )


def _build_status_embed(
    bot: commands.Bot,
) -> discord.Embed:
    """建立 Bot Runtime 狀態 Embed。"""

    startup_time = getattr(
        bot,
        "startup_time",
        time.perf_counter(),
    )

    uptime = (
        time.perf_counter()
        - startup_time
    )

    latency = round(
        bot.latency * 1000
    )

    user = bot.user

    embed = discord.Embed(
        title="Bot 狀態",
        description="目前 Bot Runtime 狀態。",
    )

    embed.add_field(
        name="帳號",
        value=(
            f"`{user}`"
            if user is not None
            else "`Unknown`"
        ),
        inline=False,
    )

    embed.add_field(
        name="延遲",
        value=f"`{latency} ms`",
        inline=True,
    )

    embed.add_field(
        name="執行時間",
        value=(
            f"`{_format_uptime(uptime)}`"
        ),
        inline=True,
    )

    embed.add_field(
        name="伺服器",
        value=f"`{len(bot.guilds)}`",
        inline=True,
    )

    embed.add_field(
        name="成員",
        value=(
            f"`{_get_member_count(bot)}`"
        ),
        inline=True,
    )

    return embed


def _build_health_embed(
    bot: DiscordBot,
) -> discord.Embed:
    """建立供 Owner 使用的核心健康檢查結果。"""

    embed = discord.Embed(
        title="Bot 健康狀態",
        description="Core 與模組的即時狀態。",
    )
    loader = bot.module_loader
    if loader is None:
        embed.add_field(name="模組", value="`未初始化`", inline=False)
        return embed

    summaries = loader.health_summary()
    if not summaries:
        embed.add_field(name="模組", value="`目前沒有可用模組`", inline=False)
        return embed

    failed = [module for module in summaries if module["status"] == "failed"]
    lines = []
    if not failed:
        lines.append(f"全部 {len(summaries)} 個 Module 狀態正常。")
    else:
        lines.append(f"共 {len(summaries)} 個 Module，失敗 {len(failed)} 個：")
    modules_to_show = failed or summaries
    for module in modules_to_show:
        status = str(module["status"])
        version = str(module["version"])
        line = f"`{module['name']}` · `{status}` · v{version}"
        if module["error"]:
            line += f"\n  `{module['error']}`"
        lines.append(line)

    embed.add_field(
        name="模組",
        value="\n".join(lines)[:1024],
        inline=False,
    )
    return embed


# ── Bot 管理 ──────────────────────

class BotManagementCog(commands.Cog):
    """提供 Owner 專用 Bot 管理介面。"""

    def __init__(
        self,
        bot: DiscordBot,
    ) -> None:
        self.bot = bot

    # ── Bot Group ──────────────────────

    @commands.group(
        name="bot",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def runtime(
        self,
        ctx: commands.Context,
    ) -> None:
        """開啟 Bot System 控制面板。"""

        view = BotPanelView(
            bot=self.bot,
            owner_id=ctx.author.id,
        )

        message = await ctx.send(
            embed=view.build_overview_embed(),
            view=view,
        )

        view.message = message

    # ── Status ──────────────────────

    @runtime.command(
        name="status",
    )
    @commands.is_owner()
    async def runtime_status(
        self,
        ctx: commands.Context,
    ) -> None:
        """顯示 Bot Runtime 狀態。"""

        await ctx.send(
            embed=_build_status_embed(
                self.bot
            )
        )

    @runtime.command(name="health")
    @commands.is_owner()
    async def runtime_health(
        self,
        ctx: commands.Context,
    ) -> None:
        """顯示 Core 與 Module 健康狀態。"""

        await ctx.send(embed=_build_health_embed(self.bot))

    # ── Stop ──────────────────────

    @runtime.command(
        name="stop",
    )
    @commands.is_owner()
    async def runtime_stop(
        self,
        ctx: commands.Context,
    ) -> None:
        """向 Application 請求安全關閉 Bot。"""

        if self.bot.shutdown_event.is_set():
            await ctx.send(
                "Bot 已經正在關閉。"
            )
            return

        await ctx.send(
            "正在安全關閉 Bot..."
        )

        self.bot.request_shutdown()
