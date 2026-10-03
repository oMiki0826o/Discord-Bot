"""
bot/mod/system/presence.py

Modification():

- 提供 Owner 專用 Presence 管理指令。
- 支援查看目前套用的 Discord 狀態。
- 支援從 Settings 重新套用 Bot Presence。

本檔提供 Discord Presence 的 Owner 管理介面。
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.settings.manager import get


# ── Presence 顯示 ──────────────────────

_ACTIVITY_LABELS = {
    "playing": "遊玩中",
    "listening": "聆聽中",
    "watching": "觀看中",
    "competing": "競賽中",
}


def _get_presence_settings() -> tuple[str, str, str]:
    """取得目前 Settings 中的 Presence 設定。"""

    activity_type = str(
        get("bot.presence.activity", "listening")
    )
    text = str(
        get("bot.presence.text", "")
    )
    status = str(
        get("bot.presence.status", "online")
    )

    return activity_type, text, status


def _build_presence_embed() -> discord.Embed:
    """建立目前 Presence 資訊 Embed。"""

    activity_type, text, status = _get_presence_settings()

    activity_label = _ACTIVITY_LABELS.get(
        activity_type,
        activity_type,
    )

    embed = discord.Embed(
        title="Discord 狀態",
        description="目前套用的 Discord 狀態。",
    )

    embed.add_field(
        name="活動類型",
        value=f"`{activity_label}`",
        inline=True,
    )

    embed.add_field(
        name="上線狀態",
        value=f"`{status}`",
        inline=True,
    )

    embed.add_field(
        name="顯示文字",
        value=f"`{text or '未設定'}`",
        inline=False,
    )

    embed.set_footer(
        text="$presence reload 重新套用 Discord 狀態"
    )

    return embed


# ── Presence 管理 ──────────────────────

class PresenceManagementCog(commands.Cog):
    """提供 Owner 專用 Presence 管理指令。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(
        name="presence",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def presence(
        self,
        ctx: commands.Context,
    ) -> None:
        """顯示目前 Discord 狀態。"""

        await ctx.send(
            embed=_build_presence_embed()
        )

    @presence.command(name="reload")
    @commands.is_owner()
    async def presence_reload(
        self,
        ctx: commands.Context,
    ) -> None:
        """從設定重新套用 Discord 狀態。"""

        refresh_presence = getattr(
            self.bot,
            "refresh_presence",
            None,
        )

        if refresh_presence is None:
            await ctx.send(
                "目前無法重新套用 Discord 狀態。"
            )
            return

        try:
            await refresh_presence()
        except discord.HTTPException as exc:
            await ctx.send(
                "Discord 狀態更新失敗。\n"
                f"`{exc}`"
            )
            return

        await ctx.send(
            embed=_build_presence_embed()
        )