"""
bot/mod/logging/command.py

Modification():

- 提供 Owner 專用的錯誤通報管理指令。
- 顯示目前錯誤通報與結束報告設定。
- 支援開啟或關閉 Discord 錯誤通報。
- 支援切換完整錯誤上下文。
- 支援切換 Owner 私訊與指定頻道。
- 支援控制發生錯誤時是否附加完整 執行階段日誌。

本檔負責 Logging Module 的 Discord Prefix Commands。
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.logging.constants import (
    ERROR_REPORTING_CHANNEL_ID,
    ERROR_REPORTING_DESTINATION,
    ERROR_REPORTING_ENABLED,
    ERROR_REPORTING_FULL_CONTEXT,
    SHUTDOWN_REPORT_SEND_LOG_FILE,
)
from bot.core.settings.manager import get, set_value


# ── Constants ──────────────────────

BOOLEAN_VALUES = {
    "on": True,
    "off": False,
}


# ── Logging Commands ──────────────────────

class LoggingManagementCog(commands.Cog):
    """提供 Owner 使用的 Logging 管理指令。"""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    # ── Error Group ──────────────────────

    @commands.group(
        name="error",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def error_group(
        self,
        ctx: commands.Context,
    ) -> None:
        """顯示目前錯誤通報設定。"""

        await ctx.send(
            embed=self._build_status_embed()
        )

    # ── Enabled ──────────────────────

    @error_group.command(
        name="enabled",
    )
    @commands.is_owner()
    async def error_enabled(
        self,
        ctx: commands.Context,
        value: str,
    ) -> None:
        """開啟或關閉 Discord 錯誤通報。"""

        enabled = self._parse_boolean(value)

        if enabled is None:
            await ctx.send(
                f"用法：`{ctx.prefix}error enabled <on|off>`"
            )
            return

        set_value(
            ERROR_REPORTING_ENABLED,
            enabled,
        )

        await ctx.send(
            "Discord 錯誤通報已"
            + ("開啟。" if enabled else "關閉。")
        )

    # ── Context ──────────────────────

    @error_group.command(
        name="context",
    )
    @commands.is_owner()
    async def error_context(
        self,
        ctx: commands.Context,
        value: str,
    ) -> None:
        """切換完整錯誤上下文。"""

        enabled = self._parse_boolean(value)

        if enabled is None:
            await ctx.send(
                f"用法：`{ctx.prefix}error context <on|off>`"
            )
            return

        set_value(
            ERROR_REPORTING_FULL_CONTEXT,
            enabled,
        )

        await ctx.send(
            "完整錯誤上下文已"
            + ("開啟。" if enabled else "關閉。")
        )

    # ── Channel ──────────────────────

    @error_group.command(
        name="channel",
    )
    @commands.is_owner()
    async def error_channel(
        self,
        ctx: commands.Context,
        destination: str,
    ) -> None:
        """設定錯誤通報與結束報告位置。"""

        if destination.lower() == "owner":
            set_value(
                ERROR_REPORTING_DESTINATION,
                "owner",
                save=False,
            )

            set_value(
                ERROR_REPORTING_CHANNEL_ID,
                None,
            )

            await ctx.send(
                "錯誤通報與結束報告位置已設為 Owner 私訊。"
            )
            return

        channel = await self._resolve_text_channel(
            ctx,
            destination,
        )

        if channel is None:
            await ctx.send(
                f"用法：`{ctx.prefix}error channel <owner|#channel>`"
            )
            return

        set_value(
            ERROR_REPORTING_DESTINATION,
            "channel",
            save=False,
        )

        set_value(
            ERROR_REPORTING_CHANNEL_ID,
            channel.id,
        )

        await ctx.send(
            "錯誤通報與結束報告位置已設為 "
            f"{channel.mention}。"
        )

    # ── Log File ──────────────────────

    @error_group.command(
        name="logfile",
    )
    @commands.is_owner()
    async def error_logfile(
        self,
        ctx: commands.Context,
        value: str,
    ) -> None:
        """控制發生錯誤時是否附加完整 執行階段日誌。"""

        enabled = self._parse_boolean(value)

        if enabled is None:
            await ctx.send(
                f"用法：`{ctx.prefix}error logfile <on|off>`"
            )
            return

        set_value(
            SHUTDOWN_REPORT_SEND_LOG_FILE,
            enabled,
        )

        await ctx.send(
            "發生錯誤時附加完整 執行階段日誌 已"
            + ("開啟。" if enabled else "關閉。")
        )

    # ── Status ──────────────────────

    def _build_status_embed(
        self,
    ) -> discord.Embed:
        """建立目前 Logging Module 設定摘要。"""

        enabled = bool(
            get(
                ERROR_REPORTING_ENABLED,
                True,
            )
        )

        full_context = bool(
            get(
                ERROR_REPORTING_FULL_CONTEXT,
                False,
            )
        )

        destination = str(
            get(
                ERROR_REPORTING_DESTINATION,
                "owner",
            )
        ).lower()

        channel_id = get(
            ERROR_REPORTING_CHANNEL_ID,
            None,
        )

        send_log_file = bool(
            get(
                SHUTDOWN_REPORT_SEND_LOG_FILE,
                True,
            )
        )

        embed = discord.Embed(
            title="日誌與錯誤通報",
            description=(
                "目前 Discord 錯誤通報與結束報告設定。"
            ),
        )

        embed.add_field(
            name="錯誤通報",
            value=self._format_boolean(
                enabled
            ),
            inline=True,
        )

        embed.add_field(
            name="完整錯誤上下文",
            value=self._format_boolean(
                full_context
            ),
            inline=True,
        )

        embed.add_field(
            name="錯誤時附加日誌",
            value=self._format_boolean(
                send_log_file
            ),
            inline=True,
        )

        embed.add_field(
            name="通報位置",
            value=self._format_destination(
                destination,
                channel_id,
            ),
            inline=False,
        )

        return embed

    # ── Channel Resolver ──────────────────────

    async def _resolve_text_channel(
        self,
        ctx: commands.Context,
        value: str,
    ) -> discord.TextChannel | None:
        """解析頻道 Mention 或 Discord Channel ID。"""

        converter = commands.TextChannelConverter()

        try:
            return await converter.convert(
                ctx,
                value,
            )
        except (
            commands.ChannelNotFound,
            commands.BadArgument,
        ):
            return None

    # ── Helpers ──────────────────────

    @staticmethod
    def _parse_boolean(
        value: str,
    ) -> bool | None:
        """解析 on/off 參數。"""

        return BOOLEAN_VALUES.get(
            value.lower()
        )

    @staticmethod
    def _format_boolean(
        value: bool,
    ) -> str:
        """將布林值轉換為顯示文字。"""

        return "開啟" if value else "關閉"

    @staticmethod
    def _format_destination(
        destination: str,
        channel_id: object,
    ) -> str:
        """格式化錯誤通報與結束報告位置。"""

        if (
            destination == "channel"
            and isinstance(channel_id, int)
        ):
            return f"<#{channel_id}>"

        return "Owner 私訊"