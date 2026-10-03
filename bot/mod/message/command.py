"""
bot/mod/message/command.py

Modification():

- 提供 /say Slash Command 作為 Message Module 的單一指令入口。
- 支援直接發送純文字與最多三個附件。
- 建立 Bot 訊息、Webhook、Embed 與管理員設定的整合面板。
- 驗證各發送模式的 Guild 管理權限政策。

本檔只負責 Discord Command 與主操作面板，
實際發送邏輯分別交由 say.py、webhook.py 與 embed.py。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from bot.mod.message.database import MessageDatabase
from bot.mod.message.embed import (
    EmbedComposerView,
    EmbedService,
)
from bot.mod.message.say import (
    SayModal,
    SayService,
)
from bot.mod.message.webhook import (
    WebhookModal,
    WebhookService,
)


PermissionCheck = Callable[
    [discord.Interaction, str],
    Awaitable[bool],
]


# ── Message Cog ──────────────────────

class MessageCog(commands.Cog):
    """提供 /say 與 Message Module 整合面板。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        database: MessageDatabase,
        say_service: SayService,
        webhook_service: WebhookService,
        embed_service: EmbedService,
        panel_timeout_seconds: int,
        admin_panel_timeout_seconds: int,
    ) -> None:
        self.bot = bot
        self.database = database
        self.say_service = say_service
        self.webhook_service = webhook_service
        self.embed_service = embed_service
        self.panel_timeout_seconds = panel_timeout_seconds
        self.admin_panel_timeout_seconds = (
            admin_panel_timeout_seconds
        )

    def cog_unload(self) -> None:
        """清理由 Message Module 建立的 Runtime Resource。"""

        self.webhook_service.close()

    # ── Commands ──────────────────────

    @app_commands.command(
        name="say",
        description="開啟 Bot 訊息發送面板。",
    )
    @app_commands.describe(
        content="直接發送純文字（留空則開啟整合面板）",
        image1="附件圖片 1（選填）",
        image2="附件圖片 2（選填）",
        image3="附件圖片 3（選填）",
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    @app_commands.checks.bot_has_permissions(
        send_messages=True
    )
    async def say(
        self,
        interaction: discord.Interaction,
        content: app_commands.Range[
            str,
            1,
            1950,
        ] | None = None,
        image1: discord.Attachment | None = None,
        image2: discord.Attachment | None = None,
        image3: discord.Attachment | None = None,
    ) -> None:
        """直接發送純文字，或開啟 Message Module 面板。"""

        attachments = tuple(
            attachment
            for attachment in (
                image1,
                image2,
                image3,
            )
            if attachment is not None
        )

        if content is not None:
            if not await self.check_mode_permission(
                interaction,
                "plain",
            ):
                return

            await self.say_service.send(
                interaction,
                content=content,
                attachments=attachments,
            )
            return

        if interaction.guild_id is None:
            await interaction.response.send_message(
                "此指令只限伺服器使用。",
                ephemeral=True,
            )
            return

        restricted = self.database.requires_management(
            interaction.guild_id
        )

        embed = discord.Embed(
            title="訊息發送面板",
            description=(
                "請選擇發送方式：Bot 訊息、Webhook 自訂身分，或 Embed。\n"
                "如有在 `/say` 附上檔案，會隨 Bot 訊息或 Webhook 一併發送。\n\n"
                f"管理權限限制：**{'已開啟' if restricted else '已關閉'}**"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=MessageSenderView(
                cog=self,
                user_id=interaction.user.id,
                attachments=attachments,
                timeout=self.panel_timeout_seconds,
            ),
            ephemeral=True,
        )

    # ── Permissions ──────────────────────

    async def check_mode_permission(
        self,
        interaction: discord.Interaction,
        mode: str,
    ) -> bool:
        """依 Guild 設定檢查指定發送模式的使用者權限。"""

        if interaction.guild_id is None:
            await interaction.response.send_message(
                "此功能只限伺服器使用。",
                ephemeral=True,
            )
            return False

        if not self.database.requires_management(
            interaction.guild_id
        ):
            return True

        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            await interaction.response.send_message(
                "無法取得你的伺服器權限。",
                ephemeral=True,
            )
            return False

        if mode == "webhook":
            allowed = (
                member.guild_permissions.manage_webhooks
            )
            label = "管理 Webhook"
        else:
            allowed = (
                member.guild_permissions.manage_messages
            )
            label = "管理訊息"

        if allowed:
            return True

        await interaction.response.send_message(
            f"此伺服器已啟用 `/say` 管理權限限制，"
            f"你需要「{label}」權限。",
            ephemeral=True,
        )
        return False


# ── Message Panel ──────────────────────

class MessageSenderSelect(discord.ui.Select):
    """選擇 Message Module 的發送模式。"""

    def __init__(
        self,
        cog: MessageCog,
        attachments: tuple[discord.Attachment, ...],
    ) -> None:
        self.cog = cog
        self.attachments = attachments

        super().__init__(
            placeholder="選擇發送方式",
            options=[
                discord.SelectOption(
                    label="Bot 訊息",
                    value="plain",
                    description="以 Bot 身分發送文字、圖片或附件",
                ),
                discord.SelectOption(
                    label="Webhook 訊息",
                    value="webhook",
                    description="使用自訂名稱與頭像發送",
                ),
                discord.SelectOption(
                    label="Embed 訊息",
                    value="embed",
                    description="發送自訂嵌入式訊息",
                ),
                discord.SelectOption(
                    label="管理員設定",
                    value="settings",
                    description="設定是否要求管理權限",
                ),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """依選擇開啟對應功能。"""

        mode = self.values[0]

        if mode == "settings":
            await self._open_settings(
                interaction
            )
            return

        if not await self.cog.check_mode_permission(
            interaction,
            mode,
        ):
            return

        if mode == "plain":
            await interaction.response.send_modal(
                SayModal(
                    self.cog.say_service,
                    self.attachments,
                )
            )
            return

        if mode == "webhook":
            await interaction.response.send_modal(
                WebhookModal(
                    self.cog.webhook_service,
                    self.attachments,
                )
            )
            return

        await interaction.response.send_message(
            "使用下方按鈕分段編輯 Embed，完成後按「發送 Embed」。",
            view=EmbedComposerView(
                service=self.cog.embed_service,
                user_id=interaction.user.id,
                timeout=self.cog.panel_timeout_seconds,
                permission_check=self.cog.check_mode_permission,
            ),
            ephemeral=True,
        )

    async def _open_settings(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """開啟 /say 的 Guild 管理權限設定。"""

        member = interaction.user

        if (
            not isinstance(
                member,
                discord.Member,
            )
            or not member.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "你需要「管理員」權限才能修改此設定。",
                ephemeral=True,
            )
            return

        if interaction.guild_id is None:
            await interaction.response.send_message(
                "此功能只限伺服器使用。",
                ephemeral=True,
            )
            return

        restricted = (
            self.cog.database.requires_management(
                interaction.guild_id
            )
        )

        await interaction.response.send_message(
            (
                "目前管理權限限制："
                f"**{'已開啟' if restricted else '已關閉'}**\n"
                "開啟後，Bot 訊息／Embed 需要管理訊息，"
                "Webhook 需要管理 Webhook。"
            ),
            view=SayAdminSettingsView(
                cog=self.cog,
                user_id=interaction.user.id,
                timeout=self.cog.admin_panel_timeout_seconds,
            ),
            ephemeral=True,
        )


class MessageSenderView(discord.ui.View):
    """限制只能由 /say 發起者操作的主面板。"""

    def __init__(
        self,
        *,
        cog: MessageCog,
        user_id: int,
        attachments: tuple[discord.Attachment, ...],
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.user_id = user_id

        self.add_item(
            MessageSenderSelect(
                cog,
                attachments,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作此面板。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的訊息發送面板。",
            ephemeral=True,
        )
        return False


# ── Admin Settings ──────────────────────

class SayAdminSettingsSelect(discord.ui.Select):
    """切換 /say 的 Guild 管理權限限制。"""

    def __init__(
        self,
        cog: MessageCog,
    ) -> None:
        self.cog = cog

        super().__init__(
            placeholder="選擇 `/say` 權限模式",
            options=[
                discord.SelectOption(
                    label="不要求管理權限（預設）",
                    value="off",
                    description="所有成員都可使用 Bot 訊息、Webhook 與 Embed",
                ),
                discord.SelectOption(
                    label="要求管理權限",
                    value="on",
                    description="依發送模式要求管理訊息或管理 Webhook",
                ),
            ],
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """更新 Guild 的 /say 管理權限限制。"""

        member = interaction.user

        if (
            interaction.guild_id is None
            or not isinstance(
                member,
                discord.Member,
            )
            or not member.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "你需要「管理員」權限才能修改此設定。",
                ephemeral=True,
            )
            return

        enabled = (
            self.values[0] == "on"
        )

        self.cog.database.set_require_management(
            interaction.guild_id,
            enabled,
        )

        await interaction.response.edit_message(
            content=(
                f"`/say` 管理權限限制已"
                f"**{'開啟' if enabled else '關閉'}**。\n"
                + (
                    "Bot 訊息／Embed 現在需要管理訊息，"
                    "Webhook 需要管理 Webhook。"
                    if enabled
                    else "所有成員都可使用全部發送模式。"
                )
            ),
            view=self.view,
        )


class SayAdminSettingsView(discord.ui.View):
    """限制只能由設定面板建立者操作。"""

    def __init__(
        self,
        *,
        cog: MessageCog,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.user_id = user_id

        self.add_item(
            SayAdminSettingsSelect(
                cog
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """阻擋其他使用者操作管理員設定面板。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的管理員設定面板。",
            ephemeral=True,
        )
        return False
