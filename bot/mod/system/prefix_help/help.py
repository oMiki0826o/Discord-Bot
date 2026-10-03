"""
bot/mod/system/prefix_help/help.py

Modification():

- Dynamic Owner-only Prefix Command Help。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from discord.ext import commands

from bot.core.discord.help.builder import build_help_categories, module_display_name
from bot.core.discord.help.models import HelpEntry
from bot.core.discord.help.view import HelpView


def _command_module(command: Any) -> str:
    """Return the Feature Module owning a Prefix command."""

    callback = getattr(command, "callback", None)
    module_path = getattr(callback, "__module__", "")
    parts = module_path.split(".")
    try:
        return parts[parts.index("mod") + 1]
    except (ValueError, IndexError):
        return "other"


def collect_owner_prefix_commands(bot: Any) -> tuple[Any, ...]:
    """Build Help categories from all currently visible Prefix commands."""

    grouped: dict[str, list[HelpEntry]] = defaultdict(list)
    for command in bot.walk_commands():
        name = str(getattr(command, "qualified_name", "")).strip()
        if not name or name == "help" or bool(getattr(command, "hidden", False)):
            continue
        callback = getattr(command, "callback", None)
        description = str(
            getattr(command, "help", "")
            or getattr(callback, "__doc__", "")
            or "沒有說明"
        ).strip()
        grouped[_command_module(command)].append(
            HelpEntry(name=name, description=description)
        )
    return build_help_categories(dict(grouped), category_name_resolver=lambda name: module_display_name(bot, name))


class OwnerHelpCog(commands.Cog):
    """Render dynamically registered Owner Prefix commands using the shared Help UI."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="help")
    @commands.is_owner()
    async def help_command(self, ctx: commands.Context) -> None:
        """顯示目前可用的 Owner Prefix Commands。"""

        await self._send_overview(ctx)

    async def _send_overview(self, ctx: commands.Context) -> None:
        categories = collect_owner_prefix_commands(self.bot)
        if not categories:
            await ctx.send("目前沒有可顯示的 Owner 指令。")
            return
        view = HelpView(categories, user_id=ctx.author.id, command_prefix="$")
        view.message = await ctx.send(embed=view.build_embed(), view=view)
