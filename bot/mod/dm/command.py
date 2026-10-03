"""
bot/mod/dm/command.py

Modification():

- Discord event and Owner-command adapter for private-message forwarding。
"""

from __future__ import annotations

import logging
from typing import Any

from discord.ext import commands

from bot.core.discord.owner import resolve_owner

from .service import DMBridgeService, parse_reply_target


logger = logging.getLogger("bot.mod.dm")


class DMCog(commands.Cog):
    """Forward ordinary user DMs while preserving explicit Bot mentions for AI."""

    def __init__(self, bot: Any, bridge: DMBridgeService) -> None:
        self.bot = bot
        self.bridge = bridge

    @commands.Cog.listener()
    async def on_message(self, message: Any) -> None:
        """Forward an ordinary incoming DM; do not compete with a Bot mention."""

        if bool(getattr(getattr(message, "author", None), "bot", False) or getattr(message, "guild", None) is not None):
            return
        if self._mentions_bot(message):
            return
        if await self._is_owner(message.author):
            await self.handle_owner_reply(message)
            return
        self.bridge.remember_sender(str(message.author.id))
        await self._forward_to_owner(message)

    async def handle_owner_reply(self, message: Any) -> bool:
        """Bridge an Owner DM reply to the sender of its forwarded message."""

        reference = getattr(message, "reference", None)
        message_id = None if reference is None else getattr(reference, "message_id", None)
        if message_id is None or not await self._is_owner(message.author):
            return False
        sender_id = self.bridge.sender_for_forward(str(message_id))
        if sender_id is None:
            return False
        content = str(getattr(message, "content", "")).strip()
        attachments = tuple(getattr(message, "attachments", ()) or ())
        if not content and not attachments:
            return True
        target = await self._resolve_user(sender_id)
        if target is None:
            return True
        try:
            if content:
                await target.send(self.bridge.settings.owner_reply_prefix + content)
            for attachment in attachments:
                url = str(getattr(attachment, "url", "")).strip()
                if url:
                    await target.send(self.bridge.settings.owner_reply_prefix + "Attachment: " + url)
        except Exception:
            logger.exception("DM bridge reply failed target_id=%s", sender_id)
        return True

    @commands.group(name="dm", invoke_without_command=True)
    @commands.is_owner()
    async def dm_group(self, ctx: commands.Context) -> None:
        """Show the Owner DM bridge command summary."""

        await ctx.send("Available: dm reply [user_id] <content>, dm send <user> <content>")

    @dm_group.command(name="reply")
    @commands.is_owner()
    async def dm_reply(self, ctx: commands.Context, *, content: str) -> None:
        """Reply to a supplied Discord ID or to the latest ordinary DM sender."""

        try:
            explicit_target, text = parse_reply_target(content)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        target_id = explicit_target or self.bridge.last_sender_id
        if target_id is None:
            await ctx.send("No recent DM sender is available.")
            return
        if await self._send_text(target_id, text):
            target = await self._resolve_user(target_id)
            mention = getattr(target, "mention", f"`{target_id}`") if target is not None else f"`{target_id}`"
            await ctx.send(f"DM sent to {mention}.")
        else:
            await ctx.send(f"Unable to send a DM to `{target_id}`.")

    @dm_group.command(name="send")
    @commands.is_owner()
    async def dm_send(self, ctx: commands.Context, user: Any, *, content: str) -> None:
        """Proactively send a private message to a Discord-resolved user."""

        text = content.strip()
        if not text:
            await ctx.send("content must not be blank")
            return
        try:
            files = [await attachment.to_file() for attachment in getattr(ctx.message, "attachments", ())]
            await user.send(text, files=files)
        except Exception:
            logger.exception("Owner DM send failed target_id=%s", getattr(user, "id", "unknown"))
            await ctx.send("Unable to send the DM.")
            return
        await ctx.send(f"DM sent to {getattr(user, 'mention', user)}.")

    async def _forward_to_owner(self, message: Any) -> None:
        owner = await self._owner_user()
        if owner is None:
            return
        sender_id = str(message.author.id)
        content = str(getattr(message, "content", "")).strip()
        summary = f"**Incoming DM**\nFrom: {message.author} (ID: `{sender_id}`)"
        if content:
            summary += "\nContent: " + content
        try:
            forwarded = await owner.send(summary)
            self.bridge.remember_forward(str(forwarded.id), sender_id)
            for attachment in tuple(getattr(message, "attachments", ()) or ()):
                url = str(getattr(attachment, "url", "")).strip()
                if url:
                    await owner.send("Attachment: " + url)
        except Exception:
            logger.exception("DM forward failed sender_id=%s", sender_id)

    async def _send_text(self, target_id: str, content: str) -> bool:
        target = await self._resolve_user(target_id)
        if target is None:
            return False
        try:
            await target.send(self.bridge.settings.owner_reply_prefix + content)
        except Exception:
            logger.exception("Owner DM reply failed target_id=%s", target_id)
            return False
        return True

    async def _owner_user(self) -> Any | None:
        """Resolve the forwarding destination through the shared Owner policy."""
        try:
            return await resolve_owner(self.bot)
        except Exception:
            logger.exception("Owner lookup through shared policy failed")
            return None

    async def _resolve_user(self, user_id: str) -> Any | None:
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None
        user = self.bot.get_user(numeric_id)
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(numeric_id)
        except Exception:
            logger.exception("DM user lookup failed target_id=%s", user_id)
            return None

    async def _is_owner(self, user: Any) -> bool:
        try:
            return bool(await self.bot.is_owner(user))
        except Exception:
            logger.exception("Owner check failed user_id=%s", getattr(user, "id", "unknown"))
            return False

    def _mentions_bot(self, message: Any) -> bool:
        bot_user = getattr(self.bot, "user", None)
        return bot_user is not None and bot_user in tuple(getattr(message, "mentions", ()) or ())
