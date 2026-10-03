"""
bot/mod/guild/announcement/view.py

Modification():

- Interactive `/server` views for announcement management。
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import discord

from bot.mod.guild.announcement.model import Announcement, AnnouncementStatus
from bot.mod.guild.announcement.repository import AnnouncementRepository
from bot.mod.guild.announcement.service import AnnouncementService


def _can_manage(interaction: discord.Interaction) -> bool:
    return (
        isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_guild
    )


class AnnouncementModal(discord.ui.Modal, title="建立公告"):
    announcement_title = discord.ui.TextInput(label="標題", max_length=256)
    content = discord.ui.TextInput(label="內容", style=discord.TextStyle.paragraph, max_length=4000)
    image_url = discord.ui.TextInput(label="圖片 URL（可留空）", required=False, max_length=1000)
    mention_role_id = discord.ui.TextInput(label="提及身分組 ID（可留空）", required=False, max_length=24)
    scheduled_at = discord.ui.TextInput(
        label="排程時間（ISO 8601；留空立即發佈）",
        required=False,
        placeholder="2026-10-03T20:00:00+08:00",
        max_length=40,
    )

    def __init__(
        self,
        *,
        channel: discord.abc.GuildChannel,
        repository: AnnouncementRepository,
        service: AnnouncementService,
    ) -> None:
        super().__init__()
        self.channel = channel
        self.repository = repository
        self.service = service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理伺服器」權限。", ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        try:
            role_id = int(str(self.mention_role_id).strip() or 0)
            schedule_text = str(self.scheduled_at).strip()
            when = datetime.fromisoformat(schedule_text) if schedule_text else now
            if when.tzinfo is None:
                raise ValueError("排程時間必須包含時區")
            value = Announcement(
                id=uuid.uuid4().hex[:12],
                guild_id=interaction.guild.id,
                author_id=interaction.user.id,
                target_channel_id=self.channel.id,
                mention_role_id=role_id,
                title=str(self.announcement_title),
                content=str(self.content),
                color=0x5865F2,
                image_url=str(self.image_url).strip(),
                status=AnnouncementStatus.DRAFT,
                created_at=now,
                updated_at=now,
            )
            value.validate()
            if role_id and interaction.guild.get_role(role_id) is None:
                raise ValueError("找不到提及身分組")
            self.repository.create(value)
            self.repository.schedule(interaction.guild.id, value.id, when.astimezone(timezone.utc))
        except (ValueError, TypeError) as exc:
            await interaction.response.send_message(f"公告設定錯誤：{exc}", ephemeral=True)
            return
        timing = "已排程" if schedule_text else "已加入立即發佈佇列"
        await interaction.response.send_message(
            content=f"{timing}，公告 ID：`{value.id}`",
            embed=self.service.build_embed(value),
            ephemeral=True,
        )


class AnnouncementChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, repository: AnnouncementRepository, service: AnnouncementService) -> None:
        super().__init__(
            placeholder="選擇公告目標頻道",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
        )
        self.repository = repository
        self.service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理伺服器」權限。", ephemeral=True)
            return
        await interaction.response.send_modal(
            AnnouncementModal(
                channel=self.values[0], repository=self.repository, service=self.service
            )
        )


class AnnouncementActionModal(discord.ui.Modal, title="公告操作"):
    announcement_id = discord.ui.TextInput(label="公告 ID", max_length=64)
    action = discord.ui.TextInput(label="操作", placeholder="cancel 或 retry", max_length=10)

    def __init__(self, repository: AnnouncementRepository) -> None:
        super().__init__()
        self.repository = repository

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None or not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理伺服器」權限。", ephemeral=True)
            return
        action = str(self.action).strip().lower()
        announcement_id = str(self.announcement_id).strip()
        try:
            if action == "cancel":
                success = self.repository.cancel(interaction.guild_id, announcement_id)
                if not success:
                    raise ValueError("公告不存在或無法取消")
            elif action == "retry":
                self.repository.schedule(
                    interaction.guild_id, announcement_id, datetime.now(timezone.utc)
                )
            else:
                raise ValueError("操作只能是 cancel 或 retry")
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message("公告狀態已更新。", ephemeral=True)


class AnnouncementManagementView(discord.ui.View):
    def __init__(
        self,
        *,
        repository: AnnouncementRepository,
        service: AnnouncementService,
        user_id: int,
        timeout: float,
    ) -> None:
        super().__init__(timeout=timeout)
        self.repository = repository
        self.service = service
        self.user_id = user_id
        self.add_item(AnnouncementChannelSelect(repository, service))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("這不是你的設定面板。", ephemeral=True)
        return False

    @discord.ui.button(label="公告紀錄", style=discord.ButtonStyle.secondary)
    async def history(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.guild_id is None or not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理伺服器」權限。", ephemeral=True)
            return
        values = self.repository.list_history(interaction.guild_id, limit=20)
        text = "\n".join(
            f"`{item.id}` {item.status.value}｜{item.title[:50]}" for item in values
        ) or "目前沒有公告紀錄。"
        await interaction.response.send_message(text[:2000], ephemeral=True)

    @discord.ui.button(label="取消／重試", style=discord.ButtonStyle.secondary)
    async def action(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(AnnouncementActionModal(self.repository))
