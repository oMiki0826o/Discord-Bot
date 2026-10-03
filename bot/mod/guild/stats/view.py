"""
bot/mod/guild/stats/view.py

Modification():

- Interactive `/server` views for statistic channel management。
"""

from __future__ import annotations

import discord

from bot.mod.guild.stats.model import StatChannel, StatMetric
from bot.mod.guild.stats.repository import GuildStatsRepository
from bot.mod.guild.stats.service import GuildStatsService


def _can_manage(interaction: discord.Interaction) -> bool:
    return (
        isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_channels
    )


class StatsConfigModal(discord.ui.Modal, title="設定統計頻道"):
    metric = discord.ui.TextInput(
        label="統計類型",
        placeholder="member_total / human_total / bot_total / online_total / role_members / delete",
        max_length=32,
    )
    label_template = discord.ui.TextInput(
        label="頻道名稱格式",
        placeholder="成員數：{count}",
        max_length=100,
    )
    role_id = discord.ui.TextInput(
        label="身分組 ID（只有 role_members 需要）",
        required=False,
        max_length=24,
    )

    def __init__(
        self,
        *,
        channel: discord.abc.GuildChannel,
        repository: GuildStatsRepository,
        service: GuildStatsService,
        max_channels: int,
    ) -> None:
        super().__init__()
        self.channel = channel
        self.repository = repository
        self.service = service
        self.max_channels = max_channels

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理頻道」權限。", ephemeral=True)
            return
        try:
            metric_text = str(self.metric).strip().lower()
            role_id = int(str(self.role_id).strip() or 0)
            if metric_text == "delete":
                self.repository.delete(interaction.guild.id, self.channel.id)
                await interaction.response.send_message("已移除此統計頻道設定。", ephemeral=True)
                return
            metric = StatMetric(metric_text)
            value = StatChannel(
                interaction.guild.id,
                self.channel.id,
                metric,
                str(self.label_template).strip(),
                role_id=role_id,
            )
            existing = self.repository.list_for_guild(interaction.guild.id)
            if (
                all(item.channel_id != self.channel.id for item in existing)
                and len(existing) >= self.max_channels
            ):
                raise ValueError(f"統計頻道最多只能設定 {self.max_channels} 個")
            self.repository.upsert(value)
            report = await self.service.refresh_guild(interaction.guild, force=True)
        except (ValueError, TypeError) as exc:
            await interaction.response.send_message(f"設定錯誤：{exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"統計頻道已儲存；更新={report.updated}，失敗={report.failed}。",
            ephemeral=True,
        )


class StatsChannelSelect(discord.ui.ChannelSelect):
    def __init__(
        self,
        repository: GuildStatsRepository,
        service: GuildStatsService,
        max_channels: int,
    ) -> None:
        super().__init__(
            placeholder="選擇要設定的語音頻道",
            channel_types=[discord.ChannelType.voice],
            min_values=1,
            max_values=1,
        )
        self.repository = repository
        self.service = service
        self.max_channels = max_channels

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理頻道」權限。", ephemeral=True)
            return
        await interaction.response.send_modal(
            StatsConfigModal(
                channel=self.values[0], repository=self.repository,
                service=self.service, max_channels=self.max_channels,
            )
        )


class StatsManagementView(discord.ui.View):
    def __init__(
        self,
        *,
        repository: GuildStatsRepository,
        service: GuildStatsService,
        user_id: int,
        timeout: float,
        max_channels: int,
    ) -> None:
        super().__init__(timeout=timeout)
        self.repository = repository
        self.service = service
        self.user_id = user_id
        self.add_item(StatsChannelSelect(repository, service, max_channels))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("這不是你的設定面板。", ephemeral=True)
        return False

    @discord.ui.button(label="立即更新全部", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.guild is None or not _can_manage(interaction):
            await interaction.response.send_message("你需要「管理頻道」權限。", ephemeral=True)
            return
        report = await self.service.refresh_guild(interaction.guild, force=True)
        await interaction.response.send_message(
            f"更新={report.updated}、未變更={report.unchanged}、失敗={report.failed}",
            ephemeral=True,
        )
