"""
bot/mod/role/command.py

Modification():

- 提供 /roles Slash Command 作為 Role Module 的管理入口。
- 提供建立、新增、移除、刪除與列出身分組面板的操作介面。
- 對會修改公開面板的操作執行二次確認。
- 驗證管理身分組與管理員權限。

本檔只負責 Role Module 的 Discord Command 與管理互動介面。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from bot.mod.role.config import (
    MAX_BUTTON_LABEL_LENGTH,
    MAX_PANEL_DESCRIPTION_LENGTH,
    MAX_PANEL_TITLE_LENGTH,
    MAX_ROLE_DESCRIPTION_LENGTH,
)
from bot.mod.role.panel import RolePanelService


ConfirmedAction = Callable[
    [discord.Interaction],
    Awaitable[None],
]


# ── Role Cog ──────────────────────

class RoleCommandCog(commands.Cog):
    """提供 /roles 身分組面板管理。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: RolePanelService,
        default_panel_title: str,
        default_panel_description: str,
        management_timeout_seconds: int,
        selection_timeout_seconds: int,
        confirmation_timeout_seconds: int,
    ) -> None:
        self.bot = bot
        self.service = service
        self.default_panel_title = (
            default_panel_title
        )
        self.default_panel_description = (
            default_panel_description
        )
        self.management_timeout_seconds = (
            management_timeout_seconds
        )
        self.selection_timeout_seconds = (
            selection_timeout_seconds
        )
        self.confirmation_timeout_seconds = (
            confirmation_timeout_seconds
        )

    async def cog_load(self) -> None:
        """Module Load 時重建身分組 Persistent View。"""

        await self.service.load_persistent_views()

    def cog_unload(self) -> None:
        """Module Unload 時停止本次建立的 Runtime View。"""

        self.service.close()

    # ── Commands ──────────────────────

    @app_commands.command(
        name="roles",
        description="開啟身分組面板管理。",
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(
        manage_roles=True
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def roles(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟身分組面板管理介面。"""

        embed = discord.Embed(
            title="身分組面板管理",
            description=(
                "請從下方選單建立、修改、"
                "列出或刪除身分組面板。"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=RoleManagementView(
                cog=self,
                user_id=interaction.user.id,
                timeout=self.management_timeout_seconds,
            ),
            ephemeral=True,
        )

    # ── Permission Helpers ──────────────────────

    @staticmethod
    async def check_permission(
        interaction: discord.Interaction,
        *,
        administrator: bool = False,
    ) -> bool:
        """重新驗證敏感操作所需權限。"""

        member = interaction.user
        guild = interaction.guild

        if (
            guild is None
            or not isinstance(
                member,
                discord.Member,
            )
        ):
            await interaction.response.send_message(
                "此功能只限伺服器成員使用。",
                ephemeral=True,
            )
            return False

        if administrator:
            allowed = (
                member.guild_permissions.administrator
            )
            permission_name = "管理員"
        else:
            allowed = (
                member.guild_permissions.manage_roles
            )
            permission_name = "管理身分組"

        if not allowed:
            await interaction.response.send_message(
                f"你需要「{permission_name}」權限才能執行此操作。",
                ephemeral=True,
            )
            return False

        bot_member = guild.me

        if (
            bot_member is None
            or not bot_member.guild_permissions.manage_roles
        ):
            await interaction.response.send_message(
                "Bot 缺少「管理身分組」權限。",
                ephemeral=True,
            )
            return False

        return True


# ── Management Panel ──────────────────────

class RoleManagementSelect(discord.ui.Select):
    """選擇身分組面板管理操作。"""

    def __init__(
        self,
        cog: RoleCommandCog,
    ) -> None:
        self.cog = cog

        super().__init__(
            placeholder="選擇身分組面板操作",
            options=[
                discord.SelectOption(
                    label="建立面板",
                    value="panel",
                ),
                discord.SelectOption(
                    label="新增身分組",
                    value="add",
                ),
                discord.SelectOption(
                    label="移除身分組",
                    value="remove",
                ),
                discord.SelectOption(
                    label="刪除面板",
                    value="delete",
                ),
                discord.SelectOption(
                    label="列出面板",
                    value="list",
                ),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """依選擇開啟對應操作。"""

        action = self.values[0]

        if action == "list":
            if not await self.cog.check_permission(
                interaction
            ):
                return

            await self.cog.service.list_panels(
                interaction
            )
            return

        if action in {
            "add",
            "remove",
        }:
            if not await self.cog.check_permission(
                interaction
            ):
                return

            await interaction.response.send_message(
                "請選擇要操作的身分組：",
                view=RoleTargetView(
                    cog=self.cog,
                    action=action,
                    user_id=interaction.user.id,
                    timeout=self.cog.selection_timeout_seconds,
                ),
                ephemeral=True,
            )
            return

        if action == "delete":
            if not await self.cog.check_permission(
                interaction,
                administrator=True,
            ):
                return
        elif not await self.cog.check_permission(
            interaction
        ):
            return

        await interaction.response.send_modal(
            RoleManagementModal(
                cog=self.cog,
                action=action,
            )
        )


class RoleManagementView(discord.ui.View):
    """限制只有 /roles 發起者可以操作。"""

    def __init__(
        self,
        *,
        cog: RoleCommandCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.user_id = user_id
        self.add_item(
            RoleManagementSelect(
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
            "這不是你的身分組管理面板。",
            ephemeral=True,
        )
        return False


# ── Role Selection ──────────────────────

class RoleTargetSelect(discord.ui.RoleSelect):
    """選擇需要加入或移除的身分組。"""

    def __init__(
        self,
        cog: RoleCommandCog,
        action: str,
    ) -> None:
        super().__init__(
            placeholder="選擇一個身分組",
            min_values=1,
            max_values=1,
        )

        self.cog = cog
        self.action = action

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """選取身分組後開啟操作資料 Modal。"""

        if not await self.cog.check_permission(
            interaction
        ):
            return

        await interaction.response.send_modal(
            RoleManagementModal(
                cog=self.cog,
                action=self.action,
                role=self.values[0],
            )
        )


class RoleTargetView(discord.ui.View):
    """限制只有原管理面板使用者可以選擇身分組。"""

    def __init__(
        self,
        *,
        cog: RoleCommandCog,
        action: str,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.user_id = user_id
        self.add_item(
            RoleTargetSelect(
                cog,
                action,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作身分組選擇器。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的身分組管理面板。",
            ephemeral=True,
        )
        return False


# ── Management Modal ──────────────────────

class RoleManagementModal(discord.ui.Modal):
    """收集身分組面板管理操作資料。"""

    def __init__(
        self,
        *,
        cog: RoleCommandCog,
        action: str,
        role: discord.Role | None = None,
    ) -> None:
        titles = {
            "panel": "建立身分組面板",
            "add": "新增身分組",
            "remove": "移除身分組",
            "delete": "刪除身分組面板",
        }

        super().__init__(
            title=titles[action]
        )

        self.cog = cog
        self.action = action
        self.role = role
        self.inputs: dict[
            str,
            discord.ui.TextInput,
        ] = {}

        if action == "panel":
            self._add_input(
                "title",
                "面板標題",
                default=cog.default_panel_title,
                max_length=MAX_PANEL_TITLE_LENGTH,
            )
            self._add_input(
                "description",
                "面板說明",
                default=cog.default_panel_description,
                max_length=MAX_PANEL_DESCRIPTION_LENGTH,
                style=discord.TextStyle.paragraph,
            )
            return

        self._add_input(
            "message_id",
            "面板訊息 ID",
            max_length=20,
        )

        if action == "add":
            self._add_input(
                "label",
                "按鈕文字（選填）",
                required=False,
                max_length=MAX_BUTTON_LABEL_LENGTH,
            )
            self._add_input(
                "emoji",
                "表情符號（選填）",
                required=False,
                max_length=100,
            )
            self._add_input(
                "description",
                "身分組說明（選填）",
                required=False,
                max_length=MAX_ROLE_DESCRIPTION_LENGTH,
            )
            self._add_input(
                "style",
                "樣式：primary/secondary/success/danger",
                default="secondary",
                max_length=9,
            )

    def _add_input(
        self,
        key: str,
        label: str,
        **kwargs: object,
    ) -> None:
        """建立並加入 Modal TextInput。"""

        item = discord.ui.TextInput(
            label=label,
            **kwargs,
        )
        self.inputs[key] = item
        self.add_item(item)

    def _value(
        self,
        key: str,
    ) -> str | None:
        """取得並清理 Modal 欄位值。"""

        if key not in self.inputs:
            return None

        value = str(
            self.inputs[key].value
        ).strip()

        return value or None

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """建立操作摘要並要求二次確認。"""

        administrator = (
            self.action == "delete"
        )

        if not await self.cog.check_permission(
            interaction,
            administrator=administrator,
        ):
            return

        message_id = self._value(
            "message_id"
        )

        if (
            self.action != "panel"
            and message_id is None
        ):
            await interaction.response.send_message(
                "此操作必須填寫面板訊息 ID。",
                ephemeral=True,
            )
            return

        if (
            self.action in {
                "add",
                "remove",
            }
            and self.role is None
        ):
            await interaction.response.send_message(
                "此操作必須選擇身分組。",
                ephemeral=True,
            )
            return

        if self.action == "panel":
            title = (
                self._value("title")
                or self.cog.default_panel_title
            )
            description = (
                self._value("description")
                or self.cog.default_panel_description
            )

            async def action(
                click: discord.Interaction,
            ) -> None:
                if not await self.cog.check_permission(
                    click
                ):
                    return

                await self.cog.service.create_panel(
                    click,
                    title=title,
                    description=description,
                )

            summary = (
                f"將在目前頻道建立公開面板「{title}」。"
            )
            confirmation_title = (
                "確認建立身分組面板"
            )

        elif self.action == "add":
            assert self.role is not None
            assert message_id is not None

            style = (
                self._value("style")
                or "secondary"
            )

            if style not in {
                "primary",
                "secondary",
                "success",
                "danger",
            }:
                await interaction.response.send_message(
                    "按鈕樣式必須是 primary、secondary、success 或 danger。",
                    ephemeral=True,
                )
                return

            async def action(
                click: discord.Interaction,
            ) -> None:
                if not await self.cog.check_permission(
                    click
                ):
                    return

                await self.cog.service.add_role(
                    click,
                    message_id=message_id,
                    role=self.role,
                    label=self._value("label"),
                    emoji=self._value("emoji"),
                    description=(
                        self._value("description")
                        or ""
                    ),
                    style=style,
                )

            summary = (
                f"將 {self.role.mention} "
                f"加入面板 `{message_id}`。"
            )
            confirmation_title = (
                "確認新增身分組"
            )

        elif self.action == "remove":
            assert self.role is not None
            assert message_id is not None

            async def action(
                click: discord.Interaction,
            ) -> None:
                if not await self.cog.check_permission(
                    click
                ):
                    return

                await self.cog.service.remove_role(
                    click,
                    message_id=message_id,
                    role=self.role,
                )

            summary = (
                f"將 {self.role.mention} "
                f"從面板 `{message_id}` 移除。"
            )
            confirmation_title = (
                "確認移除身分組"
            )

        else:
            assert message_id is not None

            async def action(
                click: discord.Interaction,
            ) -> None:
                if not await self.cog.check_permission(
                    click,
                    administrator=True,
                ):
                    return

                await self.cog.service.delete_panel(
                    click,
                    message_id=message_id,
                )

            summary = (
                f"將刪除面板 `{message_id}` 及其訊息，"
                "此操作無法復原。"
            )
            confirmation_title = (
                "確認刪除面板"
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                title=confirmation_title,
                description=summary,
                color=discord.Color.orange(),
            ),
            view=ConfirmationView(
                user_id=interaction.user.id,
                action=action,
                timeout=self.cog.confirmation_timeout_seconds,
            ),
            ephemeral=True,
        )


# ── Confirmation ──────────────────────

class ConfirmationView(discord.ui.View):
    """對公開面板修改操作進行二次確認。"""

    def __init__(
        self,
        *,
        user_id: int,
        action: ConfirmedAction,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

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
        """重新驗證權限後執行已確認操作。"""

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
