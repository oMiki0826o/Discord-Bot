"""
bot/core/discord/intents.py

Modification():

- 將 bot.intents Settings 轉換為 Discord Intents。
- 保持 Discord Client 不含硬編碼的 Feature Intent 設定。

本檔只負責 Discord Intents 建立，
不負責 Discord Client Lifecycle 或 Module 特殊需求。
"""

from __future__ import annotations

import discord

from bot.core.settings.manager import get


def build_intents() -> discord.Intents:
    """依 ``bot.intents`` 建立 Discord Intents。"""

    intents = discord.Intents.default()
    configured = get("bot.intents", {})
    if not isinstance(configured, dict):
        return intents

    for name, enabled in configured.items():
        if hasattr(intents, name):
            setattr(intents, name, bool(enabled))
    return intents
