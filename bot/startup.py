"""
bot/startup.py

Modification():

- 管理 Bot Application 啟動流程。
- 驗證環境設定。
- 準備 Runtime 資料目錄。
- 載入全域 Settings。
- 建立 Discord Bot。
- 建立並注入 Module Loader。
- 掛載 Discord Logging Handler。
- 管理 Bot 執行與安全關閉生命週期。
- 接收 Bot Application 關閉請求。
- 在關閉 Discord Client 前卸載功能 Module。
- 在 Discord Client 關閉前傳送 Session Report。
- 避免 Shutdown Report 失敗觸發遞迴錯誤通報。
- 輸出本次執行期間的錯誤摘要。

本檔負責 Application 元件組裝與生命週期，
不處理 Discord Client 內部邏輯或功能模組業務。
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from enum import Enum

from bot.config import (
    DATA_DIR,
    DATABASE_DIR,
    DISCORD_TOKEN,
    LOG_DIR,
    MODULES_DIR,
    MODULES_PACKAGE,
    validate_config,
)
from bot.core.discord.client import DiscordBot
from bot.core.logging.manager import LogManager
from bot.core.modules.loader import ModuleLoader
from bot.core.settings.manager import settings
from bot.core.settings.schema import SettingRule


log_manager = LogManager()

logger = log_manager.get_logger(
    "bot.startup"
)


class ApplicationState(str, Enum):
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    CLOSED = "closed"


_application_state = ApplicationState.RUNNING
_shutdown_lock = asyncio.Lock()


# ── Runtime 初始化 ──────────────────────

def prepare_runtime() -> None:
    """建立 Bot 執行所需的基礎資料目錄。"""

    directories = {
        DATA_DIR,
        DATABASE_DIR,
        LOG_DIR,
    }

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ── Settings 初始化 ──────────────────────

def load_settings() -> None:
    """註冊 Core Settings Schema 並載入所有非機密 Settings。"""

    settings.register(
        "bot",
        {
            "command_prefix": "$",
            "intents": {
                "members": True,
                "message_content": True,
                "presences": False,
            },
            "presence": {
                "status": "online",
                "activity": "listening",
                "text": "/play | @我",
            },
        },
        {
            "command_prefix": SettingRule(str, validator=bool, description="不可為空字串"),
            "presence.status": SettingRule(
                str,
                choices=frozenset({"online", "idle", "dnd", "invisible"}),
            ),
            "presence.activity": SettingRule(
                str,
                choices=frozenset({"playing", "streaming", "listening", "watching", "competing"}),
            ),
        },
    )
    settings.load_all()


# ── Application 初始化 ──────────────────────

def initialize() -> None:
    """執行 Application 啟動前的同步初始化。"""

    validate_config()
    prepare_runtime()
    load_settings()

    logger.info(
        "Application 初始化完成"
    )


# ── Application 組裝 ──────────────────────

def create_bot() -> DiscordBot:
    """建立並組裝 Discord Bot Application。"""

    bot = DiscordBot()

    module_loader = ModuleLoader(
        bot=bot,
        modules_dir=MODULES_DIR,
        modules_package=MODULES_PACKAGE,
    )

    bot.set_module_loader(
        module_loader
    )

    log_manager.attach_bot(
        bot
    )

    return bot


# ── Shutdown Report ──────────────────────

async def send_shutdown_report() -> None:
    """安全傳送本次 Session 的 Discord 結束報告。"""

    try:
        await asyncio.wait_for(
            log_manager.send_shutdown_report(),
            timeout=10.0,
        )

    except asyncio.TimeoutError:
        _write_shutdown_error(
            "Shutdown Report 傳送逾時"
        )

    except Exception as exc:
        _write_shutdown_error(
            "Shutdown Report 傳送失敗",
            exc,
        )


def _write_shutdown_error(
    message: str,
    error: BaseException | None = None,
) -> None:
    """直接輸出 Shutdown 錯誤，避免重新進入 Logging Handler。"""

    if error is None:
        sys.stderr.write(f"[Shutdown] {message}\n")
        return

    sys.stderr.write(
        "[Shutdown] "
        f"{message}: "
        f"{type(error).__name__}: "
        f"{error}\n"
    )


# ── Module 關閉 ──────────────────────

async def unload_modules(
    bot: DiscordBot,
) -> None:
    """卸載所有目前已載入的功能 Module。"""

    loader = bot.module_loader

    if loader is None:
        return

    try:
        await asyncio.wait_for(loader.unload_all(), timeout=15.0)

    except asyncio.TimeoutError:
        _write_shutdown_error("Module Cleanup 逾時")

    except Exception:
        logger.exception(
            "Module 批次卸載失敗"
        )


# ── Application 關閉 ──────────────────────

async def shutdown(
    bot: DiscordBot,
) -> None:
    """依正確順序安全關閉 Bot Application。"""

    global _application_state

    async with _shutdown_lock:
        if _application_state is not ApplicationState.RUNNING:
            return
        _application_state = ApplicationState.SHUTTING_DOWN

        try:
            await unload_modules(bot)
            await send_shutdown_report()
            if not bot.is_closed():
                await bot.close()
        finally:
            _application_state = ApplicationState.CLOSED


# ── Application 執行 ──────────────────────

async def run_bot(
    bot: DiscordBot,
) -> None:
    """執行 Discord Bot 並監聽 Application 關閉請求。"""

    bot_task = asyncio.create_task(
        bot.start(
            DISCORD_TOKEN
        ),
        name="discord-bot",
    )

    shutdown_task = asyncio.create_task(
        bot.shutdown_event.wait(),
        name="shutdown-waiter",
    )

    done, _ = await asyncio.wait(
        {
            bot_task,
            shutdown_task,
        },
        return_when=asyncio.FIRST_COMPLETED,
    )

    if shutdown_task in done:
        await shutdown(
            bot
        )

    if not shutdown_task.done():
        shutdown_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await shutdown_task

    await bot_task


# ── Application 啟動 ──────────────────────

async def start() -> None:
    """建立並執行 Discord Bot Application。"""

    initialize()

    bot = create_bot()

    try:
        await run_bot(
            bot
        )

    finally:
        if not bot.is_closed():
            await shutdown(
                bot
            )


# ── Application 入口 ──────────────────────

def run() -> None:
    """執行 Bot Application 並管理最外層生命週期。"""

    try:
        asyncio.run(
            start()
        )

    except KeyboardInterrupt:
        logger.info("收到鍵盤中斷，準備結束 Application")

    finally:
        log_manager.print_session_summary()
