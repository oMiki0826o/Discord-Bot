"""
bot/mod/ai/extension.py

Modification():

- 建立 AI Feature Module 的 Discord Extension 入口。
- 將 Core 整合 import 延後到 setup，使 AI package 仍可獨立匯入。
- 透過 Core 通用 natural command registry 避免 mention 被其他功能與 AI 重複處理。
- 將 permission-aware Discord Channel Reader 注入 Agent Tool adapter。
- 將 Bot-attached RuntimeHost 注入 AI assembly，保留附掛模組的 reload descriptor。

本檔案只負責註冊設定、組裝服務與加入 Cog。
"""

from __future__ import annotations

import weakref


MODULE_VERSION = "0.1.0"
MODULE_DISPLAY_NAME = "AI"
MODULE_DEPENDENCIES: tuple[str, ...] = ()

_loaded_modules = weakref.WeakKeyDictionary()


async def _install_module(bot, module, cog_factory):
    """加入 Cog；安裝失敗時回滾所有 Module-owned runtime 資源。"""

    try:
        cog = cog_factory(bot, module)
        await bot.add_cog(cog)
    except BaseException:
        await module.close()
        raise
    return cog


async def setup(bot) -> None:
    """依發布版 Module 契約組裝 AIService 與 Discord Cog。"""

    from bot.config import DATABASE_DIR
    from bot.core.discord.natural_command import natural_commands
    from bot.core.settings.manager import settings
    from bot.core.settings.schema import SettingRule

    from .assembly import build_module
    from .api import get_runtime_host
    from .commands.discord import create_ai_cog, create_channel_reader, create_prompt_audit_sink
    from .config import DEFAULT_SETTINGS, SETTINGS_NAME, build_settings_schema

    configuration = settings.register(
        SETTINGS_NAME,
        DEFAULT_SETTINGS,
        build_settings_schema(SettingRule),
    )
    module = build_module(
        database_dir=DATABASE_DIR,
        data_dir=DATABASE_DIR.parent / "ai",
        raw_settings=configuration,
        channel_reader=create_channel_reader(bot),
        runtime_host=get_runtime_host(bot),
        audit_sink=create_prompt_audit_sink(bot, int(configuration["prompt_log_channel_id"])),
    )
    cog = await _install_module(
        bot,
        module,
        lambda target, runtime: create_ai_cog(
            target,
            runtime,
            should_skip_prompt=natural_commands.contains,
        ),
    )
    _loaded_modules[bot] = (module, cog.qualified_name)


async def teardown(bot) -> None:
    """卸載 AI Cog 並釋放 worker、Provider 與 in-memory state。"""

    loaded = _loaded_modules.pop(bot, None)
    if loaded is None:
        return
    module, cog_name = loaded
    try:
        if bot.get_cog(cog_name) is not None:
            await bot.remove_cog(cog_name)
    finally:
        await module.close()
