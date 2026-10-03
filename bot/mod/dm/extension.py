"""
bot/mod/dm/extension.py

Modification():

- Extension entry point for the independent Owner DM bridge Module。
"""

from __future__ import annotations


MODULE_VERSION = "0.1.0"
MODULE_DISPLAY_NAME = "私訊橋接"
MODULE_DEPENDENCIES: tuple[str, ...] = ()


async def setup(bot) -> None:
    """Register DM settings and install the single Discord-facing Cog."""

    from bot.core.settings.manager import settings
    from bot.core.settings.schema import SettingRule

    from .command import DMCog
    from .config import DEFAULT_SETTINGS, SETTINGS_NAME, DMSettings, build_settings_schema
    from .service import DMBridgeService

    raw = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        build_settings_schema(SettingRule),
    )
    await bot.add_cog(DMCog(bot, DMBridgeService(DMSettings.from_mapping(raw))))


async def teardown(bot) -> None:
    """Provide the standard Module lifecycle hook; state belongs to the removed Cog."""

    return None
