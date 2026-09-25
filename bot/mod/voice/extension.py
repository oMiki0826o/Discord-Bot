"""
bot/mod/voice/extension.py

Modification():

- 管理 Voice Module 的載入與卸載生命週期。
- 註冊並綁定 Voice Module Settings。
- 初始化 Voice Module 自有 Database。
- 建立並註冊 VoiceChannel Cog。
- 註冊與解除註冊 Voice Module 的自然語言指令。

本檔是 Voice Module 的生命週期入口。
僅負責模組組裝、設定與資源初始化，不包含語音頻道業務邏輯。
"""

from __future__ import annotations

# ── Third Party ──────────────────────

from discord.ext import commands

# ── Project ──────────────────────

from bot.config import DATABASE_DIR
from bot.core.discord.natural_command import natural_commands
from bot.core.settings.manager import settings
from bot.mod.voice import config, database
from bot.mod.voice.command import VoiceChannel
from bot.mod.voice.natural import create_natural_commands


# ── Constants ──────────────────────

_NATURAL_COMMAND_OWNER = "voice"


# ── Module Lifecycle ──────────────────────

async def setup(
    bot: commands.Bot,
) -> None:
    """載入 Voice Module。"""

    configuration = settings.register(
        config.SETTINGS_NAME,
        config.DEFAULT_SETTINGS,
        config.SETTINGS_SCHEMA,
    )
    config.bind(configuration)

    database.configure(
        DATABASE_DIR / "voice.db"
    )

    voice = VoiceChannel(
        bot
    )

    await bot.add_cog(
        voice
    )

    try:
        natural_commands.register_many(
            _NATURAL_COMMAND_OWNER,
            create_natural_commands(
                voice
            ),
        )
    except Exception:
        natural_commands.unregister(
            _NATURAL_COMMAND_OWNER
        )

        loaded_voice = bot.get_cog(
            voice.qualified_name
        )

        if loaded_voice is not None:
            await bot.remove_cog(
                voice.qualified_name
            )

        raise


async def teardown(
    bot: commands.Bot,
) -> None:
    """卸載 Voice Module。"""

    natural_commands.unregister(
        _NATURAL_COMMAND_OWNER
    )

    voice = bot.get_cog(
        "VoiceChannel"
    )

    if voice is not None:
        await bot.remove_cog(
            voice.qualified_name
        )
