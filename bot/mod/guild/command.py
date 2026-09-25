"""
bot/mod/guild/command.py

Modification():

- 提供 /server Slash Command。
- 顯示 Guild Module 目前的伺服器設定。
- 提供歡迎、離開、日誌頻道與自動身分組設定介面。
- 提供 Guild Module 設定重置確認介面。

本檔負責 Guild Module 的 Discord Command 與互動元件。
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.mod.guild.database import GuildDatabase


# ── Guild Cog ──────────────────────

class GuildCommandCog(commands.Cog):
    """提供 Guild Module 的伺服器設定面板。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        database: GuildDatabase,
        embed_footer: str,
        panel_timeout_seconds: int,
        selection_timeout_seconds: int,
        confirmation_timeout_seconds: int,
    ) -> None:
        self.bot = bot
        self.database = database
        self.embed_footer = embed_footer
        self.panel_timeout_seconds = (
            panel_timeout_seconds
        )
        self.selection_timeout_seconds = (
            selection_timeout_seconds
        )
        self.confirmation_timeout_seconds = (
            confirmation_timeout_seconds
        )

    # ── Commands ──────────────────────

    @app_commands.command(
        name="server",
        description="開啟伺服器設定面板。",
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(
        administrator=True
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def server(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟 Guild Module 設定面板。"""

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "此指令只限伺服器使用。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=self.build_settings_embed(
                guild
            ),
            view=ServerSettingsView(
                cog=self,
                user_id=interaction.user.id,
                timeout=self.panel_timeout_seconds,
            ),
            ephemeral=True,
        )

    # ── Settings ──────────────────────

    def build_settings_embed(
        self,
        guild: discord.Guild,
    ) -> discord.Embed:
        """建立目前 Guild 設定資訊。"""

        settings = self.database.get_settings(
            guild.id
        )

        embed = discord.Embed(
            title=f"{guild.name} 伺服器設定",
            description=(
                "使用下方選單修改設定；"
                "所有操作只對目前伺服器生效。"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="頻道設定",
            value=(
                "歡迎："
                f"{self._channel_mention(guild, settings.welcome_channel_id)}\n"
                "離開："
                f"{self._channel_mention(guild, settings.leave_channel_id)}\n"
                "日誌："
                f"{self._channel_mention(guild, settings.log_channel_id)}"
            ),
            inline=False,
        )
        embed.add_field(
            name="身分組設定",
            value=(
                "自動身分組："
                f"{self._role_mention(guild, settings.auto_role_id)}"
            ),
            inline=False,
        )
        embed.set_footer(
            text=self.embed_footer
        )

        return embed

    async def set_channel(
        self,
        interaction: discord.Interaction,
        *,
        key: str,
        channel: discord.abc.GuildChannel | None,
        label: str,
    ) -> None:
        """更新 Guild Module 的頻道設定。"""

        if not self._is_administrator(
            interaction
        ):
            await interaction.response.send_message(
                "你需要「管理員」權限才能修改伺服器設定。",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "此功能只限伺服器使用。",
                ephemeral=True,
            )
            return

        self.database.set_setting(
            guild.id,
            key,
            channel.id if channel else 0,
        )

        if channel is None:
            message = f"{label}已停用"
        else:
            mention = getattr(
                channel,
                "mention",
                None,
            )
            message = (
                f"{label}已設定為 "
                f"{mention or f'**{channel.name}**'}"
            )

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

    async def set_auto_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role | None,
    ) -> None:
        """更新新成員自動身分組。"""

        if not self._is_administrator(
            interaction
        ):
            await interaction.response.send_message(
                "你需要「管理員」權限才能修改伺服器設定。",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "此功能只限伺服器使用。",
                ephemeral=True,
            )
            return

        if role is not None:
            bot_member = guild.me

            invalid = (
                role.is_default()
                or role.managed
                or bot_member is None
                or role >= bot_member.top_role
            )

            if invalid:
                await interaction.response.send_message(
                    "此身分組無法用於自動身分組設定。",
                    ephemeral=True,
                )
                return

        self.database.set_setting(
            guild.id,
            "auto_role_id",
            role.id if role else 0,
        )

        message = (
            f"新成員自動身分組已設定為 {role.mention}"
            if role
            else "新成員自動身分組已停用"
        )

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

    async def reset_settings(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """重置目前 Guild 的 Guild Module 設定。"""

        if not self._is_administrator(
            interaction
        ):
            await interaction.response.send_message(
                "你需要「管理員」權限才能重置伺服器設定。",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "此功能只限伺服器使用。",
                ephemeral=True,
            )
            return

        self.database.reset_settings(
            guild.id
        )

        await interaction.response.edit_message(
            content="伺服器設定已重置為預設值。",
            embed=None,
            view=None,
        )

    # ── Helpers ──────────────────────

    @staticmethod
    def _is_administrator(
        interaction: discord.Interaction,
    ) -> bool:
        """確認 Interaction 發起者具有管理員權限。"""

        return (
            isinstance(
                interaction.user,
                discord.Member,
            )
            and interaction.user.guild_permissions.administrator
        )

    @staticmethod
    def _channel_mention(
        guild: discord.Guild,
        channel_id: int,
    ) -> str:
        """將頻道 ID 轉為設定面板顯示文字。"""

        if not channel_id:
            return "未設定"

        channel = guild.get_channel(
            channel_id
        )

        if channel is None:
            return f"不存在（{channel_id}）"

        return getattr(
            channel,
            "mention",
            f"**{channel.name}**",
        )

    @staticmethod
    def _role_mention(
        guild: discord.Guild,
        role_id: int,
    ) -> str:
        """將身分組 ID 轉為設定面板顯示文字。"""

        if not role_id:
            return "未設定"

        role = guild.get_role(
            role_id
        )

        if role is None:
            return f"不存在（{role_id}）"

        return role.mention


# ── Settings Panel ──────────────────────

class ServerSettingsSelect(discord.ui.Select):
    """選擇需要調整的 Guild 設定。"""

    def __init__(
        self,
        cog: GuildCommandCog,
    ) -> None:
        self.cog = cog

        super().__init__(
            placeholder="選擇要調整的伺服器設定",
            options=[
                discord.SelectOption(
                    label="歡迎訊息頻道",
                    value="welcome",
                ),
                discord.SelectOption(
                    label="離開訊息頻道",
                    value="leave",
                ),
                discord.SelectOption(
                    label="管理日誌頻道",
                    value="log",
                ),
                discord.SelectOption(
                    label="新成員自動身分組",
                    value="autorole",
                ),
                discord.SelectOption(
                    label="重新整理設定資訊",
                    value="info",
                ),
                discord.SelectOption(
                    label="重置全部設定",
                    value="reset",
                ),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟選定設定的操作介面。"""

        if not self.cog._is_administrator(
            interaction
        ):
            await interaction.response.send_message(
                "你需要「管理員」權限才能修改伺服器設定。",
                ephemeral=True,
            )
            return

        action = self.values[0]

        if action == "info":
            guild = interaction.guild

            if guild is None:
                await interaction.response.send_message(
                    "此功能只限伺服器使用。",
                    ephemeral=True,
                )
                return

            await interaction.response.edit_message(
                embed=self.cog.build_settings_embed(
                    guild
                ),
                view=self.view,
            )
            return

        if action == "reset":
            await interaction.response.send_message(
                "確定要重置歡迎、離開、日誌與自動身分組設定嗎？",
                view=ResetConfirmationView(
                    cog=self.cog,
                    user_id=interaction.user.id,
                    timeout=self.cog.confirmation_timeout_seconds,
                ),
                ephemeral=True,
            )
            return

        channel_options = {
            "welcome": (
                "welcome_channel_id",
                "歡迎訊息頻道",
            ),
            "leave": (
                "leave_channel_id",
                "離開訊息頻道",
            ),
            "log": (
                "log_channel_id",
                "管理日誌頻道",
            ),
        }

        if action in channel_options:
            key, label = channel_options[
                action
            ]

            await interaction.response.send_message(
                f"請選擇{label}：",
                view=ServerChannelView(
                    cog=self.cog,
                    key=key,
                    label=label,
                    timeout=self.cog.selection_timeout_seconds,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "請選擇新成員自動身分組，或按下停用：",
            view=ServerRoleView(
                cog=self.cog,
                timeout=self.cog.selection_timeout_seconds,
            ),
            ephemeral=True,
        )


class ServerSettingsView(discord.ui.View):
    """限制只有 /server 發起者可以操作。"""

    def __init__(
        self,
        *,
        cog: GuildCommandCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.user_id = user_id
        self.add_item(
            ServerSettingsSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作設定面板。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的設定面板。",
            ephemeral=True,
        )
        return False


# ── Channel Settings ──────────────────────

class ServerChannelSelect(discord.ui.ChannelSelect):
    """選擇 Guild Module 使用的文字頻道。"""

    def __init__(
        self,
        cog: GuildCommandCog,
        *,
        key: str,
        label: str,
    ) -> None:
        super().__init__(
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1,
        )

        self.cog = cog
        self.key = key
        self.label = label

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """保存選取的文字頻道。"""

        await self.cog.set_channel(
            interaction,
            key=self.key,
            channel=self.values[0],
            label=self.label,
        )


class ServerChannelView(discord.ui.View):
    """提供頻道選擇與停用操作。"""

    def __init__(
        self,
        *,
        cog: GuildCommandCog,
        key: str,
        label: str,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.cog = cog
        self.key = key
        self.label = label

        self.add_item(
            ServerChannelSelect(
                cog,
                key=key,
                label=label,
            )
        )

    @discord.ui.button(
        label="停用此設定",
        style=discord.ButtonStyle.secondary,
    )
    async def disable(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """停用目前頻道設定。"""

        await self.cog.set_channel(
            interaction,
            key=self.key,
            channel=None,
            label=self.label,
        )


# ── Role Settings ──────────────────────

class ServerRoleSelect(discord.ui.RoleSelect):
    """選擇新成員自動身分組。"""

    def __init__(
        self,
        cog: GuildCommandCog,
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
        """保存選取的自動身分組。"""

        await self.cog.set_auto_role(
            interaction,
            self.values[0],
        )


class ServerRoleView(discord.ui.View):
    """提供身分組選擇與停用操作。"""

    def __init__(
        self,
        *,
        cog: GuildCommandCog,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.cog = cog
        self.add_item(
            ServerRoleSelect(
                cog
            )
        )

    @discord.ui.button(
        label="停用此設定",
        style=discord.ButtonStyle.secondary,
    )
    async def disable(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """停用新成員自動身分組。"""

        await self.cog.set_auto_role(
            interaction,
            None,
        )


# ── Confirmation ──────────────────────

class ResetConfirmationView(discord.ui.View):
    """確認是否重置 Guild Module 設定。"""

    def __init__(
        self,
        *,
        cog: GuildCommandCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.cog = cog
        self.user_id = user_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有原設定面板使用者可確認。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的確認面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="確認重置",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """執行 Guild Module 設定重置。"""

        await self.cog.reset_settings(
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
        """取消設定重置。"""

        await interaction.response.edit_message(
            content="已取消重置。",
            view=None,
        )
        self.stop()
