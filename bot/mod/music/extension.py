"""
bot/mod/music/extension.py

Modification():

- 管理 Music Module 的載入與卸載生命週期。
- 註冊 Music Settings 並綁定 Module 自有 Database。
- 建立並註冊 Music 與 Favorites Cog。
- 註冊與解除註冊 Music Module 的自然語言指令。
- 卸載模組時清理播放器與相關執行資源。

本檔是 Music Module 的生命週期入口。
僅負責模組組裝、資源初始化與註冊，不包含音樂播放業務邏輯。
"""

from __future__ import annotations

# ── Standard Library ──────────────────────

import logging

# ── Third Party ──────────────────────

from discord.ext import commands

# ── Project ──────────────────────

from bot.config import DATABASE_DIR
from bot.core.discord.natural_command import natural_commands
from bot.core.settings.manager import settings
from bot.mod.music import config, favorites_repository
from bot.mod.music.command import Music
from bot.mod.music.database import MusicDatabase
from bot.mod.music.favorites import Favorites
from bot.mod.music.natural import create_natural_commands
from bot.mod.music.service import get_manager


# ── Constants ──────────────────────

_NATURAL_COMMAND_OWNER = "music"

logger = logging.getLogger("bot.mod.music.extension")


# ── Module Lifecycle ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """載入 Music Module 並完成設定、資料庫與 Discord 元件組裝。"""

    configuration = settings.register(
        config.SETTINGS_NAME,
        config.DEFAULT_SETTINGS,
        config.SETTINGS_SCHEMA,
    )
    config.bind(configuration)

    database = MusicDatabase(
        DATABASE_DIR / "music.db"
    )
    favorites_repository.bind(database)

    music = Music(bot)
    favorites = Favorites(bot)

    try:
        await bot.add_cog(favorites)
        await bot.add_cog(music)

        natural_commands.register_many(
            _NATURAL_COMMAND_OWNER,
            create_natural_commands(music),
        )
    except Exception:
        natural_commands.unregister(
            _NATURAL_COMMAND_OWNER
        )

        favorites_cog = bot.get_cog("Favorites")
        if favorites_cog is not None:
            await bot.remove_cog(
                favorites_cog.qualified_name
            )

        music_cog = bot.get_cog("Music")
        if music_cog is not None:
            await bot.remove_cog(
                music_cog.qualified_name
            )

        raise


async def teardown(
    bot: commands.Bot,
) -> None:
    """卸載 Music Module 並釋放播放器與 Discord 元件。"""

    natural_commands.unregister(
        _NATURAL_COMMAND_OWNER
    )

    manager = get_manager()

    for guild_id, player in tuple(
        manager.all_players().items()
    ):
        try:
            await player.disconnect()
        except Exception:
            logger.exception(
                "Music Module 卸載時播放器清理失敗 guild_id=%s",
                guild_id,
            )
        finally:
            manager.remove(guild_id)

    favorites_cog = bot.get_cog("Favorites")
    if favorites_cog is not None:
        await bot.remove_cog(
            favorites_cog.qualified_name
        )

    music_cog = bot.get_cog("Music")
    if music_cog is not None:
        await bot.remove_cog(
            music_cog.qualified_name
        )
