"""
bot/mod/moderation/service.py

Modification():

- 實作封禁、解封、踢出、禁言、解除禁言與警告。
- 實作警告查詢、警告清除、批量刪除與管理紀錄查詢。
- 驗證管理目標的身分組階層與 Bot 權限。
- 記錄管理動作並依設定通知目標成員與 Discord 日誌頻道。

本檔負責 Moderation Module 的主要業務邏輯。
"""

from __future__ import annotations

from datetime import timedelta
import logging

import discord
from discord.ext import commands

from bot.mod.moderation.database import ModerationDatabase


logger = logging.getLogger(
    "bot.mod.moderation.service"
)


# ── Helpers ──────────────────────

def reason_text(
    reason: str | None,
) -> str:
    """將空白原因轉為一致顯示文字。"""

    return reason or "（未填寫原因）"


# ── Moderation Service ──────────────────────

class ModerationService:
    """執行 Moderation Module 的管理操作。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        database: ModerationDatabase,
        default_mute_minutes: int,
        max_mute_minutes: int,
        dm_target_on_warn: bool,
        dm_target_on_mute: bool,
        embed_footer: str,
        modlog_limit: int,
    ) -> None:
        self.bot = bot
        self.database = database
        self.default_mute_minutes = default_mute_minutes
        self.max_mute_minutes = max_mute_minutes
        self.dm_target_on_warn = dm_target_on_warn
        self.dm_target_on_mute = dm_target_on_mute
        self.embed_footer = embed_footer
        self.modlog_limit = modlog_limit

    # ── Permission Validation ──────────────────────

    def can_moderate(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
    ) -> str | None:
        """檢查管理者與 Bot 是否可以管理指定成員。"""

        guild = interaction.guild
        moderator = interaction.user

        if (
            guild is None
            or not isinstance(
                moderator,
                discord.Member,
            )
        ):
            return "無法取得伺服器管理權限資料"

        bot_member = guild.me

        if target.bot:
            return "無法對 Bot 帳號執行此操作"
        if target.id == moderator.id:
            return "無法對自己執行此操作"
        if target.id == guild.owner_id:
            return "無法管理伺服器擁有者"
        if (
            moderator.id != guild.owner_id
            and target.top_role >= moderator.top_role
        ):
            return "目標成員的身分組階層不低於你"
        if (
            target.guild_permissions.administrator
            and moderator.id != guild.owner_id
        ):
            return "無法管理具有管理員權限的成員"
        if (
            bot_member is None
            or target.top_role >= bot_member.top_role
        ):
            return "目標成員的身分組階層不低於 Bot"

        return None

    # ── Member Actions ──────────────────────

    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        reason: str | None,
        delete_days: int,
    ) -> None:
        """封禁成員。"""

        if error := self.can_moderate(
            interaction,
            member,
        ):
            await self._respond(
                interaction,
                error,
            )
            return

        guild = interaction.guild
        moderator = interaction.user
        assert guild is not None
        assert isinstance(moderator, discord.Member)

        reason_value = reason_text(reason)

        try:
            await member.ban(
                reason=reason_value,
                delete_message_days=delete_days,
            )
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少封禁權限。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "封禁失敗 guild_id=%s member_id=%s",
                guild.id,
                member.id,
            )
            await self._respond(
                interaction,
                "封禁失敗。",
            )
            return

        self.database.log_action(
            guild.id,
            "ban",
            member.id,
            moderator.id,
            reason_value,
        )
        embed = self._member_action_embed(
            "封禁",
            member,
            moderator,
            reason_value,
            discord.Color.red(),
        )
        await self._finish_action(
            interaction,
            embed,
        )

    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
    ) -> None:
        """依使用者 ID 解除封禁。"""

        guild = interaction.guild
        moderator = interaction.user

        if (
            guild is None
            or not isinstance(
                moderator,
                discord.Member,
            )
        ):
            await self._respond(
                interaction,
                "此功能只限伺服器使用。",
            )
            return

        try:
            parsed_id = int(user_id)
            user = await self.bot.fetch_user(
                parsed_id
            )
            await guild.unban(
                user
            )
        except ValueError:
            await self._respond(
                interaction,
                "請輸入有效的使用者 ID。",
            )
            return
        except discord.NotFound:
            await self._respond(
                interaction,
                "找不到該使用者或該使用者未被封禁。",
            )
            return
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少解除封禁權限。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "解除封禁失敗 guild_id=%s user_id=%s",
                guild.id,
                user_id,
            )
            await self._respond(
                interaction,
                "解除封禁失敗。",
            )
            return

        self.database.log_action(
            guild.id,
            "unban",
            parsed_id,
            moderator.id,
            "手動解除封禁",
        )

        embed = discord.Embed(
            title="管理動作：解除封禁",
            description=(
                f"已解除 `{user}`（{parsed_id}）的封禁"
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=(
                f"執行者：{moderator}  |  "
                f"{self.embed_footer}"
            )
        )
        await self._finish_action(
            interaction,
            embed,
        )

    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        reason: str | None,
    ) -> None:
        """踢出成員。"""

        if error := self.can_moderate(
            interaction,
            member,
        ):
            await self._respond(
                interaction,
                error,
            )
            return

        guild = interaction.guild
        moderator = interaction.user
        assert guild is not None
        assert isinstance(moderator, discord.Member)

        reason_value = reason_text(reason)

        try:
            await member.kick(
                reason=reason_value
            )
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少踢出權限。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "踢出失敗 guild_id=%s member_id=%s",
                guild.id,
                member.id,
            )
            await self._respond(
                interaction,
                "踢出失敗。",
            )
            return

        self.database.log_action(
            guild.id,
            "kick",
            member.id,
            moderator.id,
            reason_value,
        )
        embed = self._member_action_embed(
            "踢出",
            member,
            moderator,
            reason_value,
            discord.Color.orange(),
        )
        await self._finish_action(
            interaction,
            embed,
        )

    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        minutes: int,
        reason: str | None,
    ) -> None:
        """暫時禁言成員。"""

        if error := self.can_moderate(
            interaction,
            member,
        ):
            await self._respond(
                interaction,
                error,
            )
            return

        guild = interaction.guild
        moderator = interaction.user
        assert guild is not None
        assert isinstance(moderator, discord.Member)

        duration = min(
            minutes or self.default_mute_minutes,
            self.max_mute_minutes,
        )
        reason_value = reason_text(reason)

        try:
            await member.timeout(
                timedelta(
                    minutes=duration
                ),
                reason=reason_value,
            )
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少禁言權限。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "禁言失敗 guild_id=%s member_id=%s",
                guild.id,
                member.id,
            )
            await self._respond(
                interaction,
                "禁言失敗。",
            )
            return

        self.database.log_action(
            guild.id,
            "mute",
            member.id,
            moderator.id,
            reason_value,
            duration,
        )

        embed = self._member_action_embed(
            "禁言",
            member,
            moderator,
            reason_value,
            discord.Color.yellow(),
            extra=f"\n時長：{duration} 分鐘",
        )
        await self._finish_action(
            interaction,
            embed,
        )

        if (
            not member.bot
            and self.dm_target_on_mute
        ):
            await self._send_dm(
                member,
                discord.Embed(
                    title=(
                        f"你在 {guild.name} 被禁言"
                    ),
                    description=(
                        f"原因：{reason_value}\n"
                        f"時長：{duration} 分鐘"
                    ),
                    color=discord.Color.yellow(),
                ),
            )

    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """解除成員禁言。"""

        if error := self.can_moderate(
            interaction,
            member,
        ):
            await self._respond(
                interaction,
                error,
            )
            return

        guild = interaction.guild
        moderator = interaction.user
        assert guild is not None
        assert isinstance(moderator, discord.Member)

        try:
            await member.timeout(
                None
            )
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少解除禁言權限。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "解除禁言失敗 guild_id=%s member_id=%s",
                guild.id,
                member.id,
            )
            await self._respond(
                interaction,
                "解除禁言失敗。",
            )
            return

        self.database.log_action(
            guild.id,
            "unmute",
            member.id,
            moderator.id,
            "手動解除禁言",
        )

        embed = self._member_action_embed(
            "解除禁言",
            member,
            moderator,
            "手動解除",
            discord.Color.green(),
        )
        await self._finish_action(
            interaction,
            embed,
        )

    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        reason: str | None,
    ) -> None:
        """警告成員並保存警告紀錄。"""

        if error := self.can_moderate(
            interaction,
            member,
        ):
            await self._respond(
                interaction,
                error,
            )
            return

        guild = interaction.guild
        moderator = interaction.user
        assert guild is not None
        assert isinstance(moderator, discord.Member)

        reason_value = reason_text(reason)
        total = self.database.add_warning(
            guild.id,
            member.id,
            moderator.id,
            reason_value,
        )
        self.database.log_action(
            guild.id,
            "warn",
            member.id,
            moderator.id,
            reason_value,
        )

        embed = self._member_action_embed(
            "警告",
            member,
            moderator,
            reason_value,
            discord.Color.yellow(),
            extra=f"\n累計警告：{total} 次",
        )

        if (
            not member.bot
            and self.dm_target_on_warn
        ):
            await self._send_dm(
                member,
                discord.Embed(
                    title=(
                        f"你在 {guild.name} 收到了警告"
                    ),
                    description=(
                        f"原因：{reason_value}\n"
                        f"累計警告：{total} 次"
                    ),
                    color=discord.Color.yellow(),
                ),
            )

        await self._finish_action(
            interaction,
            embed,
        )

    # ── Records ──────────────────────

    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """顯示指定成員的警告紀錄。"""

        guild = interaction.guild
        if guild is None:
            return

        records = self.database.get_warnings(
            guild.id,
            member.id,
        )
        total = self.database.count_warnings(
            guild.id,
            member.id,
        )

        embed = discord.Embed(
            title=(
                f"{member.display_name} 的警告紀錄"
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=(
                f"累計警告：{total} 次  |  "
                f"{self.embed_footer}"
            )
        )

        if not records:
            embed.description = (
                "此成員目前無任何警告紀錄"
            )
        else:
            embed.description = "\n".join(
                (
                    f"**{index}.** "
                    f"<t:{record.created_at}:R> — "
                    f"{record.reason}"
                )
                for index, record in enumerate(
                    records,
                    start=1,
                )
            )[:4096]

        await self._respond(
            interaction,
            embed=embed,
        )

    async def clear_warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """清除指定成員的警告紀錄。"""

        guild = interaction.guild
        if guild is None:
            return

        deleted = self.database.clear_warnings(
            guild.id,
            member.id,
        )
        await self._respond(
            interaction,
            (
                f"已清除 **{member.display_name}** "
                f"的 {deleted} 筆警告。"
            ),
        )

    async def purge(
        self,
        interaction: discord.Interaction,
        amount: int,
    ) -> None:
        """批量刪除目前文字頻道訊息。"""

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await self._respond(
                interaction,
                "批量刪除僅限一般文字頻道。",
            )
            return

        if not interaction.response.is_done():
            await interaction.response.defer(
                ephemeral=True
            )

        try:
            deleted = await channel.purge(
                limit=amount
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Bot 缺少刪除訊息權限。",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.exception(
                "批量刪除失敗 guild_id=%s channel_id=%s",
                interaction.guild_id,
                interaction.channel_id,
            )
            await interaction.followup.send(
                "批量刪除訊息失敗。",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"已刪除 {len(deleted)} 則訊息。",
            ephemeral=True,
        )

    async def modlog(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """顯示最近的管理動作紀錄。"""

        guild = interaction.guild
        if guild is None:
            return

        records = self.database.get_mod_log(
            guild.id,
            limit=self.modlog_limit,
        )

        embed = discord.Embed(
            title=(
                f"管理動作紀錄（最近 {self.modlog_limit} 筆）"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=self.embed_footer
        )

        if not records:
            embed.description = (
                "目前無管理動作紀錄"
            )
        else:
            lines = []

            for record in records:
                duration = (
                    f"（{record.duration_min} 分）"
                    if record.duration_min
                    else ""
                )
                lines.append(
                    f"<t:{record.created_at}:R> "
                    f"**{record.action}** "
                    f"<@{record.user_id}>{duration} — "
                    f"{record.reason}"
                )

            embed.description = "\n".join(
                lines
            )[:4096]

        await self._respond(
            interaction,
            embed=embed,
        )

    # ── Discord Log ──────────────────────

    async def set_log_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None,
    ) -> None:
        """設定 Moderation Module 自己的 Discord 日誌頻道。"""

        guild = interaction.guild

        if guild is None:
            return

        self.database.set_log_channel_id(
            guild.id,
            channel.id if channel else 0,
        )

        await self._respond(
            interaction,
            (
                f"管理日誌頻道已設定為 {channel.mention}。"
                if channel
                else "Moderation 管理日誌頻道已停用。"
            ),
        )

    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
    ) -> None:
        """將管理動作送至 Moderation Module 自有日誌頻道。"""

        channel_id = self.database.get_log_channel_id(
            guild.id
        )

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
                "Moderation Discord 日誌發送失敗 guild_id=%s channel_id=%s",
                guild.id,
                channel.id,
            )

    # ── Output Helpers ──────────────────────

    def _member_action_embed(
        self,
        action: str,
        target: discord.Member,
        moderator: discord.Member,
        reason: str,
        color: discord.Color,
        *,
        extra: str = "",
    ) -> discord.Embed:
        """建立標準管理動作 Embed。"""

        embed = discord.Embed(
            title=f"管理動作：{action}",
            description=(
                f"目標：{target.mention}（{target}）\n"
                f"原因：{reason}{extra}"
            ),
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=(
                f"執行者：{moderator}  |  "
                f"{self.embed_footer}"
            )
        )
        embed.set_thumbnail(
            url=target.display_avatar.url
        )
        return embed

    async def _finish_action(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
    ) -> None:
        """回覆管理結果並寫入 Discord 日誌頻道。"""

        await self._respond(
            interaction,
            embed=embed,
        )

        if interaction.guild is not None:
            await self._send_log(
                interaction.guild,
                embed,
            )

    @staticmethod
    async def _send_dm(
        member: discord.Member,
        embed: discord.Embed,
    ) -> None:
        """嘗試通知目標成員，DM 失敗不影響管理動作。"""

        try:
            await member.send(
                embed=embed
            )
        except (
            discord.HTTPException,
            AttributeError,
        ):
            return

    @staticmethod
    async def _respond(
        interaction: discord.Interaction,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
    ) -> None:
        """依 Interaction 狀態選擇 Response 或 Followup。"""

        if interaction.response.is_done():
            await interaction.followup.send(
                content=content,
                embed=embed,
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            content=content,
            embed=embed,
            ephemeral=True,
        )
