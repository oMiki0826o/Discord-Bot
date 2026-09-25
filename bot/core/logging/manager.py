"""
bot/core/logging/manager.py

Modification():

- 管理全域 Logging 系統。
- 管理 Console 與 File Log。
- 管理 Log Rotation。
- 管理 Discord 錯誤回報 Handler。
- 追蹤本次執行期間的錯誤狀態。
- 提供本次執行期間的終端錯誤摘要。
- 提供 Bot 結束時的 Discord Session Report。
- 發生錯誤時支援附加完整 Session Log。
- 支援 Owner 私訊與指定頻道作為結束報告目的地。

本檔負責 Logging 系統的初始化、Handler 管理與執行期錯誤狀態。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from bot.core.discord.owner import resolve_owner
from bot.core.logging.constants import (
    DATE_FORMAT,
    ERROR_REPORTING_CHANNEL_ID,
    ERROR_REPORTING_DESTINATION,
    LOG_FILE,
    LOG_FORMAT,
    LOG_ROTATE_BACKUP_COUNT,
    LOG_ROTATE_MAX_BYTES,
    SESSION_LOG_DIR,
    SHUTDOWN_REPORT_SEND_LOG_FILE,
)
from bot.core.logging.discord_error_handler import DiscordErrorHandler
from bot.core.settings.manager import get


# ── Logging Manager ──────────────────────

class LogManager:
    """管理整個 Process 的 Python Logging 系統。"""

    _instance: LogManager | None = None

    def __new__(cls) -> LogManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self._initialized = True

        self._had_errors = False
        self._bot: commands.Bot | None = None
        self._discord_error_handler: DiscordErrorHandler | None = None

        self._setup_logging()

    # ── Logging 初始化 ──────────────────────

    def _setup_logging(self) -> None:
        """初始化 Root Logger 與基礎 Handler。"""

        SESSION_LOG_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        root_logger = logging.getLogger()

        if getattr(
            root_logger,
            "_discord_bot_logging_initialized",
            False,
        ):
            return

        root_logger._discord_bot_logging_initialized = True  # type: ignore[attr-defined]

        root_logger.setLevel(logging.INFO)

        formatter = logging.Formatter(
            LOG_FORMAT,
            datefmt=DATE_FORMAT,
        )

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_ROTATE_MAX_BYTES,
            backupCount=LOG_ROTATE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        error_tracker = _ErrorTracker(self)
        error_tracker.setLevel(logging.ERROR)

        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_tracker)

        logging.getLogger("bot").setLevel(
            logging.DEBUG
        )

        logging.getLogger("discord").setLevel(
            logging.INFO
        )

    # ── Logger ──────────────────────

    def get_logger(
        self,
        name: str,
    ) -> logging.Logger:
        """取得指定名稱的 Logger。"""

        return logging.getLogger(name)

    # ── Discord ──────────────────────

    def attach_bot(
        self,
        bot: commands.Bot,
    ) -> None:
        """掛載 Discord 錯誤回報 Handler。"""

        self._bot = bot

        root_logger = logging.getLogger()

        for handler in root_logger.handlers:
            if isinstance(
                handler,
                DiscordErrorHandler,
            ):
                self._discord_error_handler = handler
                return

        handler = DiscordErrorHandler(
            bot=bot,
        )

        self._discord_error_handler = handler
        root_logger.addHandler(handler)

        logging.getLogger(
            "bot.logging"
        ).debug(
            "DiscordErrorHandler 已掛載"
        )

    # ── Shutdown Report ──────────────────────

    async def send_shutdown_report(self) -> None:
        """傳送本次 Bot 執行期間的結束報告。"""

        if self._bot is None:
            return

        destination = await self._resolve_report_destination()

        if destination is None:
            return

        send_log_file = (
            self._had_errors
            and bool(
                get(
                    SHUTDOWN_REPORT_SEND_LOG_FILE,
                    True,
                )
            )
        )

        try:
            await destination.send(
                embed=self._build_shutdown_embed(
                    include_log=send_log_file
                )
            )

            if send_log_file:
                await self._send_session_log(
                    destination
                )

        except Exception as exc:
            self._write_internal_error(
                "Shutdown Report 傳送失敗",
                exc,
            )

    def _build_shutdown_embed(
        self,
        *,
        include_log: bool,
    ) -> discord.Embed:
        """建立本次執行期間的結束報告。"""

        if self._had_errors:
            status = "本次運行期間曾發生錯誤。"
        else:
            status = "本次運行期間無任何錯誤。"

        embed = discord.Embed(
            title="Bot 執行報告",
            description=status,
            timestamp=discord.utils.utcnow(),
        )

        if include_log:
            embed.add_field(
                name="Log",
                value=f"`{LOG_FILE.name}`",
                inline=False,
            )

        return embed

    async def _send_session_log(
        self,
        destination: discord.abc.Messageable,
    ) -> None:
        """發生錯誤時將目前 Session Log 傳送至 Discord。"""

        try:
            if not LOG_FILE.is_file():
                return

            if LOG_FILE.stat().st_size <= 0:
                return

            await destination.send(
                file=discord.File(
                    LOG_FILE,
                    filename=LOG_FILE.name,
                )
            )

        except (
            discord.Forbidden,
            discord.HTTPException,
            OSError,
        ) as exc:
            self._write_internal_error(
                "Session Log 傳送失敗",
                exc,
            )

    # ── Destination ──────────────────────

    async def _resolve_report_destination(
        self,
    ) -> discord.abc.Messageable | None:
        """依 Settings 取得 Session Report 傳送位置。"""

        destination = str(
            get(
                ERROR_REPORTING_DESTINATION,
                "owner",
            )
        ).lower()

        if destination == "channel":
            return await self._resolve_channel()

        return await self._resolve_owner()

    async def _resolve_channel(
        self,
    ) -> discord.abc.Messageable | None:
        """取得指定的 Discord 頻道。"""

        bot = self._bot

        if bot is None:
            return None

        channel_id = get(
            ERROR_REPORTING_CHANNEL_ID,
            None,
        )

        if not isinstance(
            channel_id,
            int,
        ):
            return None

        channel = bot.get_channel(
            channel_id
        )

        if channel is None:
            try:
                channel = await bot.fetch_channel(
                    channel_id
                )
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                return None

        if not isinstance(
            channel,
            discord.abc.Messageable,
        ):
            return None

        return channel

    async def _resolve_owner(
        self,
    ) -> discord.User | discord.TeamMember | None:
        """取得 Bot Owner。"""

        bot = self._bot

        if bot is None:
            return None

        return await resolve_owner(bot)

    # ── Session 狀態 ──────────────────────

    @property
    def had_errors(self) -> bool:
        """取得本次執行期間是否曾發生 ERROR 或 CRITICAL。"""

        return self._had_errors

    def print_session_summary(self) -> None:
        """透過統一 Logger 輸出本次執行期間的錯誤摘要。"""

        logger = self.get_logger("bot.logging.session")
        if self._had_errors:
            logger.warning("Session 結束 | 狀態=有錯誤 | log=%s", LOG_FILE)
        else:
            logger.info("Session 結束 | 狀態=正常 | log=%s", LOG_FILE)

    # ── Internal Failure ──────────────────────

    @staticmethod
    def _write_internal_error(
        message: str,
        error: BaseException,
    ) -> None:
        """直接輸出 Logging 系統自身錯誤，避免形成遞迴。"""

        sys.stderr.write(
            "[LogManager] "
            f"{message}: "
            f"{type(error).__name__}: "
            f"{error}\n"
        )


# ── Error Tracker ──────────────────────

class _ErrorTracker(logging.Handler):
    """追蹤本次執行期間是否發生 ERROR 或 CRITICAL。"""

    def __init__(
        self,
        manager: LogManager,
    ) -> None:
        super().__init__(
            level=logging.ERROR
        )

        self._manager = manager

    def emit(
        self,
        record: logging.LogRecord,
    ) -> None:
        """標記本次執行期間曾發生錯誤。"""

        self._manager._had_errors = True
