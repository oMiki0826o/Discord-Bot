"""
bot/mod/message/embed.py

Modification():

- 提供完整 Embed 訊息建構與發送功能。
- 支援標題、描述、顏色、作者、頁腳、縮圖、圖片與回覆。
- 提供分段式 Embed Composer，保存尚未送出的編輯狀態。
- 顏色解析失敗時使用預設藍色並回報提示。

本檔負責 Message Module 的 Embed 發送邏輯與建構介面。
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

import discord


logger = logging.getLogger(
    "bot.mod.message.embed"
)


# ── Models ──────────────────────

@dataclass(slots=True)
class EmbedData:
    """保存 Embed Composer 尚未送出的資料。"""

    title: str | None = None
    description: str | None = None
    color: str | None = None
    author: str | None = None
    author_icon: str | None = None
    footer: str | None = None
    footer_icon: str | None = None
    thumbnail: str | None = None
    image_url: str | None = None
    message_id: str | None = None


# ── Embed Service ──────────────────────

class EmbedService:
    """建立並發送完整 Discord Embed。"""

    async def send(
        self,
        interaction: discord.Interaction,
        *,
        data: EmbedData,
    ) -> None:
        """建立 Embed 並發送至目前文字頻道。"""

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
                "找不到可發送 Embed 的頻道。",
            )
            return

        bot_member = channel.guild.me

        if (
            bot_member is None
            or not channel.permissions_for(
                bot_member
            ).embed_links
        ):
            await self._respond(
                interaction,
                "Bot 缺少「嵌入連結」權限。",
            )
            return

        if (
            not data.title
            and not data.description
        ):
            await self._respond(
                interaction,
                "請先填寫 Embed 標題或內文。",
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        reference = await self._fetch_reference(
            channel,
            data.message_id,
        )

        embed_color = discord.Color.blue()
        color_warning = ""

        if data.color:
            try:
                embed_color = discord.Color.from_str(
                    data.color
                )
            except ValueError:
                color_warning = (
                    f"\n無效的顏色 `{data.color}`，"
                    "已使用預設藍色。"
                    "（範例：`#FF5733` 或 `red`）"
                )

        embed = discord.Embed(
            title=data.title,
            description=data.description,
            color=embed_color,
        )

        if data.author:
            embed.set_author(
                name=data.author,
                icon_url=data.author_icon,
            )

        if data.footer:
            embed.set_footer(
                text=data.footer,
                icon_url=data.footer_icon,
            )

        if data.thumbnail:
            embed.set_thumbnail(
                url=data.thumbnail
            )

        if data.image_url:
            embed.set_image(
                url=data.image_url
            )

        try:
            await channel.send(
                embed=embed,
                reference=reference,
            )
        except discord.HTTPException:
            logger.exception(
                "Embed 發送失敗 guild_id=%s channel_id=%s",
                interaction.guild_id,
                interaction.channel_id,
            )
            await interaction.followup.send(
                "Embed 發送失敗。",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"已發送。{color_warning}",
            ephemeral=True,
        )

    # ── Helpers ──────────────────────

    @staticmethod
    async def _fetch_reference(
        channel: discord.TextChannel | discord.Thread,
        message_id: str | None,
    ) -> discord.Message | None:
        """取得 Embed 的回覆目標。"""

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


# ── Embed Composer ──────────────────────

class EmbedComposerView(discord.ui.View):
    """提供分段式 Embed 編輯器。"""

    def __init__(
        self,
        *,
        service: EmbedService,
        user_id: int,
        timeout: float,
        permission_check,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        self.service = service
        self.user_id = user_id
        self.permission_check = permission_check
        self.data = EmbedData()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有建立編輯器的使用者可操作。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的 Embed 編輯器。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="基本內容",
        style=discord.ButtonStyle.secondary,
    )
    async def basic(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """編輯標題、描述與顏色。"""

        await interaction.response.send_modal(
            EmbedSectionModal(
                self,
                "basic",
            )
        )

    @discord.ui.button(
        label="作者與頁腳",
        style=discord.ButtonStyle.secondary,
    )
    async def attribution(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """編輯作者與頁腳。"""

        await interaction.response.send_modal(
            EmbedSectionModal(
                self,
                "attribution",
            )
        )

    @discord.ui.button(
        label="圖片與回覆",
        style=discord.ButtonStyle.secondary,
    )
    async def media(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """編輯圖片與回覆目標。"""

        await interaction.response.send_modal(
            EmbedSectionModal(
                self,
                "media",
            )
        )

    @discord.ui.button(
        label="發送 Embed",
        style=discord.ButtonStyle.primary,
    )
    async def send_embed(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """驗證權限後發送目前 Embed。"""

        if not await self.permission_check(
            interaction,
            "embed",
        ):
            return

        await self.service.send(
            interaction,
            data=self.data,
        )

        self.stop()


class EmbedSectionModal(discord.ui.Modal):
    """編輯 Embed Composer 的單一區段。"""

    def __init__(
        self,
        composer: EmbedComposerView,
        section: str,
    ) -> None:
        titles = {
            "basic": "Embed 基本內容",
            "attribution": "Embed 作者與頁腳",
            "media": "Embed 圖片與回覆",
        }

        super().__init__(
            title=titles[section]
        )

        self.composer = composer
        self.section = section
        self.inputs: dict[
            str,
            discord.ui.TextInput,
        ] = {}

        if section == "basic":
            self._add(
                "title",
                "標題",
                max_length=256,
            )
            self._add(
                "description",
                "內文",
                max_length=4000,
                style=discord.TextStyle.paragraph,
            )
            self._add(
                "color",
                "顏色（如 #FF5733 或 red）",
                max_length=30,
            )

        elif section == "attribution":
            self._add(
                "author",
                "作者名稱",
                max_length=256,
            )
            self._add(
                "author_icon",
                "作者圖示 URL",
            )
            self._add(
                "footer",
                "頁腳文字",
                max_length=2048,
            )
            self._add(
                "footer_icon",
                "頁腳圖示 URL",
            )

        else:
            self._add(
                "thumbnail",
                "縮圖 URL",
            )
            self._add(
                "image_url",
                "主要圖片 URL",
            )
            self._add(
                "message_id",
                "回覆訊息 ID",
                max_length=20,
            )

    def _add(
        self,
        key: str,
        label: str,
        **kwargs: object,
    ) -> None:
        """建立並加入單一 Embed 輸入欄位。"""

        current = getattr(
            self.composer.data,
            key,
        )

        if current:
            kwargs["default"] = current

        item = discord.ui.TextInput(
            label=label,
            required=False,
            **kwargs,
        )

        self.inputs[key] = item
        self.add_item(item)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """保存目前區段資料至 Composer Runtime State。"""

        for key, item in self.inputs.items():
            setattr(
                self.composer.data,
                key,
                str(item.value).strip() or None,
            )

        await interaction.response.send_message(
            "已儲存這一段 Embed 設定。",
            ephemeral=True,
        )
