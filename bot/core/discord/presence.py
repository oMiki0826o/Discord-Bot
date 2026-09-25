"""
bot/core/discord/presence.py

Modification():

- 管理 Discord Presence。
- 將 Settings 中的狀態設定轉換為 Discord API 所需格式。
- 保留 Settings 熱更新能力。

本檔負責 Discord Bot 的 Presence 狀態設定與轉換。
"""

from __future__ import annotations

import discord

from bot.core.settings.manager import get


# ── Presence 對照 ──────────────────────

"""
機器人目前狀態管理區：

遊玩、聆聽、觀看或競賽中，對應 Discord API 的 ActivityType。
在線、閒置、勿擾或隱形，對應 Discord API 的 Status。
"""

_ACTIVITY_TYPES: dict[str, discord.ActivityType] = {
    "playing": discord.ActivityType.playing,
    "listening": discord.ActivityType.listening,
    "watching": discord.ActivityType.watching,
    "competing": discord.ActivityType.competing,
}

_STATUS_MAP: dict[str, discord.Status] = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible,
}


# ── Presence 設定 ──────────────────────

def build_presence() -> tuple[discord.Activity | None, discord.Status]:
    """依目前 Settings 建立 Discord Presence。"""

    activity_type = str(get("bot.presence.activity", "listening"))
    activity_text = str(get("bot.presence.text", "/play | @我"))
    presence = str(get("bot.presence.status", "online"))

    discord_activity_type = _ACTIVITY_TYPES.get(
        activity_type,
        discord.ActivityType.listening,
    )

    discord_status = _STATUS_MAP.get(
        presence,
        discord.Status.online,
    )

    activity = (
        discord.Activity(
            type=discord_activity_type,
            name=activity_text,
        )
        if activity_text
        else None
    )

    return activity, discord_status
