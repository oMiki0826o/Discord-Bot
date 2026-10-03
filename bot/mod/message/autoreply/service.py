"""
bot/mod/message/autoreply/service.py

Modification():

- Discord message event adapter for auto-reply rules。
"""

from __future__ import annotations

import time
from typing import Any

import discord

from bot.core.logging.manager import LogManager
from bot.mod.message.autoreply.matcher import AutoReplyMatcher, MatchInput
from bot.mod.message.autoreply.repository import AutoReplyRepository


logger = LogManager().get_logger("message.autoreply.service")


class AutoReplyService:
    def __init__(self, repository: AutoReplyRepository, matcher: AutoReplyMatcher) -> None:
        self.repository = repository
        self.matcher = matcher

    async def handle_message(self, message: Any) -> None:
        guild = getattr(message, "guild", None)
        author = getattr(message, "author", None)
        channel = getattr(message, "channel", None)
        content = getattr(message, "content", "")
        if (
            guild is None
            or author is None
            or channel is None
            or getattr(author, "bot", False)
            or getattr(message, "webhook_id", None) is not None
            or not content
        ):
            return
        document = self.repository.load(guild.id)
        found = self.matcher.find(
            document,
            MatchInput(
                guild_id=guild.id,
                channel_id=channel.id,
                user_id=author.id,
                content=content,
                user_name=getattr(author, "display_name", str(author)),
                user_mention=getattr(author, "mention", str(author)),
                channel_mention=getattr(channel, "mention", getattr(channel, "name", "頻道")),
                guild_name=guild.name,
            ),
            now=time.monotonic(),
        )
        if found is None:
            return
        try:
            await message.reply(
                found.rendered_response,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound):
            logger.warning("無法發送自動回覆 guild=%s channel=%s", guild.id, channel.id)
        except discord.HTTPException:
            logger.exception("自動回覆 Discord HTTP 錯誤 guild=%s rule=%s", guild.id, found.rule_id)
