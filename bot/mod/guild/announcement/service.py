"""
bot/mod/guild/announcement/service.py

Modification():

- Safe Discord Embed and role-mention publisher。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import discord

from bot.mod.guild.announcement.model import Announcement


class PermanentAnnouncementError(RuntimeError):
    """Announcement cannot succeed without an administrator change."""


class TransientAnnouncementError(RuntimeError):
    """Announcement may succeed when retried later."""


@dataclass(frozen=True, slots=True)
class PublishedAnnouncement:
    message_id: int


class AnnouncementService:
    def build_embed(self, announcement: Announcement) -> discord.Embed:
        announcement.validate()
        embed = discord.Embed(
            title=announcement.title,
            description=announcement.content,
            color=discord.Color(announcement.color),
            timestamp=announcement.created_at,
        )
        if announcement.image_url:
            embed.set_image(url=announcement.image_url)
        embed.set_footer(text=f"公告 ID: {announcement.id}")
        return embed

    async def publish(self, guild: Any, announcement: Announcement) -> PublishedAnnouncement:
        channel = guild.get_channel(announcement.target_channel_id)
        if channel is None or not hasattr(channel, "send"):
            raise PermanentAnnouncementError("找不到公告目標頻道")
        content = None
        allowed_mentions = discord.AllowedMentions.none()
        if announcement.mention_role_id:
            role = guild.get_role(announcement.mention_role_id)
            if role is None:
                raise PermanentAnnouncementError("公告提及身分組不存在")
            content = role.mention
            allowed_mentions = discord.AllowedMentions(
                roles=[role], users=False, everyone=False, replied_user=False
            )
        try:
            message = await channel.send(
                content=content,
                embed=self.build_embed(announcement),
                allowed_mentions=allowed_mentions,
            )
        except (discord.Forbidden, discord.NotFound) as exc:
            raise PermanentAnnouncementError(str(exc)) from exc
        except discord.HTTPException as exc:
            raise TransientAnnouncementError(str(exc)) from exc
        return PublishedAnnouncement(message_id=message.id)
