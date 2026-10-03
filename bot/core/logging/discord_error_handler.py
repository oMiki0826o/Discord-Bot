"""
bot/core/logging/discord_error_handler.py

Modification():

- 接收 Python Logging 的 ERROR 與 CRITICAL 紀錄。
- 將錯誤報告非同步傳送至 Discord。
- 支援 Owner 私訊與指定頻道兩種通報位置。
- 支援簡略與完整錯誤上下文。
- 支援 Traceback 分段傳送。
- 避免錯誤通報失敗造成遞迴 Logging。
- 支援執行期間即時讀取錯誤通報設定。

本檔負責將 Core Logging 產生的錯誤安全提交至 Discord。
"""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from typing import TYPE_CHECKING

import discord

from bot.core.discord.owner import resolve_owner
from bot.core.logging.constants import (
    ERROR_REPORTING_CHANNEL_ID,
    ERROR_REPORTING_DESTINATION,
    ERROR_REPORTING_ENABLED,
    ERROR_REPORTING_FULL_CONTEXT,
)
from bot.core.logging.traceback import split_traceback
from bot.core.settings.manager import get

if TYPE_CHECKING:
    from discord.ext import commands


# ── Discord Error Handler ──────────────────────

class DiscordErrorHandler(logging.Handler):
    """將 ERROR 與 CRITICAL Logging 紀錄提交至 Discord。"""

    def __init__(
        self,
        *,
        bot: commands.Bot,
    ) -> None:
        super().__init__(
            level=logging.ERROR
        )

        self.bot = bot
        self._sending = False

    # ── Logging Entry ──────────────────────

    def emit(
        self,
        record: logging.LogRecord,
    ) -> None:
        """接收 Logging Record 並排程 Discord 錯誤通報。"""

        if record.levelno < logging.ERROR:
            return

        if self._sending:
            return

        if not bool(
            get(
                ERROR_REPORTING_ENABLED,
                True,
            )
        ):
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        try:
            loop.create_task(
                self._send_record(record)
            )
        except Exception as exc:
            self._write_internal_error(
                "無法建立 Discord 錯誤報告 Task",
                exc,
            )

    # ── 錯誤報告 ──────────────────────

    async def _send_record(
        self,
        record: logging.LogRecord,
    ) -> None:
        """建立並傳送 Discord 錯誤報告。"""

        if self._sending:
            return

        self._sending = True

        try:
            destination = await self._resolve_destination()

            if destination is None:
                return

            await destination.send(
                embed=self._build_summary(record)
            )

            if not bool(
                get(
                    ERROR_REPORTING_FULL_CONTEXT,
                    False,
                )
            ):
                return

            context = self._build_context(record)

            if not context:
                return

            for chunk in split_traceback(context):
                await destination.send(chunk)

        except Exception as exc:
            self._write_internal_error(
                "Discord 錯誤報告 傳送失敗",
                exc,
            )

        finally:
            self._sending = False

    # ── Destination ──────────────────────

    async def _resolve_destination(
        self,
    ) -> discord.abc.Messageable | None:
        """依 Settings 取得錯誤通報目的地。"""

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
        """取得錯誤通報指定頻道。"""

        channel_id = get(
            ERROR_REPORTING_CHANNEL_ID,
            None,
        )

        if not isinstance(
            channel_id,
            int,
        ):
            return None

        channel = self.bot.get_channel(
            channel_id
        )

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
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

        return await resolve_owner(self.bot)

    # ── Summary ──────────────────────

    def _build_summary(
        self,
        record: logging.LogRecord,
    ) -> discord.Embed:
        """建立簡略錯誤報告。"""

        message = record.getMessage()

        if len(message) > 1000:
            message = f"{message[:997]}..."

        embed = discord.Embed(
            title="錯誤報告",
            description=(
                message
                or "無錯誤訊息"
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name="Logger",
            value=f"`{record.name}`",
            inline=True,
        )

        embed.add_field(
            name="Level",
            value=f"`{record.levelname}`",
            inline=True,
        )

        exception_name = self._get_exception_name(
            record
        )

        if exception_name is not None:
            embed.add_field(
                name="Exception",
                value=f"`{exception_name}`",
                inline=True,
            )

        return embed

    # ── Full Context ──────────────────────

    @staticmethod
    def _build_context(
        record: logging.LogRecord,
    ) -> str:
        """建立完整錯誤上下文。"""

        sections = [
            f"Logger: {record.name}",
            f"Level: {record.levelname}",
            f"Message: {record.getMessage()}",
            (
                "Source: "
                f"{record.pathname}:"
                f"{record.lineno} "
                f"in {record.funcName}"
            ),
        ]

        exception_text = ""

        if record.exc_info:
            exception_text = "".join(
                traceback.format_exception(
                    *record.exc_info
                )
            ).strip()

        elif record.exc_text:
            exception_text = (
                record.exc_text.strip()
            )

        if exception_text:
            sections.extend(
                [
                    "",
                    "Traceback:",
                    exception_text,
                ]
            )

        return "\n".join(sections)

    @staticmethod
    def _get_exception_name(
        record: logging.LogRecord,
    ) -> str | None:
        """取得 Exception 類型名稱。"""

        if not record.exc_info:
            return None

        exception_type = record.exc_info[0]

        if exception_type is None:
            return None

        return exception_type.__name__

    # ── Internal Failure ──────────────────────

    @staticmethod
    def _write_internal_error(
        message: str,
        error: BaseException,
    ) -> None:
        """
        將 Handler 自身錯誤直接寫入 stderr。

        不重新使用 Python Logging，
        避免錯誤通報器觸發自身形成遞迴。
        """

        sys.stderr.write(
            "[DiscordErrorHandler] "
            f"{message}: "
            f"{type(error).__name__}: "
            f"{error}\n"
        )
