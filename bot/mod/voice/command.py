"""
bot/mod/voice/command.py

Modification():

- 提供 Join to Create 臨時語音頻道建立與自動清理功能。
- 提供 /vc 語音頻道設定與管理指令。
- 提供 Slash Command 與自然語言共用的語音操作介面。
- 臨時頻道管理允許頻道擁有者或伺服器管理員執行。
- 使用 Voice Module 自有 Database 與 Settings。

本檔負責 Voice Module 的語音頻道核心操作與 Discord Command 入口。
自然語言層僅呼叫本檔公開的 execute_* 方法，不重複實作權限、
資料庫或 Discord 頻道操作。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from bot.mod.voice import database as vc_repo
from bot.mod.voice.config import get_setting as _s_get
from bot.mod.voice.confirmation import (
    guarded_action,
    missing_permissions,
    request_confirmation,
)


logger = logging.getLogger("bot.voice")


# ── Command 結果 ──────────────────────

@dataclass(frozen=True, slots=True)
class VoiceCommandResult:
    """Voice Command 共用執行結果。"""

    success: bool
    message: str


# ── 工具函式 ──────────────────────

def _render_name(
    template: str,
    member: discord.Member,
) -> str:
    """將名稱範本中的佔位符替換為實際資料。"""

    return (
        template
        .replace("{username}", member.display_name)
        .replace("{name}", member.display_name)
        .replace("{guild}", member.guild.name)
    )


async def _get_channel_owner(
    channel: discord.VoiceChannel,
) -> str | None:
    """從 Voice DB 取得臨時頻道擁有者 ID。"""

    data = await vc_repo.get_channel(channel.id)

    if data is None:
        return None

    return data["owner_id"]


# ── Cog ──────────────────────

class VoiceChannel(commands.Cog):
    """Join to Create 臨時語音頻道系統。"""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    # ── 重啟清理 ──────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        Bot 啟動後掃描 Voice DB。

        已不存在或已空的臨時頻道會從 Discord 與 DB 清除。
        """

        cleaned = 0

        for guild in self.bot.guilds:
            entries = await vc_repo.get_all_channels(
                guild.id
            )

            for entry in entries:
                channel = guild.get_channel(
                    entry["channel_id"]
                )

                if channel is None:
                    await vc_repo.delete_channel(
                        entry["channel_id"]
                    )
                    cleaned += 1
                    continue

                if not isinstance(
                    channel,
                    discord.VoiceChannel,
                ):
                    continue

                if channel.members:
                    continue

                try:
                    await channel.delete(
                        reason="Bot 重啟後清理空的臨時頻道"
                    )

                except discord.HTTPException as exc:
                    logger.debug("[voice.cleanup] 頻道刪除失敗 channel=%s error=%s", channel.id, exc)

                await vc_repo.delete_channel(
                    channel.id
                )

                cleaned += 1

        if cleaned:
            logger.info(
                "[voice] 重啟後清理了 %d 個殭屍臨時頻道",
                cleaned,
            )

    # ── 語音狀態事件 ──────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """
        處理 JTC 建立與臨時頻道自動清理。
        """

        guild = member.guild

        if isinstance(
            after.channel,
            discord.VoiceChannel,
        ):
            await self._handle_join(
                member,
                after.channel,
                guild,
            )

        if (
            isinstance(
                before.channel,
                discord.VoiceChannel,
            )
            and before.channel != after.channel
        ):
            await self._handle_leave(
                before.channel,
                guild,
            )

    # ── JTC 建立 ──────────────────────

    async def _handle_join(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel,
        guild: discord.Guild,
    ) -> discord.VoiceChannel | None:
        """
        若成員進入 JTC 觸發頻道，建立專屬臨時頻道。

        回傳建立完成的 VoiceChannel。
        非 JTC 頻道或建立失敗時回傳 None。
        """

        settings = await vc_repo.get_vc_settings(
            guild.id
        )

        create_id = (
            settings.get("create_channel", 0)
            or int(
                _s_get(
                    "voice_channel.jtc_channel_id",
                    0,
                )
            )
        )

        if not create_id:
            return None

        if channel.id != create_id:
            return None

        category_id = (
            settings.get("category_id", 0)
            or int(
                _s_get(
                    "voice_channel.category_id",
                    0,
                )
            )
        )

        category = (
            guild.get_channel(category_id)
            if category_id
            else channel.category
        )

        template = (
            settings.get("name_template")
            or _s_get(
                "voice_channel.default_name_template",
                "{username} 的頻道",
            )
        )

        channel_name = _render_name(
            template,
            member,
        )

        user_limit = (
            settings.get("default_limit", 0)
            or int(
                _s_get(
                    "voice_channel.default_limit",
                    0,
                )
            )
        )

        try:
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,  # type: ignore[arg-type]
                user_limit=user_limit,
                position=channel.position + 1,
                reason=f"JTC：{member} 建立的臨時頻道",
            )

        except discord.Forbidden:
            logger.warning(
                "[voice.create] guild=%s "
                "member=%s missing_permission",
                guild.id,
                member.id,
            )
            return None

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.create] guild=%s "
                "member=%s error=%s",
                guild.id,
                member.id,
                exc,
            )
            return None

        try:
            await new_channel.set_permissions(
                member,
                connect=True,
                speak=True,
                manage_channels=False,
                move_members=True,
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.create] channel=%s "
                "owner_permission_error=%s",
                new_channel.id,
                exc,
            )

        await vc_repo.create_channel(
            channel_id=new_channel.id,
            guild_id=guild.id,
            owner_id=str(member.id),
            name=channel_name,
            user_limit=user_limit,
        )

        try:
            await member.move_to(
                new_channel,
                reason="JTC：移入臨時頻道",
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.create] member=%s "
                "move_error=%s",
                member.id,
                exc,
            )

            await asyncio.sleep(0.5)

            if not new_channel.members:
                try:
                    await new_channel.delete(
                        reason="JTC 建立後無法移入成員"
                    )
                except discord.HTTPException as exc:
                    logger.debug("[voice.cleanup] 頻道刪除失敗 channel=%s error=%s", channel.id, exc)

                await vc_repo.delete_channel(
                    new_channel.id
                )

            return None

        logger.info(
            "[voice.create] guild=%s "
            "channel=%s owner=%s",
            guild.id,
            new_channel.id,
            member.id,
        )

        return new_channel

    # ── JTC 清理 ──────────────────────

    async def _handle_leave(
        self,
        channel: discord.VoiceChannel,
        guild: discord.Guild,
    ) -> None:
        """臨時頻道清空後刪除頻道與 DB 紀錄。"""

        if not await vc_repo.is_temp_channel(
            channel.id
        ):
            return

        if channel.members:
            return

        try:
            await channel.delete(
                reason="臨時語音頻道已空，自動刪除"
            )

        except discord.NotFound:
            logger.debug("[voice.delete] 頻道已不存在 channel=%s", channel.id)

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.delete] guild=%s "
                "channel=%s error=%s",
                guild.id,
                channel.id,
                exc,
            )
            return

        await vc_repo.delete_channel(
            channel.id
        )

        logger.info(
            "[voice.delete] guild=%s channel=%s",
            guild.id,
            channel.id,
        )

    # ── 共用頻道驗證 ──────────────────────

    async def _get_manageable_channel(
        self,
        member: discord.Member,
    ) -> discord.VoiceChannel | None:
        """
        取得成員目前可管理的臨時語音頻道。

        頻道擁有者與具有 Administrator 權限的管理員
        均可管理臨時語音頻道。
        """

        if (
            member.voice is None
            or member.voice.channel is None
        ):
            return None

        channel = member.voice.channel

        if not isinstance(
            channel,
            discord.VoiceChannel,
        ):
            return None

        owner_id = await _get_channel_owner(
            channel
        )

        if owner_id is None:
            return None

        is_owner = owner_id == str(member.id)

        is_admin = (
            member.guild_permissions.administrator
        )

        if not is_owner and not is_admin:
            return None

        return channel

    # ── 共用建立 Command ──────────────────────

    async def execute_create(
        self,
        member: discord.Member,
    ) -> VoiceCommandResult:
        """
        使用目前 JTC 設定建立臨時語音頻道。

        Slash 與 Natural 若需要主動建立頻道，
        均應使用此方法。
        """

        if (
            member.voice is None
            or member.voice.channel is None
        ):
            return VoiceCommandResult(
                success=False,
                message="請先加入已設定的「建立語音」頻道",
            )

        channel = member.voice.channel

        if not isinstance(
            channel,
            discord.VoiceChannel,
        ):
            return VoiceCommandResult(
                success=False,
                message="請先加入已設定的「建立語音」頻道",
            )

        settings = await vc_repo.get_vc_settings(
            member.guild.id
        )

        create_id = (
            settings.get("create_channel", 0)
            or int(
                _s_get(
                    "voice_channel.jtc_channel_id",
                    0,
                )
            )
        )

        if not create_id:
            return VoiceCommandResult(
                success=False,
                message="此伺服器尚未設定建立語音頻道",
            )

        if channel.id != create_id:
            return VoiceCommandResult(
                success=False,
                message="請先加入已設定的「建立語音」頻道",
            )

        created_channel = await self._handle_join(
            member,
            channel,
            member.guild,
        )

        if created_channel is None:
            return VoiceCommandResult(
                success=False,
                message="建立語音頻道失敗",
            )

        return VoiceCommandResult(
            success=True,
            message=f"已建立語音頻道 **{created_channel.name}**",
        )

    # ── 共用名稱 Command ──────────────────────

    async def execute_name(
        self,
        member: discord.Member,
        name: str,
    ) -> VoiceCommandResult:
        """修改目前臨時語音頻道名稱。"""

        channel = await self._get_manageable_channel(
            member
        )

        if channel is None:
            return VoiceCommandResult(
                success=False,
                message="您目前沒有可管理的臨時語音頻道",
            )

        name = name.strip()

        if not name:
            return VoiceCommandResult(
                success=False,
                message="語音頻道名稱不能為空",
            )

        if len(name) > 100:
            return VoiceCommandResult(
                success=False,
                message="語音頻道名稱不能超過 100 個字元",
            )

        try:
            await channel.edit(
                name=name,
                reason=f"{member} 更名臨時頻道",
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.name] channel=%s "
                "member=%s error=%s",
                channel.id,
                member.id,
                exc,
            )

            return VoiceCommandResult(
                success=False,
                message=f"更名失敗：{exc}",
            )

        await vc_repo.update_channel(
            channel.id,
            "name",
            name,
        )

        return VoiceCommandResult(
            success=True,
            message=f"頻道已更名為 **{name}**",
        )

    # ── 共用上限 Command ──────────────────────

    async def execute_limit(
        self,
        member: discord.Member,
        limit: int,
    ) -> VoiceCommandResult:
        """修改目前臨時語音頻道人數上限。"""

        channel = await self._get_manageable_channel(
            member
        )

        if channel is None:
            return VoiceCommandResult(
                success=False,
                message="您目前沒有可管理的臨時語音頻道",
            )

        if not 0 <= limit <= 99:
            return VoiceCommandResult(
                success=False,
                message="語音上限必須介於 0 到 99",
            )

        try:
            await channel.edit(
                user_limit=limit,
                reason=f"{member} 修改臨時頻道人數上限",
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.limit] channel=%s "
                "member=%s error=%s",
                channel.id,
                member.id,
                exc,
            )

            return VoiceCommandResult(
                success=False,
                message=f"設定失敗：{exc}",
            )

        await vc_repo.update_channel(
            channel.id,
            "user_limit",
            limit,
        )

        if limit == 0:
            message = "人數上限已取消（無上限）"
        else:
            message = f"人數上限已設為 **{limit}**"

        return VoiceCommandResult(
            success=True,
            message=message,
        )

    # ── 共用鎖定 Command ──────────────────────

    async def execute_lock(
        self,
        member: discord.Member,
    ) -> VoiceCommandResult:
        """鎖定目前臨時語音頻道。"""

        channel = await self._get_manageable_channel(
            member
        )

        if channel is None:
            return VoiceCommandResult(
                success=False,
                message="您目前沒有可管理的臨時語音頻道",
            )

        try:
            await channel.set_permissions(
                member.guild.default_role,
                connect=False,
                reason=f"{member} 鎖定臨時語音頻道",
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.lock] channel=%s "
                "member=%s error=%s",
                channel.id,
                member.id,
                exc,
            )

            return VoiceCommandResult(
                success=False,
                message=f"鎖定失敗：{exc}",
            )

        await vc_repo.update_channel(
            channel.id,
            "is_locked",
            1,
        )

        return VoiceCommandResult(
            success=True,
            message="頻道已鎖定，新成員無法進入",
        )

    # ── 共用解鎖 Command ──────────────────────

    async def execute_unlock(
        self,
        member: discord.Member,
    ) -> VoiceCommandResult:
        """解鎖目前臨時語音頻道。"""

        channel = await self._get_manageable_channel(
            member
        )

        if channel is None:
            return VoiceCommandResult(
                success=False,
                message="您目前沒有可管理的臨時語音頻道",
            )

        try:
            await channel.set_permissions(
                member.guild.default_role,
                connect=None,
                reason=f"{member} 解鎖臨時語音頻道",
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.unlock] channel=%s "
                "member=%s error=%s",
                channel.id,
                member.id,
                exc,
            )

            return VoiceCommandResult(
                success=False,
                message=f"解鎖失敗：{exc}",
            )

        await vc_repo.update_channel(
            channel.id,
            "is_locked",
            0,
        )

        return VoiceCommandResult(
            success=True,
            message="頻道已解鎖",
        )

    # ── /vc ──────────────────────

    @app_commands.command(
        name="vc",
        description="臨時語音頻道設定與管理",
    )
    @app_commands.describe(
        action="要執行的語音頻道操作",
        channel="設定觸發器或強制刪除的語音頻道",
        category="臨時頻道所屬類別",
        template="建立臨時頻道時的名稱範本",
        limit="頻道人數上限（0 表示無上限）",
        name="新的臨時頻道名稱",
        member="允許、拒絕、踢出或轉移的目標成員",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="設定加入即建立",
                value="setup",
            ),
            app_commands.Choice(
                name="變更頻道名稱",
                value="name",
            ),
            app_commands.Choice(
                name="設定人數上限",
                value="limit",
            ),
            app_commands.Choice(
                name="鎖定頻道",
                value="lock",
            ),
            app_commands.Choice(
                name="解鎖頻道",
                value="unlock",
            ),
            app_commands.Choice(
                name="允許成員",
                value="permit",
            ),
            app_commands.Choice(
                name="拒絕成員",
                value="reject",
            ),
            app_commands.Choice(
                name="踢出成員",
                value="kick",
            ),
            app_commands.Choice(
                name="轉移所有權",
                value="transfer",
            ),
            app_commands.Choice(
                name="查看頻道資訊",
                value="info",
            ),
            app_commands.Choice(
                name="管理員強制刪除",
                value="forcedelete",
            ),
        ]
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    async def cmd_vc(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        channel: discord.VoiceChannel | None = None,
        category: discord.CategoryChannel | None = None,
        template: app_commands.Range[
            str,
            1,
            100,
        ] = "{username} 的頻道",
        limit: app_commands.Range[
            int,
            0,
            99,
        ] | None = None,
        name: app_commands.Range[
            str,
            1,
            100,
        ] | None = None,
        member: discord.Member | None = None,
    ) -> None:
        value = action.value

        if value == "info":
            await self.cmd_info(
                interaction
            )
            return

        if value in {
            "setup",
            "forcedelete",
        }:
            bot_permissions = (
                (
                    "manage_channels",
                    "move_members",
                )
                if value == "setup"
                else ("manage_channels",)
            )

            error = missing_permissions(
                interaction,
                user=("administrator",),
                bot=bot_permissions,
            )

            if error:
                await interaction.response.send_message(
                    error,
                    ephemeral=True,
                )
                return

            if channel is None:
                await interaction.response.send_message(
                    "此操作必須選擇語音頻道。",
                    ephemeral=True,
                )
                return

            if value == "setup":
                await request_confirmation(
                    interaction,
                    title="確認設定加入即建立頻道",
                    description=(
                        f"觸發頻道：**{channel.name}**\n"
                        f"名稱範本：`{template}`"
                    ),
                    action=guarded_action(
                        lambda click: self.cmd_setup(
                            click,
                            channel,
                            category,
                            template,
                            limit or 0,
                        ),
                        user=("administrator",),
                        bot=bot_permissions,
                    ),
                )
                return

            await request_confirmation(
                interaction,
                title="確認強制刪除臨時頻道",
                description=(
                    f"將永久刪除 **{channel.name}**，"
                    "並移除資料庫紀錄。"
                ),
                action=guarded_action(
                    lambda click: self.cmd_forcedelete(
                        click,
                        channel,
                    ),
                    user=("administrator",),
                    bot=bot_permissions,
                ),
            )
            return

        if value == "name":
            if name is None:
                await interaction.response.send_message(
                    "更名時必須填寫新名稱。",
                    ephemeral=True,
                )
                return

            await self.cmd_name(
                interaction,
                name,
            )
            return

        if value == "limit":
            if limit is None:
                await interaction.response.send_message(
                    "設定上限時必須填寫 limit。",
                    ephemeral=True,
                )
                return

            await self.cmd_limit(
                interaction,
                limit,
            )
            return

        no_target = {
            "lock": self.cmd_lock,
            "unlock": self.cmd_unlock,
        }

        if value in no_target:
            await request_confirmation(
                interaction,
                title=(
                    "確認鎖定頻道"
                    if value == "lock"
                    else "確認解鎖頻道"
                ),
                description="將修改目前臨時語音頻道的連線權限。",
                action=no_target[value],
            )
            return

        if member is None:
            await interaction.response.send_message(
                "此操作必須選擇目標成員。",
                ephemeral=True,
            )
            return

        callbacks = {
            "permit": self.cmd_permit,
            "reject": self.cmd_reject,
            "kick": self.cmd_kick,
            "transfer": self.cmd_transfer,
        }

        titles = {
            "permit": "確認允許成員",
            "reject": "確認拒絕成員",
            "kick": "確認踢出成員",
            "transfer": "確認轉移所有權",
        }

        callback = callbacks.get(value)

        if callback is None:
            await interaction.response.send_message(
                "未知的語音頻道操作。",
                ephemeral=True,
            )
            return

        await request_confirmation(
            interaction,
            title=titles[value],
            description=f"目標成員：{member.mention}",
            action=lambda click: callback(
                click,
                member,
            ),
        )

    # ── /vc setup ──────────────────────

    async def cmd_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        category: discord.CategoryChannel | None = None,
        template: str = "{username} 的頻道",
        limit: app_commands.Range[
            int,
            0,
            99,
        ] = 0,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        await vc_repo.set_vc_setting(
            guild.id,
            "create_channel",
            channel.id,
        )

        await vc_repo.set_vc_setting(
            guild.id,
            "category_id",
            category.id if category else 0,
        )

        await vc_repo.set_vc_setting(
            guild.id,
            "name_template",
            template,
        )

        await vc_repo.set_vc_setting(
            guild.id,
            "default_limit",
            int(limit),
        )

        description = [
            f"觸發頻道：**{channel.name}**",
            (
                "類別："
                f"{category.name if category else '（與觸發頻道相同）'}"
            ),
            f"名稱範本：`{template}`",
            (
                "預設人數上限："
                f"{'無上限' if limit == 0 else str(limit)}"
            ),
        ]

        embed = discord.Embed(
            title="JTC 語音頻道已設定",
            description="\n".join(
                description
            ),
            color=discord.Color.green(),
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

        logger.info(
            "[voice.setup] guild=%s "
            "channel=%s template=%r limit=%d",
            guild.id,
            channel.id,
            template,
            limit,
        )

    # ── /vc name ──────────────────────

    async def cmd_name(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[
            str,
            1,
            100,
        ],
    ) -> None:
        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        result = await self.execute_name(
            member,
            str(name),
        )

        await interaction.response.send_message(
            result.message,
            ephemeral=True,
        )

    # ── /vc limit ──────────────────────

    async def cmd_limit(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[
            int,
            0,
            99,
        ],
    ) -> None:
        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        result = await self.execute_limit(
            member,
            int(limit),
        )

        await interaction.response.send_message(
            result.message,
            ephemeral=True,
        )

    # ── /vc lock ──────────────────────

    async def cmd_lock(
        self,
        interaction: discord.Interaction,
    ) -> None:
        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        result = await self.execute_lock(
            member
        )

        await interaction.response.send_message(
            result.message,
            ephemeral=True,
        )

    # ── /vc unlock ──────────────────────

    async def cmd_unlock(
        self,
        interaction: discord.Interaction,
    ) -> None:
        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        result = await self.execute_unlock(
            member
        )

        await interaction.response.send_message(
            result.message,
            ephemeral=True,
        )

    # ── /vc permit ──────────────────────

    async def cmd_permit(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        actor = interaction.user

        if not isinstance(
            actor,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        channel = await self._get_manageable_channel(
            actor
        )

        if channel is None:
            await interaction.response.send_message(
                "您目前沒有可管理的臨時語音頻道",
                ephemeral=True,
            )
            return

        try:
            await channel.set_permissions(
                member,
                connect=True,
            )

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"設定失敗：{exc}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"已允許 {member.mention} 進入此頻道",
            ephemeral=True,
        )

    # ── /vc reject ──────────────────────

    async def cmd_reject(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        actor = interaction.user

        if not isinstance(
            actor,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        channel = await self._get_manageable_channel(
            actor
        )

        if channel is None:
            await interaction.response.send_message(
                "您目前沒有可管理的臨時語音頻道",
                ephemeral=True,
            )
            return

        if member == actor:
            await interaction.response.send_message(
                "不能禁止自己進入",
                ephemeral=True,
            )
            return

        try:
            await channel.set_permissions(
                member,
                connect=False,
            )

            if member in channel.members:
                await member.move_to(
                    None,
                    reason=f"{actor} 從臨時頻道移除",
                )

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"設定失敗：{exc}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"已禁止 {member.mention} 進入此頻道",
            ephemeral=True,
        )

    # ── /vc kick ──────────────────────

    async def cmd_kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        actor = interaction.user

        if not isinstance(
            actor,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        channel = await self._get_manageable_channel(
            actor
        )

        if channel is None:
            await interaction.response.send_message(
                "您目前沒有可管理的臨時語音頻道",
                ephemeral=True,
            )
            return

        if member == actor:
            await interaction.response.send_message(
                "不能踢出自己",
                ephemeral=True,
            )
            return

        if member not in channel.members:
            await interaction.response.send_message(
                f"{member.display_name} 不在此頻道中",
                ephemeral=True,
            )
            return

        try:
            await member.move_to(
                None,
                reason=f"{actor} 踢出臨時頻道成員",
            )

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"踢出失敗：{exc}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"已將 {member.display_name} 踢出頻道",
            ephemeral=True,
        )

    # ── /vc transfer ──────────────────────

    async def cmd_transfer(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        actor = interaction.user

        if not isinstance(
            actor,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        channel = await self._get_manageable_channel(
            actor
        )

        if channel is None:
            await interaction.response.send_message(
                "您目前沒有可管理的臨時語音頻道",
                ephemeral=True,
            )
            return

        owner_id = await _get_channel_owner(
            channel
        )

        if owner_id == str(member.id):
            await interaction.response.send_message(
                "該成員已經是此頻道的擁有者",
                ephemeral=True,
            )
            return

        if member not in channel.members:
            await interaction.response.send_message(
                f"{member.display_name} 不在此頻道中，無法轉移",
                ephemeral=True,
            )
            return

        await vc_repo.update_channel(
            channel.id,
            "owner_id",
            str(member.id),
        )

        old_owner = (
            interaction.guild.get_member(
                int(owner_id)
            )
            if interaction.guild is not None
            and owner_id is not None
            else None
        )

        try:
            if old_owner is not None:
                await channel.set_permissions(
                    old_owner,
                    overwrite=None,
                )

            await channel.set_permissions(
                member,
                connect=True,
                move_members=True,
            )

        except discord.HTTPException as exc:
            logger.warning(
                "[voice.transfer] channel=%s "
                "permission_error=%s",
                channel.id,
                exc,
            )

        await interaction.response.send_message(
            f"已將頻道所有權轉移給 {member.mention}",
            ephemeral=True,
        )

        logger.info(
            "[voice.transfer] channel=%s "
            "from=%s to=%s",
            channel.id,
            owner_id,
            member.id,
        )

    # ── /vc info ──────────────────────

    async def cmd_info(
        self,
        interaction: discord.Interaction,
    ) -> None:
        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "此指令僅限伺服器使用",
                ephemeral=True,
            )
            return

        if (
            member.voice is None
            or member.voice.channel is None
        ):
            await interaction.response.send_message(
                "請先加入語音頻道",
                ephemeral=True,
            )
            return

        channel = member.voice.channel

        if not isinstance(
            channel,
            discord.VoiceChannel,
        ):
            await interaction.response.send_message(
                "此功能僅適用於語音頻道",
                ephemeral=True,
            )
            return

        data = await vc_repo.get_channel(
            channel.id
        )

        if data is None:
            await interaction.response.send_message(
                "此頻道不是臨時頻道",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "無法取得伺服器資訊",
                ephemeral=True,
            )
            return

        owner = guild.get_member(
            int(data["owner_id"])
        )

        owner_display = (
            owner.mention
            if owner is not None
            else f"ID: {data['owner_id']}"
        )

        embed = discord.Embed(
            title=f"語音頻道：{channel.name}",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name="擁有者",
            value=owner_display,
            inline=True,
        )

        embed.add_field(
            name="人數上限",
            value=(
                str(data["user_limit"])
                if data["user_limit"]
                else "無上限"
            ),
            inline=True,
        )

        embed.add_field(
            name="鎖定狀態",
            value=(
                "已鎖定"
                if data["is_locked"]
                else "開放"
            ),
            inline=True,
        )

        embed.add_field(
            name="目前人數",
            value=f"{len(channel.members)} 人",
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # ── /vc forcedelete ──────────────────────

    async def cmd_forcedelete(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ) -> None:
        if not await vc_repo.is_temp_channel(
            channel.id
        ):
            await interaction.response.send_message(
                "此頻道不是臨時頻道",
                ephemeral=True,
            )
            return

        try:
            await channel.delete(
                reason=(
                    f"管理員 {interaction.user} "
                    "強制刪除"
                )
            )

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"刪除失敗：{exc}",
                ephemeral=True,
            )
            return

        await vc_repo.delete_channel(
            channel.id
        )

        await interaction.response.send_message(
            f"已強制刪除臨時頻道 **{channel.name}**",
            ephemeral=True,
        )