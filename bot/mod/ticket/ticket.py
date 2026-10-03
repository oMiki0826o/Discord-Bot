"""
bot/mod/ticket/ticket.py

Modification():

- 實作工單建立、關閉、成員加入與移除。
- 實作工單冷卻與每位使用者最大開票數限制。
- 建立工單私人頻道與支援身分組權限。
- 處理工單關閉後的封存或刪除流程。
- 管理工單建立與關閉 Persistent View。

本檔負責 Ticket Module 的核心工單業務邏輯。
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands

from bot.mod.ticket.database import (
    TicketDatabase,
    TicketRecord,
)


logger = logging.getLogger(
    "bot.mod.ticket.ticket"
)


# ── Ticket Service ──────────────────────

class TicketService:
    """執行 Ticket Module 的工單業務邏輯。"""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        database: TicketDatabase,
        cooldown_seconds: int,
        max_per_user: int,
        channel_prefix: str,
        category_name: str,
        archive_category: str,
        close_delay_seconds: int,
        panel_title: str,
        panel_description: str,
    ) -> None:
        self.bot = bot
        self.database = database
        self.cooldown_seconds = cooldown_seconds
        self.max_per_user = max_per_user
        self.channel_prefix = channel_prefix
        self.category_name = category_name
        self.archive_category = archive_category
        self.close_delay_seconds = close_delay_seconds
        self.panel_title = panel_title
        self.panel_description = panel_description
        self._user_last_ticket: dict[
            tuple[int, int],
            float,
        ] = {}
        self._views: list[
            discord.ui.View
        ] = []

    # ── Lifecycle ──────────────────────

    def register_persistent_views(
        self,
    ) -> None:
        """註冊固定 custom_id 的工單 Persistent View。"""

        close_view = CloseTicketView(
            self
        )
        panel_view = TicketPanelView(
            self
        )

        self.bot.add_view(
            close_view
        )
        self.bot.add_view(
            panel_view
        )
        self._views.extend(
            [
                close_view,
                panel_view,
            ]
        )

    def close(self) -> None:
        """停止本次 Module Load 建立的 Runtime View。"""

        for view in self._views:
            view.stop()

        self._views.clear()
        self._user_last_ticket.clear()

    # ── Open Ticket ──────────────────────

    async def open_ticket(
        self,
        interaction: discord.Interaction,
        *,
        topic: str = "",
    ) -> None:
        """建立新的私人 Ticket 頻道。"""

        guild = interaction.guild
        user = interaction.user

        if (
            guild is None
            or not isinstance(
                user,
                discord.Member,
            )
        ):
            await self._respond(
                interaction,
                "此功能只限伺服器成員使用。",
            )
            return

        bot_member = guild.me

        if (
            bot_member is None
            or not bot_member.guild_permissions.manage_channels
        ):
            await self._respond(
                interaction,
                "Bot 缺少「管理頻道」權限。",
            )
            return

        key = (
            guild.id,
            user.id,
        )
        now = time.monotonic()
        last = self._user_last_ticket.get(
            key,
            0.0,
        )
        remaining = (
            self.cooldown_seconds
            - (now - last)
        )

        if remaining > 0:
            await self._respond(
                interaction,
                f"請等待 {int(remaining) + 1} 秒後再建立工單。",
            )
            return

        open_tickets = (
            self.database.get_open_tickets_by_user(
                guild.id,
                user.id,
            )
        )

        if len(open_tickets) >= self.max_per_user:
            await self._respond(
                interaction,
                (
                    f"你已有 {len(open_tickets)} 張開啟中的工單"
                    f"（上限 {self.max_per_user} 張）。"
                ),
            )
            return

        settings = (
            self.database.get_guild_settings(
                guild.id
            )
        )
        ticket_number = (
            self.database.next_ticket_number(
                guild.id
            )
        )
        channel_name = (
            f"{self.channel_prefix}"
            f"{ticket_number:04d}"
        )

        category = self._resolve_category(
            guild,
            settings.category_id,
        )
        support_role = (
            guild.get_role(
                settings.support_role_id
            )
            if settings.support_role_id
            else None
        )

        overwrites: dict[
            discord.Role | discord.Member,
            discord.PermissionOverwrite,
        ] = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }

        if support_role is not None:
            overwrites[
                support_role
            ] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

        if not interaction.response.is_done():
            await interaction.response.defer(
                ephemeral=True
            )

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category,
                topic=(
                    f"工單由 {user} 建立｜{topic}"
                    if topic
                    else f"工單由 {user} 建立"
                ),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Bot 缺少建立頻道的權限。",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.exception(
                "工單頻道建立失敗 guild_id=%s user_id=%s",
                guild.id,
                user.id,
            )
            await interaction.followup.send(
                "建立工單失敗。",
                ephemeral=True,
            )
            return

        try:
            ticket_id = self.database.create_ticket(
                guild_id=guild.id,
                channel_id=channel.id,
                user_id=user.id,
                topic=topic,
            )
        except Exception:
            logger.exception(
                "工單 DB 建立失敗 guild_id=%s channel_id=%s",
                guild.id,
                channel.id,
            )
            try:
                await channel.delete(
                    reason="Ticket DB 建立失敗，回滾頻道"
                )
            except discord.HTTPException:
                logger.exception(
                    "工單建立回滾失敗 channel_id=%s",
                    channel.id,
                )

            await interaction.followup.send(
                "建立工單資料失敗，已嘗試回滾頻道。",
                ephemeral=True,
            )
            return

        self._user_last_ticket[
            key
        ] = time.monotonic()

        embed = discord.Embed(
            title=(
                f"工單 #{ticket_number:04d}"
            ),
            description=(
                f"您好 {user.mention}，感謝您建立工單！\n\n"
                + (
                    f"**主題**：{topic}\n"
                    if topic
                    else ""
                )
                + "支援人員將會盡快協助您。\n\n"
                + "完成後請點擊下方「關閉工單」按鈕。"
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=f"工單 ID：{ticket_id}"
        )

        try:
            await channel.send(
                content=user.mention,
                embed=embed,
                view=CloseTicketView(
                    self
                ),
            )
        except discord.HTTPException:
            logger.exception(
                "工單歡迎訊息發送失敗 ticket_id=%s channel_id=%s",
                ticket_id,
                channel.id,
            )

        await interaction.followup.send(
            f"工單已建立：{channel.mention}",
            ephemeral=True,
        )

        logger.info(
            "工單建立 guild_id=%s channel_id=%s user_id=%s ticket_id=%s",
            guild.id,
            channel.id,
            user.id,
            ticket_id,
        )

    # ── Close Ticket ──────────────────────

    async def close_ticket(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """關閉目前 Ticket 頻道。"""

        channel = interaction.channel
        guild = interaction.guild
        member = interaction.user

        if (
            guild is None
            or not isinstance(
                channel,
                discord.TextChannel,
            )
            or not isinstance(
                member,
                discord.Member,
            )
        ):
            await self._respond(
                interaction,
                "此操作只限工單文字頻道使用。",
            )
            return

        ticket = self.database.get_ticket_by_channel(
            channel.id
        )

        if ticket is None:
            await self._respond(
                interaction,
                "此頻道不是工單頻道。",
            )
            return

        if ticket.status == "closed":
            await self._respond(
                interaction,
                "此工單已關閉。",
            )
            return

        settings = (
            self.database.get_guild_settings(
                guild.id
            )
        )
        support_role_id = (
            settings.support_role_id
        )
        is_support = (
            support_role_id != 0
            and any(
                role.id == support_role_id
                for role in member.roles
            )
        )

        can_close = (
            member.id == ticket.user_id
            or is_support
            or member.guild_permissions.manage_channels
        )

        if not can_close:
            await self._respond(
                interaction,
                "只有工單建立者、支援身分組或頻道管理者可以關閉工單。",
            )
            return

        bot_member = guild.me

        if (
            bot_member is None
            or not bot_member.guild_permissions.manage_channels
        ):
            await self._respond(
                interaction,
                "Bot 缺少「管理頻道」權限。",
            )
            return

        if not self.database.close_ticket(
            channel.id,
            member.id,
        ):
            await self._respond(
                interaction,
                "此工單已被其他人關閉。",
            )
            return

        await self._respond(
            interaction,
            (
                f"工單已由 {member.mention} 關閉，"
                f"頻道將在 {self.close_delay_seconds} 秒後封存或刪除。"
            ),
            ephemeral=False,
        )

        logger.info(
            "工單關閉 guild_id=%s channel_id=%s user_id=%s",
            guild.id,
            channel.id,
            member.id,
        )

        await asyncio.sleep(
            self.close_delay_seconds
        )
        await self._archive_or_delete(
            guild,
            channel,
        )

    # ── Member Access ──────────────────────

    async def add_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """將成員加入目前工單。"""

        if not await self._validate_ticket_channel(
            interaction
        ):
            return

        channel = interaction.channel
        assert isinstance(
            channel,
            discord.TextChannel,
        )

        try:
            await channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少設定頻道權限的能力。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "加入工單成員失敗 channel_id=%s member_id=%s",
                channel.id,
                member.id,
            )
            await self._respond(
                interaction,
                "加入工單成員失敗。",
            )
            return

        await self._respond(
            interaction,
            f"已將 {member.mention} 加入工單。",
            ephemeral=False,
        )

    async def remove_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """將成員從目前工單移除。"""

        ticket = await self._validate_ticket_channel(
            interaction
        )

        if ticket is None:
            return

        if member.id == ticket.user_id:
            await self._respond(
                interaction,
                "不能移除工單建立者；若要結束工單請使用關閉功能。",
            )
            return

        channel = interaction.channel
        assert isinstance(
            channel,
            discord.TextChannel,
        )

        try:
            await channel.set_permissions(
                member,
                overwrite=None,
            )
        except discord.Forbidden:
            await self._respond(
                interaction,
                "Bot 缺少設定頻道權限的能力。",
            )
            return
        except discord.HTTPException:
            logger.exception(
                "移除工單成員失敗 channel_id=%s member_id=%s",
                channel.id,
                member.id,
            )
            await self._respond(
                interaction,
                "移除工單成員失敗。",
            )
            return

        await self._respond(
            interaction,
            f"已將 {member.mention} 從工單移除。",
            ephemeral=False,
        )

    # ── Stats / Panel ──────────────────────

    async def stats(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """顯示目前 Guild 的工單統計。"""

        guild = interaction.guild

        if guild is None:
            return

        stats = self.database.get_guild_stats(
            guild.id
        )

        embed = discord.Embed(
            title="工單統計",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="總工單數",
            value=str(stats.total),
            inline=True,
        )
        embed.add_field(
            name="開啟中",
            value=str(stats.open_count),
            inline=True,
        )
        embed.add_field(
            name="已關閉",
            value=str(stats.closed_count),
            inline=True,
        )

        await self._respond(
            interaction,
            embed=embed,
        )

    async def send_panel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """在目前頻道發送公開工單建立面板。"""

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await self._respond(
                interaction,
                "工單面板只能發送到一般文字頻道。",
            )
            return

        embed = discord.Embed(
            title=self.panel_title,
            description=self.panel_description,
            color=discord.Color.green(),
        )

        try:
            await channel.send(
                embed=embed,
                view=TicketPanelView(
                    self
                ),
            )
        except discord.HTTPException:
            logger.exception(
                "工單公開面板發送失敗 channel_id=%s",
                channel.id,
            )
            await self._respond(
                interaction,
                "工單面板發送失敗。",
            )
            return

        await self._respond(
            interaction,
            "工單面板已發送。",
        )

    # ── Guild Settings ──────────────────────

    async def set_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None,
    ) -> None:
        """設定工單建立類別。"""

        guild = interaction.guild

        if guild is None:
            return

        self.database.set_guild_setting(
            guild.id,
            "category_id",
            category.id if category else 0,
        )

        await self._respond(
            interaction,
            (
                f"工單類別已設定為 **{category.name}**。"
                if category
                else "工單指定類別已停用，將依類別名稱尋找。"
            ),
        )

    async def set_support_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role | None,
    ) -> None:
        """設定 Ticket Module 支援身分組。"""

        guild = interaction.guild

        if guild is None:
            return

        if role is not None and (
            role.is_default()
            or role.managed
        ):
            await self._respond(
                interaction,
                "此身分組不能作為工單支援身分組。",
            )
            return

        self.database.set_guild_setting(
            guild.id,
            "support_role_id",
            role.id if role else 0,
        )

        await self._respond(
            interaction,
            (
                f"支援身分組已設定為 {role.mention}。"
                if role
                else "工單支援身分組已停用。"
            ),
        )

    # ── Internal Helpers ──────────────────────

    def _resolve_category(
        self,
        guild: discord.Guild,
        category_id: int,
    ) -> discord.CategoryChannel | None:
        """依 Guild 設定或預設名稱解析工單類別。"""

        if category_id:
            channel = guild.get_channel(
                category_id
            )
            if isinstance(
                channel,
                discord.CategoryChannel,
            ):
                return channel

        return discord.utils.get(
            guild.categories,
            name=self.category_name,
        )

    async def _archive_or_delete(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
    ) -> None:
        """依設定封存工單；未設定或封存失敗則刪除。"""

        if self.archive_category:
            archive = discord.utils.get(
                guild.categories,
                name=self.archive_category,
            )

            if archive is None:
                try:
                    archive = await guild.create_category(
                        self.archive_category
                    )
                except discord.HTTPException:
                    logger.exception(
                        "工單封存類別建立失敗 guild_id=%s",
                        guild.id,
                    )

            if archive is not None:
                bot_member = guild.me

                overwrites: dict[
                    discord.Role | discord.Member,
                    discord.PermissionOverwrite,
                ] = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=False
                    ),
                }

                if bot_member is not None:
                    overwrites[
                        bot_member
                    ] = discord.PermissionOverwrite(
                        view_channel=True,
                        manage_channels=True,
                        read_message_history=True,
                    )

                try:
                    await channel.edit(
                        category=archive,
                        overwrites=overwrites,
                        reason="工單關閉封存",
                    )
                    return
                except discord.HTTPException:
                    logger.exception(
                        "工單封存失敗 channel_id=%s",
                        channel.id,
                    )

        try:
            await channel.delete(
                reason="工單關閉"
            )
        except discord.HTTPException:
            logger.exception(
                "工單頻道刪除失敗 channel_id=%s",
                channel.id,
            )

    async def _validate_ticket_channel(
        self,
        interaction: discord.Interaction,
    ) -> TicketRecord | None:
        """確認目前頻道為開啟中的 Ticket。"""

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            await self._respond(
                interaction,
                "此操作只限工單文字頻道使用。",
            )
            return None

        ticket = self.database.get_ticket_by_channel(
            channel.id
        )

        if ticket is None:
            await self._respond(
                interaction,
                "此頻道不是工單頻道。",
            )
            return None

        if ticket.status != "open":
            await self._respond(
                interaction,
                "此工單已關閉。",
            )
            return None

        return ticket

    @staticmethod
    async def _respond(
        interaction: discord.Interaction,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = True,
    ) -> None:
        """依 Interaction 狀態選擇 Response 或 Followup。"""

        if interaction.response.is_done():
            await interaction.followup.send(
                content=content,
                embed=embed,
                ephemeral=ephemeral,
            )
            return

        await interaction.response.send_message(
            content=content,
            embed=embed,
            ephemeral=ephemeral,
        )


# ── Persistent Close View ──────────────────────

class CloseTicketView(discord.ui.View):
    """工單頻道的持久化關閉按鈕。"""

    def __init__(
        self,
        service: TicketService,
    ) -> None:
        super().__init__(
            timeout=None
        )
        self.service = service

    @discord.ui.button(
        label="關閉工單",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close",
    )
    async def close_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """要求使用者確認關閉目前工單。"""

        await interaction.response.send_message(
            embed=discord.Embed(
                title="確認關閉工單",
                description="工單將在確認後封存或刪除，請確認問題已處理完成。",
                color=discord.Color.orange(),
            ),
            view=TicketCloseConfirmationView(
                service=self.service,
                user_id=interaction.user.id,
                timeout=60,
            ),
            ephemeral=True,
        )


# ── Persistent Open View ──────────────────────

class TicketPanelView(discord.ui.View):
    """公開工單建立面板的持久化按鈕。"""

    def __init__(
        self,
        service: TicketService,
    ) -> None:
        super().__init__(
            timeout=None
        )
        self.service = service

    @discord.ui.button(
        label="建立工單",
        style=discord.ButtonStyle.success,
        custom_id="ticket:open_panel",
    )
    async def open_panel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """開啟工單主題輸入 Modal。"""

        await interaction.response.send_modal(
            TicketTopicModal(
                self.service
            )
        )


class TicketTopicModal(
    discord.ui.Modal,
    title="建立工單",
):
    """收集工單主題。"""

    topic = discord.ui.TextInput(
        label="工單主題（選填）",
        placeholder="請簡單描述您的問題或需求",
        required=False,
        max_length=100,
        style=discord.TextStyle.paragraph,
    )

    def __init__(
        self,
        service: TicketService,
    ) -> None:
        super().__init__()
        self.service = service

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """建立使用者工單。"""

        await self.service.open_ticket(
            interaction,
            topic=str(
                self.topic.value
            ).strip(),
        )


class TicketCloseConfirmationView(
    discord.ui.View
):
    """確認 Persistent Button 發起的工單關閉。"""

    def __init__(
        self,
        *,
        service: TicketService,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.service = service
        self.user_id = user_id

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制只有發起者可以確認關閉。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的確認面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="確認關閉",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """關閉目前工單。"""

        await self.service.close_ticket(
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
        """取消關閉工單。"""

        await interaction.response.edit_message(
            content="已取消關閉工單。",
            embed=None,
            view=None,
        )
        self.stop()
