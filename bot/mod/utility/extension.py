"""
bot/mod/utility/extension.py

Modification():

- 提供 Utility Module 的 Discord Extension 入口。
- 註冊 Utility Module 預設 Settings。
- 建立 MarkItDown Service 並註冊 Utility Cog。

本檔只負責 Utility Module 的組裝與註冊，
不實作文件轉換業務邏輯。
"""

from __future__ import annotations

from discord.ext import commands

from bot.core.settings.manager import settings
from bot.mod.utility.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)
from bot.mod.utility.markitdown import (
    MarkItDownCog,
    MarkItDownService,
)


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Utility Module。"""

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    markitdown_settings = configuration["markitdown"]

    service = MarkItDownService(
        max_file_size_bytes=int(
            markitdown_settings["max_file_size_bytes"]
        ),
    )

    await bot.add_cog(
        MarkItDownCog(
            bot,
            service,
        )
    )
