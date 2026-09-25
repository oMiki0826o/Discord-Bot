"""
bot/mod/role/panel.py

Modification():

- 建立身分組自助領取面板與 Persistent Button View。
- 處理身分組按鈕的領取與移除切換。
- 建立、更新、刪除與列出身分組面板。
- 驗證身分組階層、面板容量與 Discord 訊息限制。
- 在 Module Load 時重建持久化 View，Unload 時停止 Runtime View。

本檔負責 Role Module 的身分組面板業務邏輯。
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.mod.role.config import (
    EMBED_FIELD_VALUE_LIMIT,
    MAX_BUTTON_LABEL_LENGTH,
    MAX_PANEL_DESCRIPTION_LENGTH,
    MAX_PANEL_ROLES,
    MAX_PANEL_TITLE_LENGTH,
    MAX_ROLE_DESCRIPTION_LENGTH,
)
from bot.mod.role.database import (
    RoleButtonData,
    RoleDatabase,
    RolePanelData,
)


logger = logging.getLogger(
    "bot.mod.role.panel"
)


# ── Helpers ──────────────────────

def parse_button_style(
    style: str,
) -> discord.ButtonStyle:
    """將設定文字轉為 Discord ButtonStyle。"""

    return {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
    }.get(
        style,
        discord.ButtonStyle.secondary,
    )


def split_role_lines(
    lines: list[str],
) -> list[tuple[str, str]]:
    """依 Discord Embed Field 上限切分身分組清單。"""

    fields: list[tuple[str, str]] = []
    current: list[str] = []

    for line in lines:
        candidate = "\n".join(
            [*current, line]
        )

        if (
            len(candidate) > EMBED_FIELD_VALUE_LIMIT
            and current
        ):
            label = (
                "可選身分組"
                if not fields
                else "可選身分組（續）"
            )
            fields.append(
                (
                    label,
                    "\n".join(current),
                )
            )
            current = [line]
            continue

        current.append(line)

    if current:
        label = (
            "可選身分組"
            if not fields
            else "可選身分組（續）"
        )
        fields.append(
            (
                label,
                "\n".join(current),
            )
        )

    return fields


def build_panel_embed(
    panel: RolePanelData,
    guild: discord.Guild,
) -> discord.Embed:
    """建立公開身分組面板 Embed。"""

    embed = discord.Embed(
        title=panel.title,
        description=panel.description,
        color=discord.Color.blurple(),
    )

    lines: list[str] = []

    for entry in panel.roles:
        role = guild.get_role(
            entry.role_id
        )
        role_name = (
            role.mention
            if role is not None
            else f"（已刪除 {entry.role_id}）"
        )

        lines.append(
            f"• {role_name} — {entry.description}"
        )

    for field_name, field_value in split_role_lines(
        lines
    ):
        embed.add_field(
            name=field_name,
            value=field_value,
            inline=False,
        )

    return embed


# ── Persistent View ──────────────────────

class RolePanelView(discord.ui.View):
    """身分組自助領取 Persistent View。"""

    def __init__(
        self,
        roles: tuple[RoleButtonData, ...],
    ) -> None:
        super().__init__(
            timeout=None
        )

        for entry in roles[:MAX_PANEL_ROLES]:
            self.add_item(
                RoleButton(entry)
            )


class RoleButton(discord.ui.Button):
    """單一身分組切換按鈕。"""

    def __init__(
        self,
        entry: RoleButtonData,
    ) -> None:
        super().__init__(
            label=entry.label,
            style=parse_button_style(
                entry.style
            ),
            emoji=entry.emoji,
            custom_id=(
                f"role:{entry.role_id}"
            ),
        )

        self.role_id = entry.role_id

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """切換 Interaction 使用者的指定身分組。"""

        guild = interaction.guild
        member = interaction.user

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
            return

        role = guild.get_role(
            self.role_id
        )
        bot_member = guild.me

        if role is None:
            await interaction.response.send_message(
                "此身分組已不存在。",
                ephemeral=True,
            )
            return

        if (
            bot_member is None
            or role.is_default()
            or role.managed
            or role >= bot_member.top_role
        ):
            await interaction.response.send_message(
                "此身分組無法透過自助面板管理。",
                ephemeral=True,
            )
            return

        try:
            if role in member.roles:
                await member.remove_roles(
                    role,
                    reason="身分組面板自助移除",
                )
                message = (
                    f"已移除身分組：**{role.name}**"
                )
            else:
                await member.add_roles(
                    role,
                    reason="身分組面板自助領取",
                )
                message = (
                    f"已獲得身分組：**{role.name}**"
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "Bot 缺少管理身分組的權限，或身分組階層高於 Bot。",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            logger.exception(
                "身分組自助切換失敗 guild_id=%s member_id=%s role_id=%s",
                guild.id,
                member.id,
                role.id,
            )
            await interaction.response.send_message(
                "身分組操作失敗。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )


# ── Role Panel Service ──────────────────────

class RolePanelService:
    """管理身分組面板及其 Persistent View。"""

    def __init__(
        self,
        bot: commands.Bot,
        database: RoleDatabase,
    ) -> None:
        self.bot = bot
        self.database = database
        self._views: list[
            RolePanelView
        ] = []

    async def load_persistent_views(
        self,
    ) -> None:
        """從 Database 重建所有 Persistent View。"""

        count = 0

        for panel in self.database.get_all_panels():
            try:
                self._register_view(
                    panel
                )
                count += 1
            except Exception:
                logger.exception(
                    "身分組 Persistent View 重建失敗 message_id=%s",
                    panel.message_id,
                )

        logger.info(
            "已重建 %d 個身分組面板 View",
            count,
        )

    def close(self) -> None:
        """停止本次 Module Load 建立的 Runtime View。"""

        for view in self._views:
            view.stop()

        self._views.clear()

    async def create_panel(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        description: str,
    ) -> None:
        """在目前頻道建立公開身分組面板。"""

        guild = interaction.guild
        channel = interaction.channel

        if (
            guild is None
            or not isinstance(
                channel,
                discord.TextChannel,
            )
        ):
            await self._respond(
                interaction,
                "身分組面板只能建立在一般文字頻道。",
            )
            return

        title = title.strip()
        description = description.strip()

        if (
            not title
            or len(title) > MAX_PANEL_TITLE_LENGTH
            or not description
            or len(description) > MAX_PANEL_DESCRIPTION_LENGTH
        ):
            await self._respond(
                interaction,
                "面板標題或說明長度不符合限制。",
            )
            return

        empty_panel = RolePanelData(
            panel_id=0,
            guild_id=guild.id,
            channel_id=channel.id,
            message_id=0,
            title=title,
            description=description,
            roles=(),
        )

        try:
            message = await channel.send(
                embed=build_panel_embed(
                    empty_panel,
                    guild,
                ),
                view=RolePanelView(()),
            )
        except discord.HTTPException:
            logger.exception(
                "身分組面板建立失敗 guild_id=%s channel_id=%s",
                guild.id,
                channel.id,
            )
            await self._respond(
                interaction,
                "建立身分組面板失敗。",
            )
            return

        self.database.save_panel(
            guild_id=guild.id,
            channel_id=channel.id,
            message_id=message.id,
            title=title,
            description=description,
            roles=(),
        )

        panel = self.database.get_panel_by_message(
            message.id
        )

        if panel is not None:
            self._register_view(
                panel
            )

        await self._respond(
            interaction,
            (
                f"面板已建立（訊息 ID：`{message.id}`）。\n"
                "再次使用 `/roles` 並選擇「新增身分組」即可加入按鈕。"
            ),
        )

    async def add_role(
        self,
        interaction: discord.Interaction,
        *,
        message_id: str,
        role: discord.Role,
        label: str | None,
        emoji: str | None,
        description: str,
        style: str,
    ) -> None:
        """將身分組按鈕加入既有面板。"""

        panel = await self._resolve_panel(
            interaction,
            message_id,
        )

        if panel is None:
            return

        guild = interaction.guild
        member = interaction.user

        if (
            guild is None
            or not isinstance(
                member,
                discord.Member,
            )
        ):
            return

        bot_member = guild.me

        if (
            bot_member is None
            or role.is_default()
            or role.managed
            or role >= bot_member.top_role
            or (
                member.id != guild.owner_id
                and role >= member.top_role
            )
        ):
            await self._respond(
                interaction,
                "無法將預設、整合管理、高於 Bot，或不低於你的身分組加入面板。",
            )
            return

        if any(
            entry.role_id == role.id
            for entry in panel.roles
        ):
            await self._respond(
                interaction,
                "此身分組已在面板中。",
            )
            return

        if len(panel.roles) >= MAX_PANEL_ROLES:
            await self._respond(
                interaction,
                f"每個面板最多 {MAX_PANEL_ROLES} 個身分組。",
            )
            return

        button_label = (
            label.strip()
            if label and label.strip()
            else role.name
        )
        role_description = (
            description.strip()
        )

        if len(button_label) > MAX_BUTTON_LABEL_LENGTH:
            await self._respond(
                interaction,
                f"按鈕文字不可超過 {MAX_BUTTON_LABEL_LENGTH} 個字元。",
            )
            return

        if len(role_description) > MAX_ROLE_DESCRIPTION_LENGTH:
            await self._respond(
                interaction,
                f"身分組說明不可超過 {MAX_ROLE_DESCRIPTION_LENGTH} 個字元。",
            )
            return

        if style not in {
            "primary",
            "secondary",
            "success",
            "danger",
        }:
            await self._respond(
                interaction,
                "按鈕樣式必須是 primary、secondary、success 或 danger。",
            )
            return

        roles = (
            *panel.roles,
            RoleButtonData(
                role_id=role.id,
                label=button_label,
                emoji=emoji.strip() if emoji else None,
                description=role_description,
                style=style,
            ),
        )

        updated = RolePanelData(
            panel_id=panel.panel_id,
            guild_id=panel.guild_id,
            channel_id=panel.channel_id,
            message_id=panel.message_id,
            title=panel.title,
            description=panel.description,
            roles=roles,
        )

        if not await self._update_public_panel(
            interaction,
            updated,
        ):
            return

        self.database.save_panel(
            guild_id=updated.guild_id,
            channel_id=updated.channel_id,
            message_id=updated.message_id,
            title=updated.title,
            description=updated.description,
            roles=updated.roles,
        )
        self._register_view(
            updated
        )

        await self._respond(
            interaction,
            f"已新增身分組 {role.mention} 至面板。",
        )

    async def remove_role(
        self,
        interaction: discord.Interaction,
        *,
        message_id: str,
        role: discord.Role,
    ) -> None:
        """從既有面板移除身分組按鈕。"""

        panel = await self._resolve_panel(
            interaction,
            message_id,
        )

        if panel is None:
            return

        roles = tuple(
            entry
            for entry in panel.roles
            if entry.role_id != role.id
        )

        if len(roles) == len(panel.roles):
            await self._respond(
                interaction,
                "此身分組不在面板中。",
            )
            return

        updated = RolePanelData(
            panel_id=panel.panel_id,
            guild_id=panel.guild_id,
            channel_id=panel.channel_id,
            message_id=panel.message_id,
            title=panel.title,
            description=panel.description,
            roles=roles,
        )

        if not await self._update_public_panel(
            interaction,
            updated,
        ):
            return

        self.database.save_panel(
            guild_id=updated.guild_id,
            channel_id=updated.channel_id,
            message_id=updated.message_id,
            title=updated.title,
            description=updated.description,
            roles=updated.roles,
        )
        self._register_view(
            updated
        )

        await self._respond(
            interaction,
            f"已從面板移除身分組 {role.mention}。",
        )

    async def delete_panel(
        self,
        interaction: discord.Interaction,
        *,
        message_id: str,
    ) -> None:
        """刪除公開面板訊息與 Database 紀錄。"""

        panel = await self._resolve_panel(
            interaction,
            message_id,
        )

        if panel is None:
            return

        guild = interaction.guild

        if guild is None:
            return

        channel = guild.get_channel(
            panel.channel_id
        )

        if isinstance(
            channel,
            discord.TextChannel,
        ):
            try:
                message = await channel.fetch_message(
                    panel.message_id
                )
                await message.delete()
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                logger.warning(
                    "刪除身分組面板公開訊息失敗 message_id=%s",
                    panel.message_id,
                )

        self.database.delete_panel(
            panel.message_id
        )

        await self._respond(
            interaction,
            "面板已刪除。",
        )

    async def list_panels(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """列出目前 Guild 的身分組面板。"""

        guild = interaction.guild

        if guild is None:
            await self._respond(
                interaction,
                "此功能只限伺服器使用。",
            )
            return

        panels = self.database.get_panels(
            guild.id
        )

        embed = discord.Embed(
            title="身分組面板清單",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        if not panels:
            embed.description = (
                "目前無任何身分組面板。\n"
                "使用 `/roles` 並選擇「建立面板」建立第一個。"
            )
        else:
            embed.description = "\n\n".join(
                (
                    f"**{panel.title}** — "
                    f"{len(panel.roles)} 個身分組\n"
                    f"訊息 ID：`{panel.message_id}` | "
                    f"<#{panel.channel_id}>"
                )
                for panel in panels
            )

        await self._respond(
            interaction,
            embed=embed,
        )

    # ── Discord Message ──────────────────────

    async def _update_public_panel(
        self,
        interaction: discord.Interaction,
        panel: RolePanelData,
    ) -> bool:
        """更新既有公開身分組面板。"""

        guild = interaction.guild

        if guild is None:
            return False

        channel = guild.get_channel(
            panel.channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await self._respond(
                interaction,
                "面板所在頻道已不存在或類型錯誤。",
            )
            return False

        try:
            message = await channel.fetch_message(
                panel.message_id
            )
            await message.edit(
                embed=build_panel_embed(
                    panel,
                    guild,
                ),
                view=RolePanelView(
                    panel.roles
                ),
            )
        except discord.HTTPException:
            logger.exception(
                "身分組面板更新失敗 message_id=%s",
                panel.message_id,
            )
            await self._respond(
                interaction,
                "更新面板失敗，請確認訊息、Bot 權限與按鈕資料。",
            )
            return False

        return True

    def _register_view(
        self,
        panel: RolePanelData,
    ) -> None:
        """註冊指定面板的 Persistent View。"""

        view = RolePanelView(
            panel.roles
        )
        self.bot.add_view(
            view,
            message_id=panel.message_id,
        )
        self._views.append(
            view
        )

    # ── Resolution ──────────────────────

    async def _resolve_panel(
        self,
        interaction: discord.Interaction,
        message_id: str,
    ) -> RolePanelData | None:
        """驗證訊息 ID 並取得目前 Guild 的面板。"""

        try:
            parsed_id = int(
                message_id
            )
        except ValueError:
            await self._respond(
                interaction,
                "訊息 ID 格式錯誤，請輸入純數字。",
            )
            return None

        panel = self.database.get_panel_by_message(
            parsed_id
        )

        if (
            panel is None
            or interaction.guild_id is None
            or panel.guild_id != interaction.guild_id
        ):
            await self._respond(
                interaction,
                "找不到此面板，請確認訊息 ID 與所在伺服器。",
            )
            return None

        return panel

    # ── Interaction ──────────────────────

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
