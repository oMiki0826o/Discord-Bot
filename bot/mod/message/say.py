"""
bot/mod/message/say.py

Modification():

- 提供 Bot 身分的一般訊息發送功能。
- 支援附件、圖片 URL 與指定訊息回覆。
- 在代發內容標示實際發起者。
- 限制 Mention 行為不得超過發起者本身權限。

本檔負責 Message Module 的一般訊息發送邏輯。
"""

from __future__ import annotations

import logging

import discord


logger = logging.getLogger(
    "bot.mod.message.say"
)


# ── Say Service ──────────────────────

class SayService:
    """處理 Bot 身分的一般訊息發送。"""

    def __init__(
        self,
        *,
        max_content_length: int,
        max_attachments: int,
    ) -> None:
        self.max_content_length = max_content_length
        self.max_attachments = max_attachments

    async def send(
        self,
        interaction: discord.Interaction,
        *,
        content: str,
        image_url: str | None = None,
        message_id: str | None = None,
        attachments: tuple[discord.Attachment, ...] = (),
    ) -> None:
        """以 Bot 身分發送訊息。"""

        channel = interaction.channel

        if not isinstance(
            channel,
            (
                discord.TextChannel,
                discord.Thread,
            ),
        ):
            await self._respond(
                interaction,
                "找不到可發送訊息的頻道。",
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

        if bot_member is None:
            await self._respond(
                interaction,
                "無法取得 Bot 的伺服器成員資料。",
            )
            return

        bot_permissions = channel.permissions_for(
            bot_member
        )

        if attachments and not bot_permissions.attach_files:
            await self._respond(
                interaction,
                "Bot 沒有上傳附件的權限。",
            )
            return

        if image_url and not bot_permissions.embed_links:
            await self._respond(
                interaction,
                "Bot 沒有嵌入連結的權限。",
            )
            return

        reference = await self._fetch_reference(
            channel,
            message_id,
        )

        if not interaction.response.is_done():
            await interaction.response.defer(
                ephemeral=True
            )

        try:
            files = [
                await attachment.to_file()
                for attachment in attachments
            ]

            permissions = channel.permissions_for(
                interaction.user
            )

            allowed_mentions = discord.AllowedMentions(
                everyone=permissions.mention_everyone,
                roles=permissions.mention_everyone,
                users=True,
                replied_user=True,
            )

            display_name = str(
                getattr(
                    interaction.user,
                    "display_name",
                    None,
                )
                or getattr(
                    interaction.user,
                    "name",
                    None,
                )
                or interaction.user.id
            )

            safe_display_name = (
                discord.utils.escape_markdown(
                    display_name
                )
            )

            await channel.send(
                f"**{safe_display_name}**說：{content}",
                files=files,
                reference=reference,
                allowed_mentions=allowed_mentions,
            )

            if image_url:
                embed = discord.Embed()
                embed.set_image(
                    url=image_url.strip()
                )

                await channel.send(
                    embed=embed,
                    reference=reference,
                )

        except discord.Forbidden:
            await interaction.followup.send(
                "Bot 沒有完成此訊息操作所需的權限。",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            logger.exception(
                "Bot 訊息發送失敗 guild_id=%s channel_id=%s",
                interaction.guild_id,
                interaction.channel_id,
            )
            await interaction.followup.send(
                "訊息發送失敗。",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "已發送。",
            ephemeral=True,
        )

    # ── Helpers ──────────────────────

    @staticmethod
    async def _fetch_reference(
        channel: discord.TextChannel | discord.Thread,
        message_id: str | None,
    ) -> discord.Message | None:
        """取得指定的回覆訊息。"""

        if not message_id:
            return None

        try:
            return await channel.fetch_message(
                int(message_id)
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
            ValueError,
        ):
            return None

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


# ── Say Modal ──────────────────────

class SayModal(discord.ui.Modal):
    """收集一般訊息的進階發送資料。"""

    def __init__(
        self,
        service: SayService,
        attachments: tuple[discord.Attachment, ...],
    ) -> None:
        super().__init__(
            title="發送 Bot 訊息"
        )

        self.service = service
        self.attachments = attachments

        self.content = discord.ui.TextInput(
            label="訊息內容",
            max_length=service.max_content_length,
            style=discord.TextStyle.paragraph,
        )
        self.image_url = discord.ui.TextInput(
            label="圖片 URL（選填）",
            required=False,
        )
        self.message_id = discord.ui.TextInput(
            label="回覆訊息 ID（選填）",
            required=False,
            max_length=20,
        )

        self.add_item(self.content)
        self.add_item(self.image_url)
        self.add_item(self.message_id)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """發送 Modal 收集的一般訊息。"""

        await self.service.send(
            interaction,
            content=str(self.content),
            image_url=str(self.image_url).strip() or None,
            message_id=str(self.message_id).strip() or None,
            attachments=self.attachments,
        )
