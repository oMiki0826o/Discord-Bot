"""
bot/mod/ticket/command.py

Modification():

- 提供 /ticket Slash Command 作為 Ticket Module 的單一入口。
- 提供建立、關閉、加入、移除、統計與公開面板操作。
- 提供工單類別與支援身分組的管理介面。
- 對敏感管理操作執行權限檢查與二次確認。

本檔只負責 Ticket Module 的 Discord Command 與管理互動介面。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from bot.mod.ticket.config import (
    MAX_TOPIC_LENGTH,
)
from bot.mod.ticket.ticket import (
    TicketService,
)


ConfirmedAction = Callable[
    [discord.Interaction],
    Awaitable[None],
]


# ── Permission Map ──────────────────────

USER_PERMISSIONS: dict[
    str,
    tuple[str, ...],
] = {
    "add": ("moderate_members",),
    "remove": ("moderate_members",),
    "stats": ("moderate_members",),
    "panel": ("administrator",),
    "settings": ("administrator",),
}

BOT_PERMISSIONS: dict[
    str,
    tuple[str, ...],
] = {
    "open": ("manage_channels",),
    "close": ("manage_channels",),
    "add": ("manage_channels",),
    "remove": ("manage_channels",),
    "panel": (
        "send_messages",
        "embed_links",
    ),
}


# ── Ticket Cog ──────────────────────

class TicketCog(commands.Cog):
    """提供 /ticket 工單管理面板。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: TicketService,
        management_timeout_seconds: int,
        member_selection_timeout_seconds: int,
        confirmation_timeout_seconds: int,
    ) -> None:
        self.bot = bot
        self.service = service
        self.management_timeout_seconds = (
            management_timeout_seconds
        )
        self.member_selection_timeout_seconds = (
            member_selection_timeout_seconds
        )
        self.confirmation_timeout_seconds = (
            confirmation_timeout_seconds
        )

    async def cog_load(self) -> None:
        """Module Load 時註冊工單 Persistent View。"""

        self.service.register_persistent_views()

    def cog_unload(self) -> None:
        """Module Unload 時停止 Runtime View 與清除冷卻記憶體。"""

        self.service.close()

    # ── Commands ──────────────────────

    @app_commands.command(
        name="ticket",
        description="開啟工單管理面板",
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    async def ticket(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟 Ticket Module 管理面板。"""

        embed = discord.Embed(
            title="工單管理面板",
            description=(
                "請從下方選單建立或管理工單。"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=TicketManagementView(
                cog=self,
                user_id=interaction.user.id,
                timeout=self.management_timeout_seconds,
            ),
            ephemeral=True,
        )

    # ── Dispatch ──────────────────────

    async def dispatch(
        self,
        interaction: discord.Interaction,
        action: str,
        *,
        topic: str = "",
        member: discord.Member | None = None,
    ) -> None:
        """驗證操作權限並派發至 Ticket Service。"""

        if not await self.check_permissions(
            interaction,
            action,
        ):
            return

        if action == "open":
            await self.service.open_ticket(
                interaction,
                topic=topic,
            )
            return

        if action == "stats":
            await self.service.stats(
                interaction
            )
            return

        if action == "settings":
            await interaction.response.send_message(
                "請選擇要修改的 Ticket 設定：",
                view=TicketSettingsView(
                    cog=self,
                    user_id=interaction.user.id,
                    timeout=self.member_selection_timeout_seconds,
                ),
                ephemeral=True,
            )
            return

        if action == "close":
            await self._confirm(
                interaction,
                title="確認關閉工單",
                description="工單將在確認後封存或刪除。",
                action_name=action,
                action=self.service.close_ticket,
            )
            return

        if action == "panel":
            channel = interaction.channel
            channel_mention = (
                channel.mention
                if isinstance(
                    channel,
                    discord.TextChannel,
                )
                else "目前頻道"
            )

            await self._confirm(
                interaction,
                title="確認發送工單面板",
                description=(
                    f"將在 {channel_mention} 發送公開的工單建立面板。"
                ),
                action_name=action,
                action=self.service.send_panel,
            )
            return

        if member is None:
            await self._error(
                interaction,
                "加入或移除操作必須選擇成員。",
            )
            return

        if action == "add":
            operation = (
                self.service.add_member
            )
            label = "加入"
        else:
            operation = (
                self.service.remove_member
            )
            label = "移除"

        async def execute(
            click: discord.Interaction,
        ) -> None:
            await operation(
                click,
                member,
            )

        await self._confirm(
            interaction,
            title=f"確認{label}工單成員",
            description=(
                f"目標成員：{member.mention}"
            ),
            action_name=action,
            action=execute,
        )

    # ── Permissions ──────────────────────

    async def check_permissions(
        self,
        interaction: discord.Interaction,
        action: str,
    ) -> bool:
        """驗證使用者與 Bot 的工單操作權限。"""

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

        for permission in USER_PERMISSIONS.get(
            action,
            (),
        ):
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

        for permission in BOT_PERMISSIONS.get(
            action,
            (),
        ):
            if not getattr(
                bot_member.guild_permissions,
                permission,
                False,
            ):
                await self._error(
                    interaction,
                    f"Bot 缺少 `{permission}` 權限。",
                )
                return False

        return True

    # ── Confirmation ──────────────────────

    async def _confirm(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        description: str,
        action_name: str,
        action: ConfirmedAction,
    ) -> None:
        """建立 Ticket Module 的二次確認介面。"""

        await interaction.response.send_message(
            embed=discord.Embed(
                title=title,
                description=description,
                color=discord.Color.orange(),
            ),
            view=ConfirmationView(
                cog=self,
                action_name=action_name,
                user_id=interaction.user.id,
                action=action,
                timeout=self.confirmation_timeout_seconds,
            ),
            ephemeral=True,
        )

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


# ── Management Panel ──────────────────────

class TicketActionSelect(discord.ui.Select):
    """選擇工單操作。"""

    def __init__(
        self,
        cog: TicketCog,
    ) -> None:
        self.cog = cog

        super().__init__(
            placeholder="選擇工單操作",
            options=[
                discord.SelectOption(label="建立工單", value="open"),
                discord.SelectOption(label="關閉目前工單", value="close"),
                discord.SelectOption(label="加入成員", value="add"),
                discord.SelectOption(label="移除成員", value="remove"),
                discord.SelectOption(label="查看統計", value="stats"),
                discord.SelectOption(label="發送工單面板", value="panel"),
                discord.SelectOption(label="工單設定", value="settings"),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """依操作開啟對應互動流程。"""

        action = self.values[0]

        if action == "open":
            if not await self.cog.check_permissions(
                interaction,
                action,
            ):
                return

            await interaction.response.send_modal(
                TicketTopicModal(
                    self.cog
                )
            )
            return

        if action in {
            "add",
            "remove",
        }:
            if not await self.cog.check_permissions(
                interaction,
                action,
            ):
                return

            await interaction.response.send_message(
                "請選擇要加入或移除的成員：",
                view=TicketMemberView(
                    cog=self.cog,
                    action=action,
                    user_id=interaction.user.id,
                    timeout=self.cog.member_selection_timeout_seconds,
                ),
                ephemeral=True,
            )
            return

        await self.cog.dispatch(
            interaction,
            action,
        )


class TicketManagementView(discord.ui.View):
    """限制只有 /ticket 發起者可以操作。"""

    def __init__(
        self,
        *,
        cog: TicketCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.user_id = user_id
        self.add_item(
            TicketActionSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作工單管理面板。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的工單管理面板。",
            ephemeral=True,
        )
        return False


# ── Topic Modal ──────────────────────

class TicketTopicModal(discord.ui.Modal):
    """收集 /ticket open 的工單主題。"""

    def __init__(
        self,
        cog: TicketCog,
    ) -> None:
        super().__init__(
            title="建立工單"
        )
        self.cog = cog
        self.topic = discord.ui.TextInput(
            label="工單主題（選填）",
            required=False,
            max_length=MAX_TOPIC_LENGTH,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(
            self.topic
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """建立工單。"""

        await self.cog.dispatch(
            interaction,
            "open",
            topic=str(
                self.topic.value
            ).strip(),
        )


# ── Member Selection ──────────────────────

class TicketMemberSelect(discord.ui.UserSelect):
    """選擇需要加入或移除的工單成員。"""

    def __init__(
        self,
        cog: TicketCog,
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
        """解析選取的 Guild Member 並派發操作。"""

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

        await self.cog.dispatch(
            interaction,
            self.action,
            member=member,
        )


class TicketMemberView(discord.ui.View):
    """限制只有原管理面板使用者可以選擇成員。"""

    def __init__(
        self,
        *,
        cog: TicketCog,
        action: str,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.user_id = user_id
        self.add_item(
            TicketMemberSelect(
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
            "這不是你的工單管理面板。",
            ephemeral=True,
        )
        return False


# ── Confirmation ──────────────────────

class ConfirmationView(discord.ui.View):
    """Ticket Module 的敏感操作確認介面。"""

    def __init__(
        self,
        *,
        cog: TicketCog,
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
        """重新驗證權限後執行操作。"""

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
        """取消目前操作。"""

        await interaction.response.edit_message(
            content="已取消操作。",
            embed=None,
            view=None,
        )
        self.stop()


# ── Ticket Settings ──────────────────────

class TicketSettingsSelect(discord.ui.Select):
    """選擇 Ticket Module Guild 設定。"""

    def __init__(
        self,
        cog: TicketCog,
    ) -> None:
        self.cog = cog
        super().__init__(
            placeholder="選擇 Ticket 設定",
            options=[
                discord.SelectOption(
                    label="工單類別",
                    value="category",
                ),
                discord.SelectOption(
                    label="支援身分組",
                    value="support_role",
                ),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟 Ticket 設定選擇器。"""

        if not await self.cog.check_permissions(
            interaction,
            "settings",
        ):
            return

        action = self.values[0]

        if action == "category":
            view: discord.ui.View = (
                TicketCategoryView(
                    cog=self.cog,
                    user_id=interaction.user.id,
                    timeout=self.cog.member_selection_timeout_seconds,
                )
            )
            message = "請選擇工單建立類別："
        else:
            view = TicketSupportRoleView(
                cog=self.cog,
                user_id=interaction.user.id,
                timeout=self.cog.member_selection_timeout_seconds,
            )
            message = "請選擇工單支援身分組："

        await interaction.response.send_message(
            message,
            view=view,
            ephemeral=True,
        )


class TicketSettingsView(discord.ui.View):
    """Ticket Module Guild 設定面板。"""

    def __init__(
        self,
        *,
        cog: TicketCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.user_id = user_id
        self.add_item(
            TicketSettingsSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有原管理者可以操作。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的工單設定面板。",
            ephemeral=True,
        )
        return False


class TicketCategorySelect(
    discord.ui.ChannelSelect
):
    """選擇 Ticket 建立類別。"""

    def __init__(
        self,
        cog: TicketCog,
    ) -> None:
        super().__init__(
            channel_types=[
                discord.ChannelType.category
            ],
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """保存 Ticket 類別。"""

        if not await self.cog.check_permissions(
            interaction,
            "settings",
        ):
            return

        selected = self.values[0]

        if not isinstance(
            selected,
            discord.CategoryChannel,
        ):
            await interaction.response.send_message(
                "請選擇頻道類別。",
                ephemeral=True,
            )
            return

        await self.cog.service.set_category(
            interaction,
            selected,
        )


class TicketCategoryView(discord.ui.View):
    """提供 Ticket 類別選擇與停用。"""

    def __init__(
        self,
        *,
        cog: TicketCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.cog = cog
        self.user_id = user_id
        self.add_item(
            TicketCategorySelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有原管理者可以操作。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的工單設定面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="停用指定類別",
        style=discord.ButtonStyle.secondary,
    )
    async def disable(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """清除 Ticket 類別 ID。"""

        if not await self.cog.check_permissions(
            interaction,
            "settings",
        ):
            return

        await self.cog.service.set_category(
            interaction,
            None,
        )


class TicketSupportRoleSelect(
    discord.ui.RoleSelect
):
    """選擇 Ticket 支援身分組。"""

    def __init__(
        self,
        cog: TicketCog,
    ) -> None:
        super().__init__(
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """保存 Ticket 支援身分組。"""

        if not await self.cog.check_permissions(
            interaction,
            "settings",
        ):
            return

        await self.cog.service.set_support_role(
            interaction,
            self.values[0],
        )


class TicketSupportRoleView(
    discord.ui.View
):
    """提供 Ticket 支援身分組選擇與停用。"""

    def __init__(
        self,
        *,
        cog: TicketCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.cog = cog
        self.user_id = user_id
        self.add_item(
            TicketSupportRoleSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有原管理者可以操作。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的工單設定面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="停用支援身分組",
        style=discord.ButtonStyle.secondary,
    )
    async def disable(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """清除 Ticket 支援身分組。"""

        if not await self.cog.check_permissions(
            interaction,
            "settings",
        ):
            return

        await self.cog.service.set_support_role(
            interaction,
            None,
        )
