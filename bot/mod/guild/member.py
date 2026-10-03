"""
bot/mod/guild/member.py

Modification():

- 處理伺服器成員加入與離開事件。
- 發送歡迎與離開訊息。
- 為新成員套用自動身分組。
- 將成員進出事件寫入指定 Discord 日誌頻道。

本檔負責 Guild Module 的成員生命週期事件。
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.mod.guild.database import GuildDatabase


logger = logging.getLogger(
    "bot.mod.guild.member"
)


# ── Helpers ──────────────────────

def format_member_message(
    template: str,
    member: discord.Member,
) -> str:
    """套用 Guild Module 支援的訊息範本變數。"""

    return (
        template
        .replace(
            "{user}",
            member.mention,
        )
        .replace(
            "{username}",
            str(member),
        )
        .replace(
            "{guild}",
            member.guild.name,
        )
        .replace(
            "{count}",
            str(
                member.guild.member_count
                or 0
            ),
        )
    )


# ── Member Cog ──────────────────────

class GuildMemberCog(commands.Cog):
    """處理 Guild 成員加入與離開事件。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        database: GuildDatabase,
        welcome_template: str,
        leave_template: str,
        embed_footer: str,
    ) -> None:
        self.bot = bot
        self.database = database
        self.welcome_template = welcome_template
        self.leave_template = leave_template
        self.embed_footer = embed_footer

    # ── Member Events ──────────────────────

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member,
    ) -> None:
        """處理成員加入事件。"""

        guild = member.guild
        settings = self.database.get_settings(
            guild.id
        )

        await self._send_member_message(
            guild,
            settings.welcome_channel_id,
            format_member_message(
                self.welcome_template,
                member,
            ),
            event="welcome",
        )

        if settings.auto_role_id:
            role = guild.get_role(
                settings.auto_role_id
            )

            if role is not None:
                try:
                    await member.add_roles(
                        role,
                        reason="自動身分組",
                    )
                except discord.HTTPException:
                    logger.exception(
                        "自動身分組套用失敗 guild_id=%s member_id=%s role_id=%s",
                        guild.id,
                        member.id,
                        role.id,
                    )

        embed = discord.Embed(
            title="成員加入",
            description=(
                f"{member.mention}（{member}）"
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(
            url=member.display_avatar.url
        )
        embed.set_footer(
            text=(
                f"ID: {member.id}  |  "
                f"{self.embed_footer}"
            )
        )

        await self._send_log(
            guild,
            settings.log_channel_id,
            embed,
        )

        logger.info(
            "成員加入 guild_id=%s member_id=%s",
            guild.id,
            member.id,
        )

    @commands.Cog.listener()
    async def on_member_remove(
        self,
        member: discord.Member,
    ) -> None:
        """處理成員離開事件。"""

        guild = member.guild
        settings = self.database.get_settings(
            guild.id
        )

        await self._send_member_message(
            guild,
            settings.leave_channel_id,
            format_member_message(
                self.leave_template,
                member,
            ),
            event="leave",
        )

        embed = discord.Embed(
            title="成員離開",
            description=(
                f"{member}（{member.id}）"
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=self.embed_footer
        )

        await self._send_log(
            guild,
            settings.log_channel_id,
            embed,
        )

    # ── Discord Output ──────────────────────

    @staticmethod
    async def _send_member_message(
        guild: discord.Guild,
        channel_id: int,
        content: str,
        *,
        event: str,
    ) -> None:
        """將成員事件訊息送至設定的文字頻道。"""

        if not channel_id:
            return

        channel = guild.get_channel(
            channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return

        try:
            await channel.send(
                content
            )
        except discord.HTTPException:
            logger.exception(
                "成員事件訊息發送失敗 event=%s guild_id=%s channel_id=%s",
                event,
                guild.id,
                channel.id,
            )

    @staticmethod
    async def _send_log(
        guild: discord.Guild,
        channel_id: int,
        embed: discord.Embed,
    ) -> None:
        """將成員事件 Embed 送至管理日誌頻道。"""

        if not channel_id:
            return

        channel = guild.get_channel(
            channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return

        try:
            await channel.send(
                embed=embed
            )
        except discord.HTTPException:
            logger.exception(
                "Guild 日誌發送失敗 guild_id=%s channel_id=%s",
                guild.id,
                channel.id,
            )
