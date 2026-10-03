"""
bot/mod/message/webhook.py

Modification():

- 提供自訂名稱與頭像的 Webhook 訊息發送功能。
- 支援附件、圖片 URL 與模擬引用訊息。
- 維護每個文字頻道的 Bot 專屬 Webhook 快取。
- 驗證快取 Webhook 是否仍存在，失效時重新取得或建立。

本檔負責 Message Module 的 Webhook 發送邏輯與輸入介面。
"""

from __future__ import annotations

import logging

import discord


logger = logging.getLogger(
    "bot.mod.message.webhook"
)


# ── Webhook Service ──────────────────────

class WebhookService:
    """處理 Message Module 的 Webhook 訊息。"""

    def __init__(
        self,
        *,
        bot: discord.Client,
        webhook_name: str,
        max_content_length: int,
        max_attachments: int,
    ) -> None:
        self.bot = bot
        self.webhook_name = webhook_name
        self.max_content_length = max_content_length
        self.max_attachments = max_attachments

        self._cache: dict[
            int,
            discord.Webhook,
        ] = {}

    def close(self) -> None:
        """清除 Module Reload 後不應保留的 Webhook Cache。"""

        self._cache.clear()

    async def send(
        self,
        interaction: discord.Interaction,
        *,
        content: str,
        username: str | None = None,
        avatar_url: str | None = None,
        image_url: str | None = None,
        message_id: str | None = None,
        attachments: tuple[discord.Attachment, ...] = (),
    ) -> None:
        """使用 Bot 專屬 Webhook 發送訊息。"""

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await self._respond(
                interaction,
                "Webhook 僅限一般文字頻道使用。",
            )
            return

        content = content.strip()

        if not content:
            await self._respond(
                interaction,
                "訊息內容不可為空白。",
            )
            return

        if len(content) > self.max_content_length:
            await self._respond(
                interaction,
                f"訊息內容不可超過 {self.max_content_length} 個字元。",
            )
            return

        if len(attachments) > self.max_attachments:
            await self._respond(
                interaction,
                f"最多只能附加 {self.max_attachments} 個檔案。",
            )
            return

        bot_member = channel.guild.me

        if (
            bot_member is None
            or not channel.permissions_for(
                bot_member
            ).manage_webhooks
        ):
            await self._respond(
                interaction,
                "Bot 缺少「管理 Webhook」權限。",
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        reference_text = await self._build_reference_text(
            channel,
            message_id,
        )

        send_name = (
            username.strip()
            if username and username.strip()
            else interaction.user.display_name
        )
        send_avatar = (
            avatar_url.strip()
            if avatar_url and avatar_url.strip()
            else str(
                interaction.user.display_avatar.url
            )
        )

        try:
            files = [
                await attachment.to_file()
                for attachment in attachments
            ]

            webhook = await self._get_webhook(
                channel
            )

            await self._send_payload(
                webhook,
                content=reference_text + content,
                username=send_name,
                avatar_url=send_avatar,
                image_url=image_url,
                files=files,
            )

        except discord.NotFound:
            self._cache.pop(
                channel.id,
                None,
            )

            try:
                files = [
                    await attachment.to_file()
                    for attachment in attachments
                ]

                webhook = await self._get_webhook(
                    channel
                )

                await self._send_payload(
                    webhook,
                    content=reference_text + content,
                    username=send_name,
                    avatar_url=send_avatar,
                    image_url=image_url,
                    files=files,
                )

            except discord.HTTPException:
                logger.exception(
                    "Webhook 重建後發送失敗 guild_id=%s channel_id=%s",
                    interaction.guild_id,
                    interaction.channel_id,
                )
                await interaction.followup.send(
                    "Webhook 訊息發送失敗。",
                    ephemeral=True,
                )
                return

        except discord.HTTPException:
            logger.exception(
                "Webhook 訊息發送失敗 guild_id=%s channel_id=%s",
                interaction.guild_id,
                interaction.channel_id,
            )
            await interaction.followup.send(
                "Webhook 訊息發送失敗。",
                ephemeral=True,
            )
            return

        logger.info(
            "Webhook 訊息已發送 guild_id=%s channel_id=%s user_id=%s",
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
        )

        await interaction.followup.send(
            "已發送。",
            ephemeral=True,
        )

    # ── Webhook Cache ──────────────────────

    async def _get_webhook(
        self,
        channel: discord.TextChannel,
    ) -> discord.Webhook:
        """取得或建立頻道的 Bot 專屬 Webhook。"""

        cached = self._cache.get(
            channel.id
        )

        if cached is not None:
            try:
                webhooks = await channel.webhooks()

                if any(
                    webhook.id == cached.id
                    for webhook in webhooks
                ):
                    return cached
            except discord.HTTPException:
                logger.warning(
                    "Webhook Cache 驗證失敗 channel_id=%s",
                    channel.id,
                )

            self._cache.pop(
                channel.id,
                None,
            )

        webhooks = await channel.webhooks()
        bot_user = self.bot.user

        for webhook in webhooks:
            if (
                webhook.user is not None
                and bot_user is not None
                and webhook.user.id == bot_user.id
            ):
                self._cache[channel.id] = webhook
                return webhook

        webhook = await channel.create_webhook(
            name=self.webhook_name
        )
        self._cache[channel.id] = webhook

        return webhook

    # ── Helpers ──────────────────────

    async def _send_payload(
        self,
        webhook: discord.Webhook,
        *,
        content: str,
        username: str,
        avatar_url: str,
        image_url: str | None,
        files: list[discord.File],
    ) -> None:
        """發送 Webhook 主訊息與選填圖片。"""

        await webhook.send(
            content,
            username=username,
            avatar_url=avatar_url,
            files=files,
            wait=True,
        )

        if image_url and image_url.strip():
            embed = discord.Embed()
            embed.set_image(
                url=image_url.strip()
            )

            await webhook.send(
                embed=embed,
                username=username,
                avatar_url=avatar_url,
                wait=True,
            )

    @staticmethod
    async def _build_reference_text(
        channel: discord.TextChannel,
        message_id: str | None,
    ) -> str:
        """建立 Webhook 發送時使用的引用文字。"""

        if not message_id:
            return ""

        try:
            message = await channel.fetch_message(
                int(message_id)
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
            ValueError,
        ):
            return ""

        return (
            f"> 回覆 {message.author.mention}\n"
        )

    @staticmethod
    async def _respond(
        interaction: discord.Interaction,
        content: str,
    ) -> None:
        """依 Interaction 狀態選擇 Response 或 Followup。"""

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


# ── Webhook Modal ──────────────────────

class WebhookModal(discord.ui.Modal):
    """收集 Webhook 發送資料。"""

    def __init__(
        self,
        service: WebhookService,
        attachments: tuple[discord.Attachment, ...],
    ) -> None:
        super().__init__(
            title="發送 Webhook 訊息"
        )

        self.service = service
        self.attachments = attachments

        self.content = discord.ui.TextInput(
            label="訊息內容",
            max_length=service.max_content_length,
            style=discord.TextStyle.paragraph,
        )
        self.username = discord.ui.TextInput(
            label="顯示名稱（選填）",
            required=False,
            max_length=80,
        )
        self.avatar_url = discord.ui.TextInput(
            label="頭像 URL（選填）",
            required=False,
        )
        self.image_url = discord.ui.TextInput(
            label="圖片 URL（選填）",
            required=False,
        )
        self.message_id = discord.ui.TextInput(
            label="引用訊息 ID（選填）",
            required=False,
            max_length=20,
        )

        self.add_item(self.content)
        self.add_item(self.username)
        self.add_item(self.avatar_url)
        self.add_item(self.image_url)
        self.add_item(self.message_id)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """發送 Modal 收集的 Webhook 訊息。"""

        await self.service.send(
            interaction,
            content=str(self.content),
            username=str(self.username).strip() or None,
            avatar_url=str(self.avatar_url).strip() or None,
            image_url=str(self.image_url).strip() or None,
            message_id=str(self.message_id).strip() or None,
            attachments=self.attachments,
        )
