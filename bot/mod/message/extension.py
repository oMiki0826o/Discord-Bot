"""
bot/mod/message/extension.py

Modification():

- 提供 Message Module 的 Discord Extension 入口。
- 註冊 Message Module 預設 Settings。
- 建立 Message Module 自有 Database。
- 組裝 Say、Webhook 與 Embed 功能服務。
- 註冊 Message Module 的 Discord Cog。

本檔只負責 Message Module 的組裝與註冊，
不實作具體訊息發送功能。
"""

from __future__ import annotations

from discord.ext import commands

from bot.config import DATABASE_DIR
from bot.core.settings.manager import settings
from bot.mod.message.command import MessageCog
from bot.mod.message.config import (
    DEFAULT_SETTINGS,
    SETTINGS_NAME,
    SETTINGS_SCHEMA,
)
from bot.mod.message.database import MessageDatabase
from bot.mod.message.embed import EmbedService
from bot.mod.message.say import SayService
from bot.mod.message.webhook import WebhookService


# ── Extension ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """註冊 Message Module。"""

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        SETTINGS_SCHEMA,
    )

    database = MessageDatabase(
        DATABASE_DIR / "message.db",
        default_require_management=bool(
            configuration["require_management"]
        ),
    )

    say_service = SayService(
        max_content_length=int(
            configuration["plain_max_content_length"]
        ),
        max_attachments=int(
            configuration["max_attachments"]
        ),
    )

    webhook_service = WebhookService(
        bot=bot,
        webhook_name=str(
            configuration["webhook_name"]
        ),
        max_content_length=int(
            configuration["webhook_max_content_length"]
        ),
        max_attachments=int(
            configuration["max_attachments"]
        ),
    )

    embed_service = EmbedService()

    await bot.add_cog(
        MessageCog(
            bot,
            database=database,
            say_service=say_service,
            webhook_service=webhook_service,
            embed_service=embed_service,
            panel_timeout_seconds=int(
                configuration["panel_timeout_seconds"]
            ),
            admin_panel_timeout_seconds=int(
                configuration[
                    "admin_panel_timeout_seconds"
                ]
            ),
        )
    )
