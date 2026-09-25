"""
bot/mod/moderation/command.py

Modification():

- 提供 /mod Slash Command 作為 Moderation Module 的單一入口。
- 提供封禁、解封、踢出、禁言、警告、清除與紀錄查詢操作介面。
- 對所有會改變狀態的管理操作執行二次確認。
- 在執行與確認階段重新驗證使用者及 Bot 權限。
- 提供 Moderation Module 自有日誌頻道設定介面。

本檔只負責 Moderation Module 的 Discord Command 與互動元件。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from bot.mod.moderation.config import (
    MAX_BAN_DELETE_DAYS,
    MAX_PURGE_AMOUNT,
    MAX_REASON_LENGTH,
)
from bot.mod.moderation.service import (
    ModerationService,
    reason_text,
)


ConfirmedAction = Callable[
    [discord.Interaction],
    Awaitable[None],
]


# ── Permission Helpers ──────────────────────

USER_PERMISSIONS: dict[
    str,
    tuple[str, ...],
] = {
    "ban": ("ban_members",),
    "unban": ("ban_members",),
    "kick": ("kick_members",),
    "mute": ("moderate_members",),
    "unmute": ("moderate_members",),
    "warn": ("moderate_members",),
    "warnings": ("moderate_members",),
    "clear_warns": ("administrator",),
    "purge": ("manage_messages",),
    "modlog": ("moderate_members",),
    "log_channel": ("administrator",),
}

BOT_PERMISSIONS: dict[
    str,
    tuple[str, ...],
] = {
    "ban": ("ban_members",),
    "unban": ("ban_members",),
    "kick": ("kick_members",),
    "mute": ("moderate_members",),
    "unmute": ("moderate_members",),
    "purge": (
        "manage_messages",
        "read_message_history",
    ),
}


# ── Moderation Cog ──────────────────────

class ModerationCog(commands.Cog):
    """提供 /mod 管理面板。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: ModerationService,
        panel_timeout_seconds: int,
        member_selection_timeout_seconds: int,
        confirmation_timeout_seconds: int,
    ) -> None:
        self.bot = bot
        self.service = service
        self.panel_timeout_seconds = panel_timeout_seconds
        self.member_selection_timeout_seconds = (
            member_selection_timeout_seconds
        )
        self.confirmation_timeout_seconds = (
            confirmation_timeout_seconds
        )

    # ── Commands ──────────────────────

    @app_commands.command(
        name="mod",
        description="開啟伺服器管理面板",
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    async def moderation(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟 Moderation Module 管理面板。"""

        embed = discord.Embed(
            title="伺服器管理面板",
            description=(
                "請從下方選單選擇管理操作。\n"
                "需要成員的操作會再顯示成員選擇器。"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=ModerationView(
                cog=self,
                user_id=interaction.user.id,
                timeout=self.panel_timeout_seconds,
            ),
            ephemeral=True,
        )

    # ── Dispatch ──────────────────────

    async def dispatch(
        self,
        interaction: discord.Interaction,
        action: str,
        *,
        member: discord.Member | None = None,
        user_id: str | None = None,
        reason: str | None = None,
        minutes: int = 0,
        delete_days: int = 0,
        amount: int = 10,
    ) -> None:
        """驗證操作權限並執行查詢或建立確認介面。"""

        if not await self.check_permissions(
            interaction,
            action,
        ):
            return

        if action == "warnings":
            if member is None:
                await self._error(
                    interaction,
                    "查看警告時必須選擇目標成員。",
                )
                return

            await self.service.warnings(
                interaction,
                member,
            )
            return

        if action == "modlog":
            await self.service.modlog(
                interaction
            )
            return

        if action == "log_channel":
            await interaction.response.send_message(
                "請選擇 Moderation 管理日誌頻道：",
                view=LogChannelView(
                    cog=self,
                    user_id=interaction.user.id,
                    timeout=self.member_selection_timeout_seconds,
                ),
                ephemeral=True,
            )
            return

        if action == "unban":
            if not user_id:
                await self._error(
                    interaction,
                    "解除封禁時必須填寫使用者 ID。",
                )
                return

            async def execute(
                click: discord.Interaction,
            ) -> None:
                await self.service.unban(
                    click,
                    user_id,
                )

            target = (
                f"使用者 ID `{user_id}`"
            )

        elif action == "purge":
            async def execute(
                click: discord.Interaction,
            ) -> None:
                await self.service.purge(
                    click,
                    amount,
                )

            target = (
                f"目前頻道最近 **{amount}** 則訊息"
            )

        else:
            if member is None:
                await self._error(
                    interaction,
                    "此操作必須選擇目標成員。",
                )
                return

            async def execute(
                click: discord.Interaction,
            ) -> None:
                if action == "ban":
                    await self.service.ban(
                        click,
                        member,
                        reason=reason,
                        delete_days=delete_days,
                    )
                elif action == "kick":
                    await self.service.kick(
                        click,
                        member,
                        reason=reason,
                    )
                elif action == "mute":
                    await self.service.mute(
                        click,
                        member,
                        minutes=minutes,
                        reason=reason,
                    )
                elif action == "unmute":
                    await self.service.unmute(
                        click,
                        member,
                    )
                elif action == "warn":
                    await self.service.warn(
                        click,
                        member,
                        reason=reason,
                    )
                elif action == "clear_warns":
                    await self.service.clear_warnings(
                        click,
                        member,
                    )

            target = member.mention

        labels = {
            "ban": "封禁",
            "unban": "解除封禁",
            "kick": "踢出",
            "mute": "禁言",
            "unmute": "解除禁言",
            "warn": "警告",
            "clear_warns": "清除全部警告",
            "purge": "批量刪除訊息",
        }

        await interaction.response.send_message(
            embed=discord.Embed(
                title=(
                    f"確認{labels[action]}"
                ),
                description=(
                    f"目標：{target}\n"
                    f"原因：{reason_text(reason)}\n"
                    "此操作將被記錄。"
                ),
                color=discord.Color.orange(),
            ),
            view=ConfirmationView(
                cog=self,
                action_name=action,
                user_id=interaction.user.id,
                action=execute,
                timeout=self.confirmation_timeout_seconds,
            ),
            ephemeral=True,
        )

    # ── Permissions ──────────────────────

    async def check_permissions(
        self,
        interaction: discord.Interaction,
        action: str,
    ) -> bool:
        """驗證目前操作的使用者與 Bot 權限。"""

        guild = interaction.guild
        member = interaction.user

        if (
            guild is None
            or not isinstance(
                member,
                discord.Member,
            )
        ):
            await self._error(
                interaction,
                "此功能只限伺服器成員使用。",
            )
            return False

        user_permissions = USER_PERMISSIONS[
            action
        ]

        for permission in user_permissions:
            if not getattr(
                member.guild_permissions,
                permission,
                False,
            ):
                await self._error(
                    interaction,
                    f"你缺少 `{permission}` 權限。",
                )
                return False

        bot_member = guild.me

        if bot_member is None:
            await self._error(
                interaction,
                "無法取得 Bot 的伺服器權限。",
            )
            return False

        bot_permissions = (
            guild.me.guild_permissions
        )

        for permission in BOT_PERMISSIONS.get(
            action,
            (),
        ):
            if not getattr(
                bot_permissions,
                permission,
                False,
            ):
                await self._error(
                    interaction,
                    f"Bot 缺少 `{permission}` 權限。",
                )
                return False

        return True

    @staticmethod
    async def _error(
        interaction: discord.Interaction,
        content: str,
    ) -> None:
        """回覆權限或輸入錯誤。"""

        if interaction.response.is_done():
            await interaction.followup.send(
                content,
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            content,
            ephemeral=True,
        )


# ── Main Panel ──────────────────────

class ModerationActionSelect(discord.ui.Select):
    """選擇管理操作。"""

    def __init__(
        self,
        cog: ModerationCog,
    ) -> None:
        self.cog = cog

        super().__init__(
            placeholder="選擇管理操作",
            options=[
                discord.SelectOption(label="封禁成員", value="ban"),
                discord.SelectOption(label="解除封禁", value="unban"),
                discord.SelectOption(label="踢出成員", value="kick"),
                discord.SelectOption(label="禁言成員", value="mute"),
                discord.SelectOption(label="解除禁言", value="unmute"),
                discord.SelectOption(label="警告成員", value="warn"),
                discord.SelectOption(label="查看警告", value="warnings"),
                discord.SelectOption(label="清除警告", value="clear_warns"),
                discord.SelectOption(label="批量刪除訊息", value="purge"),
                discord.SelectOption(label="查看管理紀錄", value="modlog"),
                discord.SelectOption(label="設定管理日誌頻道", value="log_channel"),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """依操作類型開啟下一步介面。"""

        action = self.values[0]

        if action in {
            "modlog",
            "log_channel",
        }:
            await self.cog.dispatch(
                interaction,
                action,
            )
            return

        if action in {
            "unban",
            "purge",
        }:
            if not await self.cog.check_permissions(
                interaction,
                action,
            ):
                return

            await interaction.response.send_modal(
                ModerationInputModal(
                    self.cog,
                    action,
                )
            )
            return

        if not await self.cog.check_permissions(
            interaction,
            action,
        ):
            return

        await interaction.response.send_message(
            "請選擇目標成員：",
            view=ModerationMemberView(
                cog=self.cog,
                action=action,
                user_id=interaction.user.id,
                timeout=self.cog.member_selection_timeout_seconds,
            ),
            ephemeral=True,
        )


class ModerationView(discord.ui.View):
    """限制只有 /mod 發起者可以操作。"""

    def __init__(
        self,
        *,
        cog: ModerationCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.user_id = user_id
        self.add_item(
            ModerationActionSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作管理面板。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的管理面板。",
            ephemeral=True,
        )
        return False


# ── Member Selection ──────────────────────

class ModerationMemberSelect(discord.ui.UserSelect):
    """選擇管理目標成員。"""

    def __init__(
        self,
        cog: ModerationCog,
        action: str,
    ) -> None:
        super().__init__(
            placeholder="選擇一位成員",
            min_values=1,
            max_values=1,
        )
        self.cog = cog
        self.action = action

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """取得 Guild Member 後繼續管理流程。"""

        guild = interaction.guild

        if guild is None:
            return

        selected = self.values[0]
        member = guild.get_member(
            selected.id
        )

        if member is None:
            await interaction.response.send_message(
                "找不到這位伺服器成員。",
                ephemeral=True,
            )
            return

        if self.action in {
            "warnings",
            "unmute",
            "clear_warns",
        }:
            await self.cog.dispatch(
                interaction,
                self.action,
                member=member,
            )
            return

        await interaction.response.send_modal(
            ModerationInputModal(
                self.cog,
                self.action,
                member,
            )
        )


class ModerationMemberView(discord.ui.View):
    """限制只有原管理面板使用者可以選擇成員。"""

    def __init__(
        self,
        *,
        cog: ModerationCog,
        action: str,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.user_id = user_id
        self.add_item(
            ModerationMemberSelect(
                cog,
                action,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作成員選擇器。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的管理面板。",
            ephemeral=True,
        )
        return False


# ── Input Modal ──────────────────────

class ModerationInputModal(discord.ui.Modal):
    """收集管理操作的原因與數值參數。"""

    def __init__(
        self,
        cog: ModerationCog,
        action: str,
        member: discord.Member | None = None,
    ) -> None:
        labels = {
            "ban": "封禁成員",
            "unban": "解除封禁",
            "kick": "踢出成員",
            "mute": "禁言成員",
            "warn": "警告成員",
            "purge": "批量刪除訊息",
        }

        super().__init__(
            title=labels[action]
        )

        self.cog = cog
        self.action = action
        self.member = member
        self.reason: discord.ui.TextInput | None = None
        self.number: discord.ui.TextInput | None = None

        if action == "unban":
            self.number = discord.ui.TextInput(
                label="使用者 ID",
                placeholder="123456789012345678",
                max_length=20,
            )
            self.add_item(
                self.number
            )
            return

        if action == "purge":
            self.number = discord.ui.TextInput(
                label="刪除數量（1-100）",
                default="10",
                max_length=3,
            )
            self.add_item(
                self.number
            )
            return

        self.reason = discord.ui.TextInput(
            label="原因（選填）",
            required=False,
            max_length=MAX_REASON_LENGTH,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(
            self.reason
        )

        if action == "mute":
            self.number = discord.ui.TextInput(
                label="禁言分鐘數",
                default=str(
                    cog.service.default_mute_minutes
                ),
                max_length=5,
            )
            self.add_item(
                self.number
            )
        elif action == "ban":
            self.number = discord.ui.TextInput(
                label="刪除訊息天數（0-7）",
                default="0",
                max_length=1,
            )
            self.add_item(
                self.number
            )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """驗證 Modal 輸入後交由 Cog Dispatch。"""

        raw_number = (
            str(self.number.value).strip()
            if self.number
            else ""
        )

        try:
            if self.action == "unban":
                if not raw_number.isdigit():
                    raise ValueError

                await self.cog.dispatch(
                    interaction,
                    self.action,
                    user_id=raw_number,
                )
                return

            if self.action == "purge":
                amount = int(
                    raw_number
                )

                if not 1 <= amount <= MAX_PURGE_AMOUNT:
                    raise ValueError

                await self.cog.dispatch(
                    interaction,
                    self.action,
                    amount=amount,
                )
                return

            number = (
                int(raw_number)
                if raw_number
                else 0
            )

            if (
                self.action == "mute"
                and not 1 <= number <= self.cog.service.max_mute_minutes
            ):
                raise ValueError

            if (
                self.action == "ban"
                and not 0 <= number <= MAX_BAN_DELETE_DAYS
            ):
                raise ValueError

        except ValueError:
            await interaction.response.send_message(
                "輸入的數字超出允許範圍。",
                ephemeral=True,
            )
            return

        reason = (
            str(self.reason.value).strip() or None
            if self.reason
            else None
        )

        await self.cog.dispatch(
            interaction,
            self.action,
            member=self.member,
            reason=reason,
            minutes=(
                number
                if self.action == "mute"
                else 0
            ),
            delete_days=(
                number
                if self.action == "ban"
                else 0
            ),
        )


# ── Confirmation ──────────────────────

class ConfirmationView(discord.ui.View):
    """對狀態修改操作進行二次確認。"""

    def __init__(
        self,
        *,
        cog: ModerationCog,
        action_name: str,
        user_id: int,
        action: ConfirmedAction,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.cog = cog
        self.action_name = action_name
        self.user_id = user_id
        self.action = action

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有原操作使用者可以確認。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的確認面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="確認",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """重新驗證權限後執行管理動作。"""

        if not await self.cog.check_permissions(
            interaction,
            self.action_name,
        ):
            return

        await self.action(
            interaction
        )
        self.stop()

    @discord.ui.button(
        label="取消",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """取消目前管理操作。"""

        await interaction.response.edit_message(
            content="已取消操作。",
            embed=None,
            view=None,
        )
        self.stop()


# ── Log Channel ──────────────────────

class LogChannelSelect(discord.ui.ChannelSelect):
    """選擇 Moderation Module 的管理日誌頻道。"""

    def __init__(
        self,
        cog: ModerationCog,
    ) -> None:
        super().__init__(
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """保存 Moderation Module 日誌頻道。"""

        if not await self.cog.check_permissions(
            interaction,
            "log_channel",
        ):
            return

        channel = self.values[0]

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "請選擇一般文字頻道。",
                ephemeral=True,
            )
            return

        await self.cog.service.set_log_channel(
            interaction,
            channel,
        )


class LogChannelView(discord.ui.View):
    """提供管理日誌頻道選擇與停用。"""

    def __init__(
        self,
        *,
        cog: ModerationCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.cog = cog
        self.user_id = user_id
        self.add_item(
            LogChannelSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有原管理面板使用者可以操作。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的管理面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="停用管理日誌",
        style=discord.ButtonStyle.secondary,
    )
    async def disable(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """停用 Moderation Module 的 Discord 日誌頻道。"""

        if not await self.cog.check_permissions(
            interaction,
            "log_channel",
        ):
            return

        await self.cog.service.set_log_channel(
            interaction,
            None,
        )
