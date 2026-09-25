"""
bot/core/discord/owner.py

Modification():

- 集中管理 Discord Bot Owner Identity。
- 統一 OWNER_ID、Discord Application Owner 與 Discord Team Owner 的判定順序。
- 供 Command、Logging 與 Shutdown Report 使用相同 Owner Policy。

本檔只負責 Owner Identity Resolution，
不負責 Owner Command、錯誤通報或 Application Lifecycle。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.config import OWNER_ID

if TYPE_CHECKING:
    from discord.abc import User
    from discord.ext import commands


async def resolve_owner_id(bot: commands.Bot) -> int | None:
    """依 OWNER_ID、Application Owner、Team Owner 取得唯一 Owner ID。"""

    if OWNER_ID is not None:
        return OWNER_ID

    try:
        application = await bot.application_info()
    except discord.HTTPException:
        return None

    if application.owner is not None:
        return application.owner.id
    if application.team is not None and application.team.owner is not None:
        return application.team.owner.id
    return None


async def is_owner(bot: commands.Bot, user: User) -> bool:
    """判斷使用者是否符合全專案唯一 Owner Policy。"""

    owner_id = await resolve_owner_id(bot)
    return owner_id is not None and user.id == owner_id


async def resolve_owner(bot: commands.Bot) -> discord.User | discord.TeamMember | None:
    """取得錯誤與關閉報告的 Owner 對象。"""

    owner_id = await resolve_owner_id(bot)
    if owner_id is None:
        return None

    cached = bot.get_user(owner_id)
    if cached is not None:
        return cached

    try:
        return await bot.fetch_user(owner_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None
